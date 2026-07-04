"""Order Flow Imbalance (OFI) and Micro-Price Engine.

Cont, Kukanov, Stoikov (2014) OFI — formal measure of supply/demand imbalance
from Level 1+2+3 order book changes. This is THE foundational microstructure
metric used by every prop desk.

Stoikov (2018) Micro-Price — weighted mid-price based on book imbalance and
queue dynamics. Provides a better "fair price" estimate than simple mid.

Also computes:
- Kyle's Lambda (price impact per unit of net order flow)
- Amihud Illiquidity Ratio (|return| / dollar volume)
- Roll Spread Estimator (from serial covariance of price changes)
- Corwin-Schultz Spread Estimator (from high-low prices)
- Depth-Weighted Mid-Price
- Trade Sign Autocorrelation (informed flow detection)
- Effective vs Realized Spread Decomposition
- Fill Probability at Best Bid/Ask (CME FIFO queue position)
"""
from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.ofi")

OFI_LEVELS = int(os.getenv("OFI_LEVELS", "5"))
OFI_DECAY = float(os.getenv("OFI_DECAY", "0.95"))
MICRO_PRICE_DEPTH = int(os.getenv("MICRO_PRICE_DEPTH", "5"))
KYLE_WINDOW = int(os.getenv("KYLE_WINDOW", "100"))
AMIHUD_WINDOW = int(os.getenv("AMIHUD_WINDOW", "100"))
ROLL_WINDOW = int(os.getenv("ROLL_WINDOW", "100"))
CORWIN_SCHULTZ_WINDOW = int(os.getenv("CORWIN_SCHULTZ_WINDOW", "30"))
TRADE_SIGN_WINDOW = int(os.getenv("TRADE_SIGN_WINDOW", "50"))
FILL_PROB_QUEUE_DEPTH = float(os.getenv("FILL_PROB_QUEUE_DEPTH", "100"))


