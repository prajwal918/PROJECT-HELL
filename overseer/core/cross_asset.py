"""Cross-Asset Signal Engine.

Commodity-Currency links:
  - AUD correlated with iron ore
  - CAD correlated with crude oil
  - NZD correlated with dairy prices

Bond-Currency flows:
  - Real-time yield curve shifts driving FX moves
  - US 10Y vs German Bund spread → EUR/USD

Equity-Currency risk flows:
  - VIX/SPX correlation with JPY (risk-off = JPY bid)
  - AUD correlated with equity market breadth

Carry Trade Flow Estimation:
  - When JPY weakens systematically = carry unwinding
  - Forward premium / interest differential as signal

Credit-Currency link:
  - CDS spreads, credit spreads as FX stress indicators
"""
from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.cross_asset")

CROSS_ASSET_HISTORY = int(os.getenv("CROSS_ASSET_HISTORY", "200"))
CARRY_LOOKBACK = int(os.getenv("CARRY_LOOKBACK", "20"))
CORR_WINDOW = int(os.getenv("CROSS_CORR_WINDOW", "50"))
IRON_ORE_AUD_WEIGHT = float(os.getenv("IRON_ORE_AUD_WEIGHT", "0.30"))
OIL_CAD_WEIGHT = float(os.getenv("OIL_CAD_WEIGHT", "0.30"))
VIX_JPY_WEIGHT = float(os.getenv("VIX_JPY_WEIGHT", "0.25"))
YIELD_FX_WEIGHT = float(os.getenv("YIELD_FX_WEIGHT", "0.20"))
CARRY_FLOW_THRESHOLD = float(os.getenv("CARRY_FLOW_THRESHOLD", "0.02"))


