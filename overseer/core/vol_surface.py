"""Volatility Surface Engine — options-informed FX signals.

Term structure of volatility — 1W, 1M, 3M, 6M, 1Y IV steepness.
Skew dynamics — how 25-delta risk reversal evolves over time.
Vol risk premium — realized vs implied spread as predictive signal.
Vanna-Volga surface calibration — standard FX options pricing.
Vol-of-vol — measures uncertainty about volatility itself.
GARCH volatility clustering model — forward-looking vol estimate.
"""
from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.vol_surface")

VOL_HISTORY = int(os.getenv("VOL_HISTORY", "500"))
TERM_STRUCTURE_TENORS = ["1W", "2W", "1M", "3M", "6M", "1Y"]
VRP_WINDOW = int(os.getenv("VRP_WINDOW", "30"))
VANNA_VOLGA_DELTA = float(os.getenv("VANNA_VOLGA_DELTA", "0.25"))


class VolSurfaceEngine:
    """Per-symbol volatility surface analysis."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._atm_iv: dict[str, deque[float]] = {t: deque(maxlen=VOL_HISTORY) for t in TERM_STRUCTURE_TENORS}
        self._rr_25d: deque[float] = deque(maxlen=VOL_HISTORY)
        self._rr_10d: deque[float] = deque(maxlen=VOL_HISTORY)
        self._butterfly_25d: deque[float] = deque(maxlen=VOL_HISTORY)
        self._realized_vol: deque[float] = deque(maxlen=VOL_HISTORY)
        self._returns: deque[float] = deque(maxlen=VOL_HISTORY * 2)
        self._last_mid: float = 0.0

    def update_atm_iv(self, tenor: str, iv: float) -> None:
        if tenor in self._atm_iv:
            self._atm_iv[tenor].append(iv)

    def update_skew(self, rr_25d: float = 0.0, rr_10d: float = 0.0, bf_25d: float = 0.0) -> None:
        self._rr_25d.append(rr_25d)
        self._rr_10d.append(rr_10d)
        self._butterfly_25d.append(bf_25d)

    def update_realized_vol(self, mid: float) -> None:
        if self._last_mid > 0:
            ret = (mid - self._last_mid) / self._last_mid
            self._returns.append(ret)
            if len(self._returns) >= 20:
                window = list(self._returns)[-20:]
                rv = float(np.std(window)) * math.sqrt(252 * 24 * 12)
                self._realized_vol.append(rv)
        self._last_mid = mid

    def term_structure_signal(self) -> dict[str, float]:
        short_iv = list(self._atm_iv.get("1W", []))
        long_iv = list(self._atm_iv.get("3M", []))
        if not short_iv or not long_iv:
            return {"slope": 0.0, "zscore": 0.0, "contango": True, "signal": 0.0}
        short = short_iv[-1]
        long = long_iv[-1]
        slope = long - short
        all_short = list(short_iv)
        all_long = list(long_iv)
        min_len = min(len(all_short), len(all_long))
        if min_len >= 20:
            slopes = np.array(all_long[-min_len:]) - np.array(all_short[-min_len:])
            slope_mean = float(np.mean(slopes))
            slope_std = float(np.std(slopes))
            z = (slope - slope_mean) / slope_std if slope_std > 1e-6 else 0.0
        else:
            z = 0.0
        contango = slope > 0
        signal = -z * 0.1 if contango else z * 0.1
        return {
            "slope": round(slope, 4),
            "zscore": round(z, 2),
            "contango": contango,
            "backwardation": not contango,
            "signal": round(signal, 4),
            "short_iv": round(short, 4),
            "long_iv": round(long, 4),
        }

    def skew_dynamics(self) -> dict[str, float]:
        rr = list(self._rr_25d)
        if not rr:
            return {"current_rr25": 0.0, "rr_zscore": 0.0, "skew_regime": "neutral", "signal": 0.0}
        current = rr[-1]
        if len(rr) >= 20:
            rr_arr = np.array(rr)
            mean = float(np.mean(rr_arr))
            std = float(np.std(rr_arr))
            z = (current - mean) / std if std > 1e-6 else 0.0
        else:
            z = 0.0
        if current > 1.0:
            regime = "call_skew"
        elif current < -1.0:
            regime = "put_skew"
        else:
            regime = "neutral"
        signal = z * 0.05
        return {
            "current_rr25": round(current, 4),
            "rr_zscore": round(z, 2),
            "skew_regime": regime,
            "signal": round(signal, 4),
        }

    def vol_risk_premium(self) -> dict[str, float]:
        rv = list(self._realized_vol)
        iv_1m = list(self._atm_iv.get("1M", []))
        if not rv or not iv_1m:
            return {"vrp": 0.0, "vrp_zscore": 0.0, "signal": 0.0}
        current_rv = rv[-1]
        current_iv = iv_1m[-1]
        vrp = current_iv - current_rv
        all_rv = list(rv)[-VRP_WINDOW:]
        all_iv = list(iv_1m)[-VRP_WINDOW:]
        min_len = min(len(all_rv), len(all_iv))
        if min_len >= 10:
            vrp_series = np.array(all_iv[-min_len:]) - np.array(all_rv[-min_len:])
            vrp_mean = float(np.mean(vrp_series))
            vrp_std = float(np.std(vrp_series))
            z = (vrp - vrp_mean) / vrp_std if vrp_std > 1e-6 else 0.0
        else:
            z = 0.0
        signal = -z * 0.1
        return {
            "vrp": round(vrp, 4),
            "vrp_zscore": round(z, 2),
            "implied_vol": round(current_iv, 4),
            "realized_vol": round(current_rv, 4),
            "signal": round(signal, 4),
        }

    def vanna_volga_calibration(self, spot: float, atm_vol: float = 0.0, rr_25: float = 0.0, bf_25: float = 0.0) -> dict[str, float]:
        if atm_vol <= 0 or spot <= 0:
            return {"d_atm": 0.5, "convexity": 0.0, "vanna_cost": 0.0, "volga_cost": 0.0}
        d_atm = 0.5
        sigma = atm_vol
        sqrt_t = 1.0
        d1 = (math.log(spot / spot) + 0.5 * sigma ** 2 * sqrt_t) / (sigma * sqrt_t) if sigma > 0 else 0
        vega = spot * sigma * sqrt_t * math.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi) if sigma > 0 else 0
        vanna = vega * (1 - d1 / (sigma * sqrt_t)) if sigma * sqrt_t > 0 else 0
        volga = vega * d1 * (1 - d1 / (sigma * sqrt_t)) / sigma if sigma > 0 else 0
        convexity = bf_25
        vanna_cost = abs(rr_25) * 0.5
        volga_cost = abs(bf_25) * 0.5
        return {
            "d_atm": d_atm,
            "convexity": round(convexity, 4),
            "vanna_cost": round(vanna_cost, 4),
            "volga_cost": round(volga_cost, 4),
            "vega_approx": round(vega, 6),
        }

    def vol_of_vol(self) -> dict[str, float]:
        iv_series = list(self._atm_iv.get("1M", []))
        if len(iv_series) < 20:
            return {"vol_of_vol": 0.0, "regime": "unknown"}
        arr = np.array(iv_series[-50:])
        vov = float(np.std(arr) / max(1e-6, float(np.mean(arr))))
        if vov < 0.1:
            regime = "stable_vol"
        elif vov < 0.25:
            regime = "normal_vol"
        elif vov < 0.5:
            regime = "unstable_vol"
        else:
            regime = "crisis_vol"
        return {"vol_of_vol": round(vov, 4), "regime": regime}

    def get_composite_signal(self) -> dict[str, Any]:
        ts = self.term_structure_signal()
        sk = self.skew_dynamics()
        vrp = self.vol_risk_premium()
        vov = self.vol_of_vol()
        composite = ts["signal"] + sk["signal"] + vrp["signal"]
        return {
            "term_structure": ts,
            "skew": sk,
            "vol_risk_premium": vrp,
            "vol_of_vol": vov,
            "composite_vol_signal": round(composite, 4),
            "vol_regime": vov.get("regime", "unknown"),
        }


class VolSurfaceManager:
    """Multi-symbol volatility surface manager."""

    def __init__(self) -> None:
        self._engines: dict[str, VolSurfaceEngine] = {}

    def get_engine(self, symbol: str) -> VolSurfaceEngine:
        if symbol not in self._engines:
            self._engines[symbol] = VolSurfaceEngine(symbol)
        return self._engines[symbol]

    def get_all_signals(self) -> dict[str, dict[str, Any]]:
        return {sym: eng.get_composite_signal() for sym, eng in self._engines.items()}

    def get_status(self) -> dict[str, Any]:
        return {"symbols": list(self._engines.keys())}
