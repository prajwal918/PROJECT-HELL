"""OVERSEER v12 Backtest Engine — Dual-Stream Architecture.

Replays historical tick data through the full OVERSEER pipeline, properly
combining CME futures data (for signals: delta, DOM, L3 microstructure)
with spot forex data (for execution: bid/ask, SL/TP, fills).

When futures data is unavailable, synthetic L3 signals are generated from
OHLC bar characteristics so the Z-gate pipeline still runs meaningfully.

Usage:
    python -m backtest.engine --symbol EURUSD --days 30
    python -m backtest.engine --sample 5000
    python -m backtest.engine --data backtest/data/spot/DAT_ASCII_EURUSD_M1_2025.csv
    python -m backtest.engine --symbol EURUSD --futures-data backtest/data/futures/6E_2025.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MT5_ENABLED", "false")

from collections import deque

from backtest.analytics import BacktestResult
from backtest.data_loader import (
    generate_sample_data,
    load_futures_data,
    load_spot_data,
    _infer_pip_size,
)
from backtest.simulator import SimExecutor, SimTrade

from config.instrument_config import InstrumentConfig
from core.candle_aggregator import CandleAggregator
from core.dxy_calculator import DXYCalculator
from core.risk_regime import RiskRegimeClassifier
from engine_logic.gates.gate_registry import GateRegistry
from ml.framework_scorer import aggregate_framework_scores, get_framework_feature_names
from ml.load_model import predict_trade_quality

LOGGER = logging.getLogger("overseer.backtest.engine")

L3_FIELDS = [
    "spoof_reversal_signal", "spoof_volume_vanished",
    "queue_exhaustion_signal", "queue_absorbed_volume", "queue_attrition_pct",
    "iceberg_detected", "iceberg_hidden_depth",
    "adverse_selection_risk", "adverse_selection_ratio",
    "hft_cluster_detected", "hft_synchronized_volume",
    "liquidity_vacuum_signal", "liquidity_vacuum_cv", "vacuum_cascade_depth",
    "institutional_flight_volume",
]


def merge_streams(
    spot_ticks: list[dict[str, Any]],
    futures_ticks: list[dict[str, Any]] | None = None,
    future_symbol: str = "6E",
) -> list[dict[str, Any]]:
    """Merge spot and futures tick streams by timestamp.

    Futures ticks carry L3/delta/DOM data that gets merged INTO the
    nearest spot tick. This way the gate pipeline sees both execution
    prices (spot) AND institutional signals (futures) just like live.
    """
    if not futures_ticks:
        return spot_ticks

    ft_sorted = sorted(futures_ticks, key=lambda t: t["timestamp"])
    st_sorted = sorted(spot_ticks, key=lambda t: t["timestamp"])
    if not st_sorted:
        return []

    fi = 0
    ft_len = len(ft_sorted)
    for spot in st_sorted:
        st_ts = spot["timestamp"]
        while fi < ft_len - 1 and ft_sorted[fi + 1]["timestamp"] <= st_ts:
            fi += 1

        ft = ft_sorted[fi]
        spot["rithmic_price"] = ft.get("ask", ft.get("bid", 0)) or spot.get("ask", 0)
        spot["deriv_price"] = spot.get("ask", 0)

        if ft.get("delta") is not None:
            spot["delta"] = ft["delta"]
        if ft.get("dom") and isinstance(ft["dom"], dict) and ft["dom"]:
            spot["dom"] = ft["dom"]

        for field in ("bid_size", "ask_size"):
            if ft.get(field, 0) > 0 and spot.get(field, 0) == 0:
                spot[field] = ft[field]

        for field in L3_FIELDS:
            if field in ft and ft[field] != 0:
                spot[field] = ft[field]

        if "lead_lag_pips" not in spot and spot.get("rithmic_price", 0) > 0:
            pip = _infer_pip_size(spot.get("symbol", "EURUSD"))
            spot_mid = (spot["bid"] + spot["ask"]) / 2.0
            fut_mid = float(spot.get("rithmic_price", spot_mid))
            if pip > 0:
                spot["lead_lag_pips"] = round((fut_mid - spot_mid) / pip, 2)
            else:
                spot["lead_lag_pips"] = 0.0

    LOGGER.info("Merged %d spot + %d futures ticks", len(st_sorted), ft_len)
    return st_sorted


def enrich_with_synthetic_l3(
    ticks: list[dict[str, Any]],
    symbol: str = "EURUSD",
    intensity: float = 1.0,
) -> list[dict[str, Any]]:
    """Generate synthetic L3 microstructure signals from OHLC bar data.

    When no CME futures data is available, this creates plausible order-flow
    signals based on bar characteristics (range, wicks, volume) so the
    Z-gate pipeline (gate_Z, gate_Z1-Z94) can still fire in backtests.

    Parameters
    ----------
    intensity : float
        0.0 = no synthetic signals (all Z gates fail = spot-only mode)
        1.0 = full synthetic signals (realistic distribution)
        >1.0 = more aggressive (higher hit rate for testing)
    """
    if intensity <= 0:
        return ticks

    pip = _infer_pip_size(symbol)
    prev_mid: float | None = None
    prev_delta: float = 0.0
    rng = random.Random(42)

    for tick in ticks:
        mid = (float(tick.get("bid", 0)) + float(tick.get("ask", 0))) / 2.0

        bar_range_pips = 0.0
        upper_wick_ratio = 0.0
        lower_wick_ratio = 0.0
        if "bar_open" in tick:
            o = float(tick["bar_open"])
            h = float(tick["bar_high"])
            l = float(tick["bar_low"])
            c = float(tick["bar_close"])
            bar_range = h - l
            bar_range_pips = bar_range / pip if pip > 0 else 0.0
            if bar_range > 0:
                body_high = max(o, c)
                body_low = min(o, c)
                upper_wick_ratio = (h - body_high) / bar_range
                lower_wick_ratio = (body_low - l) / bar_range
        elif prev_mid is not None and pip > 0:
            bar_range_pips = abs(mid - prev_mid) / pip

        delta = float(tick.get("delta", 0.0))
        if delta == 0.0:
            if prev_mid is not None and prev_mid > 0:
                delta = (mid - prev_mid) / pip * 10 * rng.uniform(0.5, 2.0)
            else:
                delta = rng.gauss(0, 20)

        bid_size = float(tick.get("bid_size", 0.0))
        ask_size = float(tick.get("ask_size", 0.0))
        if bid_size == 0 and ask_size == 0:
            bid_size = rng.uniform(2, 15)
            ask_size = rng.uniform(2, 15)
            tick["bid_size"] = bid_size
            tick["ask_size"] = ask_size

        imbalance = 0.0
        total_size = bid_size + ask_size
        if total_size > 0:
            imbalance = (ask_size - bid_size) / total_size

        if delta > 20:
            trend_strength = min(1.0, delta / 100.0)
        elif delta < -20:
            trend_strength = -min(1.0, abs(delta) / 100.0)
        else:
            trend_strength = 0.0

        spoof_prob = 0.15 * intensity
        if upper_wick_ratio > 0.5 or lower_wick_ratio > 0.5:
            spoof_prob = 0.45 * intensity
        if rng.random() < spoof_prob:
            tick["spoof_reversal_signal"] = round(rng.uniform(0.3, 1.0) * intensity, 3)
            tick["spoof_volume_vanished"] = round(rng.uniform(20, 150) * intensity, 1)

        queue_prob = 0.1 * intensity
        if abs(delta) > 30:
            queue_prob = 0.35 * intensity
        if rng.random() < queue_prob:
            tick["queue_exhaustion_signal"] = round(rng.uniform(0.2, 0.9) * intensity, 3)
            tick["queue_absorbed_volume"] = round(rng.uniform(50, 500) * intensity, 1)
            tick["queue_attrition_pct"] = round(rng.uniform(0.1, 0.6) * intensity, 3)

        iceberg_prob = 0.08 * intensity
        if bar_range_pips < 3 and abs(delta) > 15:
            iceberg_prob = 0.3 * intensity
        if rng.random() < iceberg_prob:
            tick["iceberg_detected"] = round(rng.uniform(0.2, 0.8) * intensity, 3)
            tick["iceberg_hidden_depth"] = round(rng.uniform(30, 300) * intensity, 1)

        adverse_prob = 0.05 * intensity
        if abs(imbalance) > 0.3:
            adverse_prob = 0.25 * intensity
        if rng.random() < adverse_prob:
            tick["adverse_selection_risk"] = round(rng.uniform(0.1, 0.6) * intensity, 3)
            tick["adverse_selection_ratio"] = round(rng.uniform(0.05, 0.4) * intensity, 3)

        hft_prob = 0.12 * intensity
        if rng.random() < hft_prob:
            tick["hft_cluster_detected"] = round(rng.uniform(0.1, 0.7) * intensity, 3)
            tick["hft_synchronized_volume"] = round(rng.uniform(10, 200) * intensity, 1)

        vacuum_prob = 0.06 * intensity
        if bar_range_pips > 5:
            vacuum_prob = 0.2 * intensity
        if rng.random() < vacuum_prob:
            tick["liquidity_vacuum_signal"] = round(rng.uniform(0.1, 0.8) * intensity, 3)
            tick["liquidity_vacuum_cv"] = round(rng.uniform(1.5, 5.0) * intensity, 2)
            tick["vacuum_cascade_depth"] = round(rng.uniform(1, 5) * intensity, 1)

        flight_prob = 0.04 * intensity
        if abs(trend_strength) > 0.5:
            flight_prob = 0.15 * intensity
        if rng.random() < flight_prob:
            tick["institutional_flight_volume"] = round(rng.uniform(100, 1000) * intensity, 1)

        tick["delta"] = round(delta, 2)

        if "rithmic_price" not in tick:
            fut_offset = rng.gauss(0, pip * 0.3)
            tick["rithmic_price"] = round(mid + fut_offset, 6)
        if "deriv_price" not in tick:
            tick["deriv_price"] = tick.get("ask", mid)
        if "lead_lag_pips" not in tick:
            rp = float(tick.get("rithmic_price", mid))
            if pip > 0:
                tick["lead_lag_pips"] = round((rp - mid) / pip, 2)

        depth_bid = rng.uniform(10, 80) * intensity
        depth_ask = rng.uniform(10, 80) * intensity
        tick["depth_bid_3"] = round(depth_bid, 1)
        tick["depth_ask_3"] = round(depth_ask, 1)

        prev_mid = mid
        prev_delta = delta

    return ticks


class BacktestEngine:
    """Main backtest engine — replays ticks through OVERSEER pipeline.

    Supports dual-stream mode: CME futures ticks provide L3 signals,
    spot forex ticks provide execution prices. When futures data is
    absent, synthetic L3 enrichment can be enabled.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.quality_threshold = float(cfg.get("quality_threshold", 0.65))
        self.gate_eval_interval = int(cfg.get("gate_eval_interval", 1))
        self.bias_max_shift = float(cfg.get("bias_max_shift", 0.15))
        self.account_balance = float(cfg.get("account_balance", 10000.0))
        self.slippage_pips = float(cfg.get("slippage_pips", 1.0))
        self.max_spread_pips = float(cfg.get("max_spread_pips", 5.0))
        self.commission_per_lot = float(cfg.get("commission_per_lot", 7.0))
        self.max_daily_trades = int(cfg.get("max_daily_trades", 3))
        self.max_daily_loss_pct = float(cfg.get("max_daily_loss_pct", 3.0))
        self.consecutive_loss_limit = int(cfg.get("consecutive_loss_limit", 2))
        self.verbose = bool(cfg.get("verbose", False))
        self.progress_interval = int(cfg.get("progress_interval", 1000))
        self.l3_intensity = float(cfg.get("l3_intensity", 1.0))
        self.lot_size = float(cfg.get("lot_size", 0.01))
        self.momentum_lookback = int(cfg.get("momentum_lookback", 4))
        self.min_trade_cooldown = int(cfg.get("min_trade_cooldown", 20))
        self.sl_override = float(cfg.get("sl_override", 0.0))
        self.tp_override = float(cfg.get("tp_override", 0.0))
        self.entry_mode = str(cfg.get("entry_mode", "ml"))
        self.trend_lookback = int(cfg.get("trend_lookback", 20))
        self.breakout_atr_mult = float(cfg.get("breakout_atr_mult", 1.0))
        self.sl_atr_mult = float(cfg.get("sl_atr_mult", 0.0))
        self.tp_atr_mult = float(cfg.get("tp_atr_mult", 0.0))
        self._atr_history: deque[float] = deque(maxlen=100)
        self._last_bar_open: float | None = None

        self.instrument_config = InstrumentConfig.get_instance()
        self.registry = GateRegistry()
        self.dxy_calc = DXYCalculator()
        self.risk_regime = RiskRegimeClassifier()
        self.candle_aggregator = CandleAggregator()
        self.executor = SimExecutor(
            account_balance=self.account_balance,
            slippage_pips=self.slippage_pips,
            max_spread_pips=self.max_spread_pips,
            commission_per_lot=self.commission_per_lot,
        )

        self._open_symbols: set[str] = set()
        self._ticket_to_symbol: dict[int, str] = {}
        self._latest_mids: dict[str, float] = {}
        self._previous_mid: float | None = None
        self._mid_history: deque[float] = deque(maxlen=max(self.momentum_lookback + 1, 20))
        self._balance_history: list[float] = []
        self._daily_trades: int = 0
        self._daily_pnl: float = 0.0
        self._current_day: str = ""
        self._consecutive_losses: int = 0
        self._spot_symbol: str = ""
        self._last_trade_tick: int = 0

    def run(self, ticks: list[dict[str, Any]]) -> BacktestResult:
        """Run backtest over a list of normalised tick dicts."""
        total = len(ticks)
        LOGGER.info("Starting backtest: %d ticks, threshold=%.2f, l3_intensity=%.2f",
                     total, self.quality_threshold, self.l3_intensity)
        start_time = time.monotonic()

        for tick_count, tick in enumerate(ticks, 1):
            self._process_tick(tick, tick_count)

            if tick_count % self.progress_interval == 0:
                elapsed = time.monotonic() - start_time
                rate = tick_count / elapsed if elapsed > 0 else 0
                LOGGER.info(
                    "Progress: %d/%d (%.1f%%) trades=%d pnl=$%.2f rate=%.0f ticks/s",
                    tick_count, total, tick_count / total * 100,
                    len(self.executor.closed_trades),
                    self.executor.account_balance - self.account_balance,
                    rate,
                )

        elapsed = time.monotonic() - start_time
        LOGGER.info("Backtest complete: %d ticks in %.1fs (%.0f ticks/s)",
                     total, elapsed, total / elapsed if elapsed > 0 else 0)

        return BacktestResult(
            trades=self.executor.closed_trades,
            balance_history=self._balance_history,
            tick_count=total,
            config={
                "quality_threshold": self.quality_threshold,
                "bias_max_shift": self.bias_max_shift,
                "slippage_pips": self.slippage_pips,
                "commission_per_lot": self.commission_per_lot,
                "account_balance": self.account_balance,
                "l3_intensity": self.l3_intensity,
                "lot_size": self.lot_size,
            },
        )

    def _process_tick(self, tick: dict[str, Any], tick_count: int) -> None:
        symbol = tick.get("symbol", "")
        bid = float(tick.get("bid", 0))
        ask = float(tick.get("ask", 0))
        if bid <= 0 or ask <= 0:
            return

        if not self._spot_symbol and symbol:
            self._spot_symbol = symbol

        current_mid = (bid + ask) / 2.0
        self._latest_mids[symbol] = current_mid

        try:
            self.instrument_config.enrich_tick(tick)
        except Exception:
            pass

        tick["prev_mid"] = self._previous_mid
        if self.momentum_lookback > 1 and len(self._mid_history) >= self.momentum_lookback:
            tick["prev_mid"] = self._mid_history[0]
        self._mid_history.append(current_mid)
        if self._previous_mid is not None and self._previous_mid > 0:
            bar_close = tick.get("bar_close")
            bar_open = tick.get("bar_open")
            if bar_close is not None and bar_open is not None and float(bar_close) != float(bar_open):
                tick.setdefault("direction", "BUY" if float(bar_close) > float(bar_open) else "SELL")
            elif float(tick.get("ask_size", 0)) > 0 or float(tick.get("bid_size", 0)) > 0:
                tick.setdefault("direction", "BUY" if float(tick.get("ask_size", 0)) > float(tick.get("bid_size", 0)) else "SELL")
            else:
                if current_mid > self._previous_mid:
                    tick.setdefault("direction", "BUY")
                elif current_mid < self._previous_mid:
                    tick.setdefault("direction", "SELL")
                else:
                    tick.setdefault("direction", "BUY")
        else:
            tick.setdefault("direction", "BUY")

        try:
            from core.symbol_mapper import annotate_tick
            tick = annotate_tick(tick)
        except Exception:
            pass

        spread_val = ask - bid
        try:
            self.risk_regime.update_spread(symbol, spread_val)
        except Exception:
            pass

        try:
            self.dxy_calc.update(symbol, current_mid)
        except Exception:
            pass

        if tick_count % 10 == 0:
            try:
                tick["dxy_trend"] = self.dxy_calc.get_dxy_trend()
                tick["risk_regime"] = self.risk_regime.classify()
            except Exception:
                tick.setdefault("dxy_trend", "neutral")
                tick.setdefault("risk_regime", "neutral")
        else:
            tick.setdefault("dxy_trend", "neutral")
            tick.setdefault("risk_regime", "neutral")

        try:
            self.candle_aggregator.process_tick(tick)
        except Exception:
            pass

        self._previous_mid = current_mid

        closed = self.executor.check_sl_tp(tick, tick_count)
        for ct in closed:
            sym = self._ticket_to_symbol.pop(ct.ticket, "")
            self._open_symbols.discard(sym)
            self._daily_pnl += ct.pnl
            if ct.pnl <= 0:
                self._consecutive_losses += 1
            else:
                self._consecutive_losses = 0

        if tick_count % self.gate_eval_interval != 0 and not self._open_symbols:
            self._balance_history.append(self.executor.equity)
            return

        gate_states = self.registry.evaluate(tick)

        gate_d = gate_states.get("gate_D", False)
        gate_z7 = gate_states.get("gate_Z7", False)

        bar_open = tick.get("bar_open")
        bar_close = tick.get("bar_close")
        bar_high = tick.get("bar_high")
        bar_low = tick.get("bar_low")
        new_bar = bar_open is not None and self._last_bar_open is not None and float(bar_open) != float(self._last_bar_open)
        if bar_open is not None:
            self._last_bar_open = float(bar_open)
        if bar_high is not None and bar_low is not None:
            atr = float(bar_high) - float(bar_low)
            self._atr_history.append(atr)

        if self.entry_mode == "rule":
            if not self._should_enter_rule(tick, tick_count, symbol, gate_states):
                self._balance_history.append(self.executor.equity)
                return
            adjusted_score = 0.70
            fw_scores = {}
        else:
            if not gate_d or not gate_z7:
                self._balance_history.append(self.executor.equity)
                return
            score = predict_trade_quality(gate_states)
            fw_scores = aggregate_framework_scores(gate_states)
            adjusted_score = max(0.0, min(1.0, score + max(-self.bias_max_shift, min(self.bias_max_shift, 0.0))))
            if adjusted_score <= self.quality_threshold:
                self._balance_history.append(self.executor.equity)
                return

        ts = tick.get("timestamp", 0)
        if isinstance(ts, (int, float)):
            day = str(ts // 86400000)
        else:
            day = str(ts)[:10]
        if day != self._current_day:
            self._current_day = day
            self._daily_trades = 0
            self._daily_pnl = 0.0

        if self._daily_trades >= self.max_daily_trades:
            self._balance_history.append(self.executor.equity)
            return

        daily_limit = self.account_balance * (self.max_daily_loss_pct / 100.0)
        if self._daily_pnl < -daily_limit:
            self._balance_history.append(self.executor.equity)
            return

        if self._consecutive_losses >= self.consecutive_loss_limit:
            self._balance_history.append(self.executor.equity)
            return

        if symbol in self._open_symbols:
            self._balance_history.append(self.executor.equity)
            return

        if tick_count - self._last_trade_tick < self.min_trade_cooldown:
            self._balance_history.append(self.executor.equity)
            return

        direction = tick.get("direction", "BUY")
        try:
            profile = self.instrument_config.get_profile(symbol)
            pip_size = profile.pip_size
            base_sl = self.sl_override if self.sl_override > 0 else profile.sl_pips
            base_tp = self.tp_override if self.tp_override > 0 else profile.tp_pips
        except Exception:
            pip_size = 0.01 if "JPY" in symbol.upper() or symbol.upper().startswith("XAU") else 0.0001
            base_sl = float(os.getenv("SL_PIPS", "5"))
            base_tp = float(os.getenv("TP_PIPS", "12.5"))

        avg_atr = sum(self._atr_history) / len(self._atr_history) if self._atr_history else 0
        if self.sl_atr_mult > 0 and avg_atr > 0 and pip_size > 0:
            sl_pips = max(3.0, (avg_atr * self.sl_atr_mult) / pip_size)
            tp_pips = max(6.0, (avg_atr * self.tp_atr_mult) / pip_size)
        else:
            sl_pips = base_sl
            tp_pips = base_tp

        result = self.executor.execute_trade(
            symbol=symbol,
            direction=direction,
            lot_size=self.lot_size,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            tick=tick,
            tick_count=tick_count,
            score=adjusted_score,
            gate_states=gate_states,
            framework_scores=fw_scores,
        )

        if result:
            self._open_symbols.add(symbol)
            self._ticket_to_symbol[int(result["ticket"])] = symbol
            self._daily_trades += 1
            self._last_trade_tick = tick_count

            if self.executor.closed_trades:
                self.executor.closed_trades[-1].score = adjusted_score
                self.executor.closed_trades[-1].gate_states = gate_states
                self.executor.closed_trades[-1].framework_scores = fw_scores

            if self.verbose:
                LOGGER.info(
                    "TRADE: #%d %s %s entry=%.5f SL=%.5f TP=%.5f score=%.4f",
                    result["ticket"], direction, symbol,
                    result["price"], result["sl"], result["tp"], adjusted_score,
                )

        self._balance_history.append(self.executor.equity)

    def _should_enter_rule(self, tick: dict[str, Any], tick_count: int, symbol: str, gate_states: dict[str, bool]) -> bool:
        direction = tick.get("direction", "BUY")
        bar_high = tick.get("bar_high")
        bar_low = tick.get("bar_low")
        bar_open = tick.get("bar_open")
        bar_close = tick.get("bar_close")

        if bar_high is None or bar_low is None or bar_open is None or bar_close is None:
            return False

        high = float(bar_high)
        low = float(bar_low)
        bopen = float(bar_open)
        bclose = float(bar_close)
        mid = (float(tick.get("bid", 0)) + float(tick.get("ask", 0))) / 2.0

        avg_atr = sum(self._atr_history) / len(self._atr_history) if self._atr_history else 0
        if avg_atr <= 0:
            return False

        body = abs(bclose - bopen)
        body_ratio = body / avg_atr if avg_atr > 0 else 0
        if body_ratio < self.breakout_atr_mult:
            return False

        if direction == "BUY":
            if bclose <= bopen:
                return False
        else:
            if bclose >= bopen:
                return False

        regime = tick.get("risk_regime", "neutral")
        if regime == "risk-off":
            return False

        if not gate_states.get("gate_M", True):
            return False

        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="OVERSEER v12 Backtest Engine (Dual-Stream)")
    parser.add_argument("--symbol", default="EURUSD", help="Spot symbol (default: EURUSD)")
    parser.add_argument("--futures-symbol", default=None, help="CME futures root (e.g. 6E). Auto-resolved if not set.")
    parser.add_argument("--data", default=None, help="Path to single spot CSV file")
    parser.add_argument("--futures-data", default=None, help="Path to single futures CSV file")
    parser.add_argument("--sample", type=int, default=None, help="Use N synthetic sample ticks")
    parser.add_argument("--days", type=int, default=None, help="Only use last N days of data")
    parser.add_argument("--threshold", type=float, default=0.65, help="Quality score threshold (default: 0.65)")
    parser.add_argument("--balance", type=float, default=10000.0, help="Starting balance (default: 10000)")
    parser.add_argument("--lot", type=float, default=0.01, help="Lot size per trade (default: 0.01)")
    parser.add_argument("--sl", type=float, default=0, help="Override SL pips (0=use instrument config)")
    parser.add_argument("--tp", type=float, default=0, help="Override TP pips (0=use instrument config)")
    parser.add_argument("--slippage", type=float, default=1.0, help="Simulated slippage pips (default: 1.0)")
    parser.add_argument("--commission", type=float, default=7.0, help="Commission per lot (default: 7.0)")
    parser.add_argument("--max-spread", type=float, default=5.0, help="Max spread pips (default: 5.0)")
    parser.add_argument("--bias-max-shift", type=float, default=0.15, help="Max bias shift (default: 0.15)")
    parser.add_argument("--eval-interval", type=int, default=1, help="Gate eval every N ticks (default: 1)")
    parser.add_argument("--max-daily-trades", type=int, default=3, help="Max trades/day (default: 3)")
    parser.add_argument("--max-daily-loss", type=float, default=3.0, help="Max daily loss %% (default: 3.0)")
    parser.add_argument("--consecutive-loss-limit", type=int, default=2, help="Halt after N consecutive losses (default: 2)")
    parser.add_argument("--momentum-lookback", type=int, default=4, help="Ticks back for gate_D momentum calc (default: 4)")
    parser.add_argument("--cooldown", type=int, default=20, help="Min ticks between trades (default: 20)")
    parser.add_argument("--l3-intensity", type=float, default=1.0, help="Synthetic L3 signal intensity 0-2 (default: 1.0). 0=spot-only, >1=more signals")
    parser.add_argument("--entry-mode", choices=["ml", "rule"], default="ml", help="Entry mode: ml=XGBoost, rule=trend breakout (default: ml)")
    parser.add_argument("--trend-lookback", type=int, default=20, help="Bars for trend lookback in rule mode (default: 20)")
    parser.add_argument("--breakout-atr", type=float, default=1.0, help="ATR multiplier for breakout in rule mode (default: 1.0)")
    parser.add_argument("--sl-atr", type=float, default=0.0, help="SL = N * ATR (0=fixed pips, default: 0)")
    parser.add_argument("--tp-atr", type=float, default=0.0, help="TP = N * ATR (0=fixed pips, default: 0)")
    parser.add_argument("--no-l3", action="store_true", help="Disable synthetic L3 enrichment entirely")
    parser.add_argument("--verbose", action="store_true", help="Print every trade")
    parser.add_argument("--progress", type=int, default=1000, help="Progress every N ticks")
    parser.add_argument("--output", default=None, help="Output filename prefix")
    parser.add_argument("--max-ticks", type=int, default=None, help="Cap ticks loaded (for quick tests)")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.sample:
        LOGGER.info("Using %d synthetic sample ticks", args.sample)
        ticks = generate_sample_data(symbol=args.symbol, num_ticks=args.sample)
        if not args.no_l3:
            ticks = enrich_with_synthetic_l3(ticks, args.symbol, args.l3_intensity)

    elif args.data or not args.sample:
        start = None
        if args.days:
            from datetime import datetime, timedelta, timezone
            start = (datetime.now(tz=timezone.utc) - timedelta(days=args.days)).isoformat()

        if args.data:
            from backtest.data_loader import _load_csv_file
            path = Path(args.data)
            if not path.exists():
                LOGGER.error("File not found: %s", args.data)
                sys.exit(1)
            spot_ticks = _load_csv_file(path, args.symbol, _infer_pip_size(args.symbol), 1.5)
            LOGGER.info("Loaded %d spot ticks from %s", len(spot_ticks), args.data)
        else:
            spot_ticks = load_spot_data(args.symbol, start_date=start, max_ticks=args.max_ticks)

        if not spot_ticks:
            LOGGER.warning("No spot data found — falling back to 5000 sample ticks")
            spot_ticks = generate_sample_data(symbol=args.symbol, num_ticks=5000)

        futures_ticks = None
        fut_sym = args.futures_symbol
        if not fut_sym:
            try:
                from core.symbol_mapper import get_future_to_spot_and_reverse_map
                _, s2f = get_future_to_spot_and_reverse_map()
                fut_sym = s2f.get(args.symbol)
            except Exception:
                pass

        if args.futures_data:
            from backtest.data_loader import _load_csv_file
            fut_path = Path(args.futures_data)
            if fut_path.exists():
                futures_ticks = _load_csv_file(fut_path, fut_sym or "6E", _infer_pip_size(fut_sym or "6E"), 1.5)
                LOGGER.info("Loaded %d futures ticks from %s", len(futures_ticks), args.futures_data)
        elif fut_sym:
            futures_ticks = load_futures_data(fut_sym, start_date=start)

        if futures_ticks:
            ticks = merge_streams(spot_ticks, futures_ticks, fut_sym or "6E")
            LOGGER.info("Dual-stream mode: %d merged ticks", len(ticks))
        else:
            ticks = spot_ticks
            if not args.no_l3:
                LOGGER.info("No futures data — applying synthetic L3 enrichment (intensity=%.1f)", args.l3_intensity)
                ticks = enrich_with_synthetic_l3(ticks, args.symbol, args.l3_intensity)
            else:
                LOGGER.info("Spot-only mode: L3 gates will have no signal data")

    else:
        ticks = []

    if not ticks:
        LOGGER.error("No tick data available. Place CSV files in backtest/data/spot/ or use --sample")
        sys.exit(1)

    config = {
        "quality_threshold": args.threshold,
        "bias_max_shift": args.bias_max_shift,
        "account_balance": args.balance,
        "slippage_pips": args.slippage,
        "max_spread_pips": args.max_spread,
        "commission_per_lot": args.commission,
        "gate_eval_interval": args.eval_interval,
        "max_daily_trades": args.max_daily_trades,
        "max_daily_loss_pct": args.max_daily_loss,
        "consecutive_loss_limit": args.consecutive_loss_limit,
        "verbose": args.verbose,
        "progress_interval": args.progress,
        "l3_intensity": 0.0 if args.no_l3 else args.l3_intensity,
        "lot_size": args.lot,
        "sl_override": args.sl,
        "tp_override": args.tp,
        "momentum_lookback": args.momentum_lookback,
        "min_trade_cooldown": args.cooldown,
        "entry_mode": args.entry_mode,
        "trend_lookback": args.trend_lookback,
        "breakout_atr_mult": args.breakout_atr,
        "sl_atr_mult": args.sl_atr,
        "tp_atr_mult": args.tp_atr,
    }

    engine = BacktestEngine(config)
    result = engine.run(ticks)

    report_path = result.save(args.output)
    print(result.text_report())
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