class CrossAssetEngine:
    """Multi-asset signal engine for institutional cross-market alpha."""

    def __init__(self) -> None:
        self._fx_returns: dict[str, deque[float]] = {}
        self._commodity_returns: dict[str, deque[float]] = {}
        self._equity_returns: dict[str, deque[float]] = {}
        self._yield_changes: dict[str, deque[float]] = {}
        self._vix_history: deque[float] = deque(maxlen=CROSS_ASSET_HISTORY)
        self._carry_signals: dict[str, float] = {}
        self._risk_flow: dict[str, float] = {}
        self._last_prices: dict[str, float] = {}

    def update_fx(self, symbol: str, mid: float) -> None:
        self._update_return("fx", symbol, mid)

    def update_commodity(self, name: str, price: float) -> None:
        self._update_return("commodity", name, price)

    def update_equity(self, name: str, price: float) -> None:
        self._update_return("equity", name, price)

    def update_yield(self, name: str, value: float) -> None:
        if name not in self._yield_changes:
            self._yield_changes[name] = deque(maxlen=CROSS_ASSET_HISTORY)
        self._yield_changes[name].append(value)

    def update_vix(self, vix: float) -> None:
        self._vix_history.append(vix)

    def _update_return(self, asset_type: str, key: str, price: float) -> None:
        store = {"fx": self._fx_returns, "commodity": self._commodity_returns, "equity": self._equity_returns}[asset_type]
        if key not in store:
            store[key] = deque(maxlen=CROSS_ASSET_HISTORY)
        prev = self._last_prices.get(key, 0)
        self._last_prices[key] = price
        if prev > 0:
            ret = (price - prev) / prev
            store[key].append(ret)

    def commodity_currency_signal(self, fx_symbol: str) -> dict[str, float]:
        signals = {}
        if fx_symbol in ("6AM6", "AUDUSD"):
            iron_ore = list(self._commodity_returns.get("iron_ore", []))
            aud = list(self._fx_returns.get(fx_symbol, []))
            if len(iron_ore) >= 20 and len(aud) >= 20:
                min_len = min(len(iron_ore), len(aud))
                corr = float(np.corrcoef(iron_ore[-min_len:], aud[-min_len:])[0, 1])
                signals["iron_ore_aud_corr"] = round(corr, 4)
                signals["iron_ore_aud_signal"] = round(corr * IRON_ORE_AUD_WEIGHT, 4)

        if fx_symbol in ("6CM6", "USDCAD"):
            oil = list(self._commodity_returns.get("crude_oil", []))
            cad = list(self._fx_returns.get(fx_symbol, []))
            if len(oil) >= 20 and len(cad) >= 20:
                min_len = min(len(oil), len(cad))
                corr = float(np.corrcoef(oil[-min_len:], cad[-min_len:])[0, 1])
                signals["oil_cad_corr"] = round(corr, 4)
                signals["oil_cad_signal"] = round(corr * OIL_CAD_WEIGHT, 4)

        return signals

    def equity_currency_risk_flow(self, fx_symbol: str) -> dict[str, float]:
        signals = {}
        vix = list(self._vix_history)
        fx = list(self._fx_returns.get(fx_symbol, []))

        if len(vix) >= 20 and len(fx) >= 20:
            min_len = min(len(vix), len(fx))
            corr = float(np.corrcoef(vix[-min_len:], fx[-min_len:])[0, 1])
            jpy_symbols = ("6JM6", "USDJPY", "6SM6", "USDCHF")
            if fx_symbol in jpy_symbols:
                risk_signal = -corr * VIX_JPY_WEIGHT
            else:
                risk_signal = corr * VIX_JPY_WEIGHT * 0.5
            signals["vix_fx_corr"] = round(corr, 4)
            signals["risk_flow_signal"] = round(risk_signal, 4)

        if len(vix) >= 5:
            vix_current = vix[-1]
            vix_mean = float(np.mean(vix[-50:])) if len(vix) >= 50 else float(np.mean(vix))
            vix_z = (vix_current - vix_mean) / max(1e-6, float(np.std(vix[-50:]))) if len(vix) >= 50 else 0
            self._risk_flow[fx_symbol] = vix_z
            signals["vix_zscore"] = round(vix_z, 2)
            signals["risk_regime_signal"] = round(vix_z * -0.1, 4) if fx_symbol in ("6JM6", "6SM6") else round(vix_z * 0.05, 4)

        return signals

    def yield_currency_signal(self, fx_symbol: str) -> dict[str, float]:
        signals = {}
        us_10y = list(self._yield_changes.get("us_10y", []))
        bund_10y = list(self._yield_changes.get("bund_10y", []))
        if fx_symbol in ("6EM6", "EURUSD") and len(us_10y) >= 10 and len(bund_10y) >= 10:
            min_len = min(len(us_10y), len(bund_10y))
            spread = np.array(us_10y[-min_len:]) - np.array(bund_10y[-min_len:])
            if len(spread) >= 5:
                spread_z = (spread[-1] - float(np.mean(spread))) / max(1e-6, float(np.std(spread)))
                signals["us_bund_spread_z"] = round(float(spread_z), 2)
                signals["yield_fx_signal"] = round(float(spread_z) * YIELD_FX_WEIGHT, 4)

        jgb = list(self._yield_changes.get("jgb_10y", []))
        if fx_symbol in ("6JM6", "USDJPY") and len(us_10y) >= 10 and len(jgb) >= 10:
            min_len = min(len(us_10y), len(jgb))
            spread = np.array(us_10y[-min_len:]) - np.array(jgb[-min_len:])
            if len(spread) >= 5:
                spread_z = (spread[-1] - float(np.mean(spread))) / max(1e-6, float(np.std(spread)))
                signals["us_jgb_spread_z"] = round(float(spread_z), 2)
                signals["yield_fx_signal"] = round(float(spread_z) * YIELD_FX_WEIGHT, 4)

        return signals

    def carry_trade_signal(self, fx_symbol: str, rate_diff: float = 0.0) -> dict[str, float]:
        fx = list(self._fx_returns.get(fx_symbol, []))
        signals = {"carry_bias": round(rate_diff, 4)}
        if len(fx) >= CARRY_LOOKBACK:
            recent_return = float(np.mean(fx[-CARRY_LOOKBACK:]))
            carry_expected = rate_diff / 252 * CARRY_LOOKBACK
            carry_residual = recent_return - carry_expected
            signals["carry_residual"] = round(carry_residual, 6)
            if abs(carry_residual) > CARRY_FLOW_THRESHOLD:
                if carry_residual < -CARRY_FLOW_THRESHOLD and rate_diff > 0:
                    signals["carry_unwind_signal"] = 1.0
                    signals["carry_flow_direction"] = -1.0
                elif carry_residual > CARRY_FLOW_THRESHOLD and rate_diff > 0:
                    signals["carry_unwind_signal"] = 0.0
                    signals["carry_flow_direction"] = 1.0
        self._carry_signals[fx_symbol] = signals.get("carry_flow_direction", 0.0)
        return signals

    def get_composite_signal(self, fx_symbol: str, rate_diff: float = 0.0) -> dict[str, Any]:
        commodity = self.commodity_currency_signal(fx_symbol)
        equity = self.equity_currency_risk_flow(fx_symbol)
        yield_s = self.yield_currency_signal(fx_symbol)
        carry = self.carry_trade_signal(fx_symbol, rate_diff)
        all_signals = {}
        for d in [commodity, equity, yield_s, carry]:
            all_signals.update(d)
        composite = sum(v for k, v in all_signals.items() if k.endswith("_signal") and abs(v) <= 1.0)
        return {
            "composite_cross_asset_score": round(composite, 4),
            "commodity_signals": commodity,
            "equity_signals": equity,
            "yield_signals": yield_s,
            "carry_signals": carry,
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "fx_symbols": list(self._fx_returns.keys()),
            "commodities": list(self._commodity_returns.keys()),
            "equities": list(self._equity_returns.keys()),
            "yields": list(self._yield_changes.keys()),
            "vix_data_points": len(self._vix_history),
        }