class MicrostructureEngine:
    """Per-symbol microstructure alpha engine."""

    def __init__(self, symbol: str, tick_size: float = 0.0001) -> None:
        self.symbol = symbol
        self.tick_size = tick_size
        self._prev_bids: list[tuple[float, float]] = []
        self._prev_asks: list[tuple[float, float]] = []
        self._ofi: float = 0.0
        self._ofi_history: deque[float] = deque(maxlen=200)
        self._micro_price: float = 0.0
        self._depth_mid: float = 0.0
        self._trade_signs: deque[float] = deque(maxlen=TRADE_SIGN_WINDOW)
        self._price_changes: deque[float] = deque(maxlen=KYLE_WINDOW)
        self._order_flows: deque[float] = deque(maxlen=KYLE_WINDOW)
        self._returns: deque[float] = deque(maxlen=AMIHUD_WINDOW)
        self._dollar_volumes: deque[float] = deque(maxlen=AMIHUD_WINDOW)
        self._mid_prices: deque[float] = deque(maxlen=ROLL_WINDOW)
        self._highs: deque[float] = deque(maxlen=CORWIN_SCHULTZ_WINDOW)
        self._lows: deque[float] = deque(maxlen=CORWIN_SCHULTZ_WINDOW)
        self._kyle_lambda: float = 0.0
        self._amihud: float = 0.0
        self._roll_spread: float = 0.0
        self._corwin_schultz_spread: float = 0.0
        self._trade_sign_autocorr: float = 0.0
        self._effective_spread: float = 0.0
        self._realized_spread: float = 0.0
        self._fill_prob_bid: float = 0.0
        self._fill_prob_ask: float = 0.0
        self._last_mid: float = 0.0

    def update_book(self, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> None:
        ofi = self._compute_ofi(bids, asks)
        self._ofi = self._ofi * OFI_DECAY + ofi * (1 - OFI_DECAY)
        self._ofi_history.append(self._ofi)
        self._prev_bids = list(bids[:OFI_LEVELS])
        self._prev_asks = list(asks[:OFI_LEVELS])
        self._compute_micro_price(bids, asks)
        self._compute_depth_mid(bids, asks)
        self._compute_fill_probability(bids, asks)
        if bids and asks:
            mid = (bids[0][0] + asks[0][0]) / 2.0
            if self._last_mid > 0:
                ret = (mid - self._last_mid) / self._last_mid
                self._returns.append(ret)
            self._last_mid = mid
            self._mid_prices.append(mid)
            self._highs.append(max(p for p, _ in bids[:3]) if bids else mid)
            self._lows.append(min(p for p, _ in asks[:3]) if asks else mid)
        self._compute_kyle()
        self._compute_amihud()
        self._compute_roll()
        self._compute_corwin_schultz()
        self._compute_spread_decomposition(bids, asks)

    def on_trade(self, side: str, price: float, size: float) -> None:
        sign = 1.0 if side.lower() in ("buy", "bid") else -1.0
        self._trade_signs.append(sign)
        self._order_flows.append(sign * size)
        dollar_vol = price * size if price > 0 else size
        self._dollar_volumes.append(dollar_vol)
        if self._last_mid > 0 and price > 0:
            half_spread = abs(price - self._last_mid)
            self._effective_spread = 2.0 * half_spread
            self._realized_spread = half_spread
        self._compute_trade_sign_autocorr()

    def _compute_ofi(self, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> float:
        if not self._prev_bids or not self._prev_asks:
            return 0.0
        bid_ofi = 0.0
        for i in range(min(OFI_LEVELS, len(bids), len(self._prev_bids))):
            curr_p, curr_s = bids[i]
            prev_p, prev_s = self._prev_bids[i] if i < len(self._prev_bids) else (0, 0)
            if curr_p > prev_p:
                bid_ofi += curr_s
            elif curr_p == prev_p:
                bid_ofi += max(0, curr_s - prev_s)
            elif curr_p < prev_p:
                bid_ofi -= prev_s
        ask_ofi = 0.0
        for i in range(min(OFI_LEVELS, len(asks), len(self._prev_asks))):
            curr_p, curr_s = asks[i]
            prev_p, prev_s = self._prev_asks[i] if i < len(self._prev_asks) else (0, 0)
            if curr_p > prev_p:
                ask_ofi -= curr_s
            elif curr_p == prev_p:
                ask_ofi -= max(0, curr_s - prev_s)
            elif curr_p < prev_p:
                ask_ofi += prev_s
        return bid_ofi - ask_ofi

    def _compute_micro_price(self, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> None:
        if not bids or not asks:
            return
        best_bid, bid_size = bids[0]
        best_ask, ask_size = asks[0]
        total = bid_size + ask_size
        if total <= 0:
            self._micro_price = (best_bid + best_ask) / 2.0
            return
        imbalance = bid_size / total
        mid = (best_bid + best_ask) / 2.0
        half_spread = (best_ask - best_bid) / 2.0
        self._micro_price = mid + half_spread * (2 * imbalance - 1)

    def _compute_depth_mid(self, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> None:
        if not bids or not asks:
            return
        total_size = 0.0
        weighted_sum = 0.0
        for price, size in bids[:MICRO_PRICE_DEPTH]:
            weighted_sum += price * size
            total_size += size
        for price, size in asks[:MICRO_PRICE_DEPTH]:
            weighted_sum += price * size
            total_size += size
        self._depth_mid = weighted_sum / total_size if total_size > 0 else (bids[0][0] + asks[0][0]) / 2.0

    def _compute_fill_probability(self, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> None:
        if bids:
            best_bid_size = bids[0][1]
            total_bid_depth = sum(s for _, s in bids[:5])
            self._fill_prob_bid = 1.0 - min(1.0, best_bid_size / max(1, total_bid_depth)) * 0.3
            self._fill_prob_bid *= min(1.0, total_bid_depth / FILL_PROB_QUEUE_DEPTH)
        if asks:
            best_ask_size = asks[0][1]
            total_ask_depth = sum(s for _, s in asks[:5])
            self._fill_prob_ask = 1.0 - min(1.0, best_ask_size / max(1, total_ask_depth)) * 0.3
            self._fill_prob_ask *= min(1.0, total_ask_depth / FILL_PROB_QUEUE_DEPTH)

    def _compute_kyle(self) -> None:
        if len(self._price_changes) < 20 or len(self._order_flows) < 20:
            return
        flows = np.array(list(self._order_flows))
        changes = np.array(list(self._price_changes))
        if len(flows) != len(changes):
            return
        flow_std = np.std(flows)
        if flow_std > 0:
            self._kyle_lambda = float(np.cov(changes, flows)[0, 1] / (flow_std ** 2)) if flow_std > 1e-12 else 0.0
        else:
            self._kyle_lambda = 0.0
        if self._last_mid > 0 and len(self._mid_prices) >= 2:
            dp = self._mid_prices[-1] - self._mid_prices[-2] if len(self._mid_prices) >= 2 else 0
            if abs(self._ofi) > 1e-12:
                raw_lambda = abs(dp) / abs(self._ofi)
                self._kyle_lambda = self._kyle_lambda * 0.9 + raw_lambda * 0.1

    def _compute_amihud(self) -> None:
        if len(self._returns) < 20 or len(self._dollar_volumes) < 20:
            return
        n = min(len(self._returns), len(self._dollar_volumes))
        rets = list(self._returns)[-n:]
        vols = list(self._dollar_volumes)[-n:]
        total = 0.0
        count = 0
        for r, v in zip(rets, vols):
            if v > 0:
                total += abs(r) / v
                count += 1
        self._amihud = total / max(1, count) * 1e6 if count > 0 else 0.0

    def _compute_roll(self) -> None:
        if len(self._mid_prices) < 20:
            return
        prices = list(self._mid_prices)
        changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        if len(changes) < 10:
            return
        changes_arr = np.array(changes)
        if len(changes_arr) > 2:
            cov = np.cov(changes_arr[:-1], changes_arr[1:])[0, 1]
            self._roll_spread = 2.0 * math.sqrt(max(0, -cov)) if cov < 0 else 0.0

    def _compute_corwin_schultz(self) -> None:
        if len(self._highs) < 2 or len(self._lows) < 2:
            return
        highs = list(self._highs)[-CORWIN_SCHULTZ_WINDOW:]
        lows = list(self._lows)[-CORWIN_SCHULTZ_WINDOW:]
        if len(highs) < 2:
            return
        beta_sum = 0.0
        gamma_sum = 0.0
        count = 0
        for i in range(1, len(highs)):
            h2 = highs[i]
            l2 = lows[i]
            h1 = highs[i - 1]
            l1 = lows[i - 1]
            h = max(h1, h2)
            l = min(l1, l2)
            beta = math.log(max(l, 1e-12)) ** 2 + math.log(max(h, 1e-12)) ** 2 - 2 * math.log(max(l2, 1e-12)) * math.log(max(h2, 1e-12)) - 2 * math.log(max(l1, 1e-12)) * math.log(max(h1, 1e-12))
            gamma = (math.log(max(h, 1e-12)) - math.log(max(l, 1e-12))) ** 2 - beta
            beta_sum += beta
            gamma_sum += gamma
            count += 1
        if count > 0:
            beta_avg = beta_sum / count
            gamma_avg = gamma_sum / count
            sqrt_2 = math.sqrt(2)
            discriminant = max(0, 2 * beta_avg - gamma_avg / 2)
            alpha = (sqrt_2 - 1) * math.sqrt(discriminant) / sqrt_2 if discriminant > 0 else 0
            self._corwin_schultz_spread = 2 * (math.exp(alpha) - 1) / (1 + math.exp(alpha)) if alpha > 0 else 0.0

    def _compute_trade_sign_autocorr(self) -> None:
        if len(self._trade_signs) < 10:
            return
        signs = list(self._trade_signs)
        if len(signs) < 5:
            return
        signs_arr = np.array(signs)
        mean = np.mean(signs_arr)
        if np.std(signs_arr) > 1e-10:
            self._trade_sign_autocorr = float(np.corrcoef(signs_arr[:-1], signs_arr[1:])[0, 1])
        else:
            self._trade_sign_autocorr = 0.0

    def _compute_spread_decomposition(self, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> None:
        if not bids or not asks:
            return
        quoted_spread = asks[0][0] - bids[0][0]
        if self._effective_spread > 0:
            self._realized_spread = max(0, self._effective_spread - quoted_spread * 0.5)

    def get_metrics(self) -> dict[str, float]:
        return {
            "ofi": round(self._ofi, 2),
            "ofi_zscore": round(self._ofi_zscore(), 2),
            "micro_price": round(self._micro_price, 6),
            "depth_mid": round(self._depth_mid, 6),
            "micro_price_deviation_pips": round(self._micro_price_dev_pips(), 2),
            "kyle_lambda": round(self._kyle_lambda, 8),
            "amihud": round(self._amihud, 6),
            "roll_spread": round(self._roll_spread, 6),
            "corwin_schultz_spread": round(self._corwin_schultz_spread, 6),
            "trade_sign_autocorr": round(self._trade_sign_autocorr, 4),
            "effective_spread": round(self._effective_spread, 6),
            "realized_spread": round(self._realized_spread, 6),
            "fill_prob_bid": round(self._fill_prob_bid, 4),
            "fill_prob_ask": round(self._fill_prob_ask, 4),
            "informed_flow_detected": 1.0 if abs(self._trade_sign_autocorr) > 0.3 else 0.0,
            "ofi_imbalance_direction": 1.0 if self._ofi > 0 else (-1.0 if self._ofi < 0 else 0.0),
        }

    def _ofi_zscore(self) -> float:
        if len(self._ofi_history) < 20:
            return 0.0
        arr = np.array(list(self._ofi_history))
        std = np.std(arr)
        if std > 1e-10:
            return (self._ofi - np.mean(arr)) / std
        return 0.0

    def _micro_price_dev_pips(self) -> float:
        if self._last_mid <= 0 or self.tick_size <= 0:
            return 0.0
        return (self._micro_price - self._last_mid) / self.tick_size


class OFIManager:
    """Multi-symbol OFI and micro-price manager."""

    def __init__(self) -> None:
        self._engines: dict[str, MicrostructureEngine] = {}

    def get_engine(self, symbol: str, tick_size: float = 0.0001) -> MicrostructureEngine:
        if symbol not in self._engines:
            self._engines[symbol] = MicrostructureEngine(symbol, tick_size)
        return self._engines[symbol]

    def update_book(self, symbol: str, bids: list[tuple[float, float]], asks: list[tuple[float, float]], tick_size: float = 0.0001) -> None:
        self.get_engine(symbol, tick_size).update_book(bids, asks)

    def on_trade(self, symbol: str, side: str, price: float, size: float, tick_size: float = 0.0001) -> None:
        self.get_engine(symbol, tick_size).on_trade(side, price, size)

    def get_all_metrics(self) -> dict[str, dict[str, float]]:
        return {sym: eng.get_metrics() for sym, eng in self._engines.items()}

    def get_status(self) -> dict[str, Any]:
        return {"symbols": list(self._engines.keys())}
