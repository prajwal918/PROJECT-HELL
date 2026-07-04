"""Pairs Trading and Statistical Arbitrage Engine.

Cointegration testing — Engle-Granger, ADF tests.
Statistical arbitrage — pairs trading with spread z-score entry/exit.
Ornstein-Uhlenbeck parameter estimation — half-life of mean reversion.
Basket arbitrage — triangular or multi-leg arbitrage detection.
Mean-reversion signals — cross-pair residual trading.
"""
from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.pairs_statarb")

PAIRS_HISTORY = int(os.getenv("PAIRS_HISTORY", "500"))
ADF_LAGS = int(os.getenv("ADF_LAGS", "1"))
ADF_CRITICAL_95 = float(os.getenv("ADF_CRITICAL_95", "-2.86"))
ZSCORE_ENTRY = float(os.getenv("ZSCORE_ENTRY", "2.0"))
ZSCORE_EXIT = float(os.getenv("ZSCORE_EXIT", "0.5"))
OU_MAX_HALFLIFE = int(os.getenv("OU_MAX_HALFLIFE", "500"))
OU_MIN_HALFLIFE = int(os.getenv("OU_MIN_HALFLIFE", "5"))

KNOWN_FX_PAIRS = [
    ("6EM6", "6BM6"),
    ("6AM6", "6NM6"),
    ("6EM6", "6SM6"),
    ("6BM6", "6AM6"),
    ("6CM6", "6SM6"),
]


class PairsEngine:
    """Cointegration-based pairs trading engine."""

    def __init__(self) -> None:
        self._price_history: dict[str, deque[float]] = {}
        self._cointegration_results: dict[tuple[str, str], dict[str, Any]] = {}
        self._active_pairs: dict[tuple[str, str], dict[str, Any]] = {}
        self._spread_history: dict[tuple[str, str], deque[float]] = {}
        self._last_prices: dict[str, float] = {}

    def update_price(self, symbol: str, mid: float) -> None:
        if symbol not in self._price_history:
            self._price_history[symbol] = deque(maxlen=PAIRS_HISTORY)
        self._price_history[symbol].append(mid)
        self._last_prices[symbol] = mid

    def adf_test(self, series: np.ndarray) -> dict[str, float]:
        n = len(series)
        if n < 30:
            return {"adf_stat": 0.0, "p_value": 1.0, "is_stationary": False}
        diff = np.diff(series)
        y = diff[1:]
        x_lagged = series[1:-1]
        diff_lagged = diff[:-1]
        X = np.column_stack([np.ones(len(y)), x_lagged, diff_lagged])
        try:
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
            residuals = y - X @ beta
            se = float(np.sqrt(np.sum(residuals ** 2) / (len(y) - X.shape[1])))
            if se > 1e-10:
                t_stat = beta[1] / se
            else:
                t_stat = 0.0
        except np.linalg.LinAlgError:
            t_stat = 0.0
        is_stationary = t_stat < ADF_CRITICAL_95
        p_value_approx = max(0.001, min(0.999, 1.0 / (1.0 + abs(t_stat))))
        return {"adf_stat": round(t_stat, 4), "p_value": round(p_value_approx, 4), "is_stationary": is_stationary}

    def engle_granger(self, y_sym: str, x_sym: str) -> dict[str, Any]:
        y = list(self._price_history.get(y_sym, []))
        x = list(self._price_history.get(x_sym, []))
        if len(y) < 50 or len(x) < 50:
            return {"cointegrated": False, "hedge_ratio": 0.0, "adf": {}}
        min_len = min(len(y), len(x))
        y_arr = np.array(y[-min_len:])
        x_arr = np.array(x[-min_len:])
        X = np.column_stack([np.ones(min_len), x_arr])
        try:
            beta = np.linalg.lstsq(X, y_arr, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"cointegrated": False, "hedge_ratio": 0.0, "adf": {}}
        intercept = beta[0]
        hedge_ratio = beta[1]
        spread = y_arr - intercept - hedge_ratio * x_arr
        adf = self.adf_test(spread)
        cointegrated = adf.get("is_stationary", False)
        result = {
            "cointegrated": cointegrated,
            "hedge_ratio": round(hedge_ratio, 6),
            "intercept": round(intercept, 6),
            "adf": adf,
            "spread_mean": round(float(np.mean(spread)), 6),
            "spread_std": round(float(np.std(spread)), 6),
            "current_spread": round(float(spread[-1]), 6),
        }
        self._cointegration_results[(y_sym, x_sym)] = result
        return result

    def estimate_half_life(self, spread: np.ndarray) -> int:
        if len(spread) < 20:
            return OU_MAX_HALFLIFE
        diff = np.diff(spread)
        X = spread[:-1].reshape(-1, 1)
        y = diff
        try:
            beta = np.linalg.lstsq(X, y, rcond=None)[0][0]
        except (np.linalg.LinAlgError, IndexError):
            return OU_MAX_HALFLIFE
        if beta >= 0:
            return OU_MAX_HALFLIFE
        halflife = int(-math.log(2) / beta)
        return max(OU_MIN_HALFLIFE, min(OU_MAX_HALFLIFE, halflife))

    def compute_spread_zscore(self, y_sym: str, x_sym: str) -> dict[str, Any]:
        key = (y_sym, x_sym)
        if key not in self._cointegration_results:
            coint = self.engle_granger(y_sym, x_sym)
            if not coint.get("cointegrated", False):
                return {"zscore": 0.0, "signal": "none", "pair": key}
        coint = self._cointegration_results.get(key, {})
        hedge = coint.get("hedge_ratio", 1.0)
        intercept = coint.get("intercept", 0.0)
        y = self._last_prices.get(y_sym, 0)
        x = self._last_prices.get(x_sym, 0)
        if y <= 0 or x <= 0:
            return {"zscore": 0.0, "signal": "none", "pair": key}
        current_spread = y - intercept - hedge * x
        spread_std = coint.get("spread_std", 1e-6)
        spread_mean = coint.get("spread_mean", 0)
        zscore = (current_spread - spread_mean) / max(1e-8, spread_std)
        if key not in self._spread_history:
            self._spread_history[key] = deque(maxlen=PAIRS_HISTORY)
        self._spread_history[key].append(current_spread)
        spread_arr = np.array(list(self._spread_history[key]))
        halflife = self.estimate_half_life(spread_arr) if len(spread_arr) >= 20 else OU_MAX_HALFLIFE
        if zscore > ZSCORE_ENTRY:
            signal = "short_spread"
        elif zscore < -ZSCORE_ENTRY:
            signal = "long_spread"
        elif abs(zscore) < ZSCORE_EXIT:
            signal = "exit"
        else:
            signal = "hold"
        return {
            "pair": key,
            "zscore": round(zscore, 2),
            "signal": signal,
            "current_spread": round(current_spread, 6),
            "halflife_ticks": halflife,
            "is_tradeable": OU_MIN_HALFLIFE <= halflife <= OU_MAX_HALFLIFE,
        }

    def scan_all_pairs(self, pairs: list[tuple[str, str]] | None = None) -> list[dict[str, Any]]:
        if pairs is None:
            pairs = KNOWN_FX_PAIRS
        results = []
        for y_sym, x_sym in pairs:
            if y_sym in self._price_history and x_sym in self._price_history:
                zs = self.compute_spread_zscore(y_sym, x_sym)
                results.append(zs)
        return results

    def get_active_signals(self) -> list[dict[str, Any]]:
        return [zs for zs in self.scan_all_pairs() if zs.get("signal") in ("long_spread", "short_spread")]

    def triangular_arb_check(self, sym_a: str, sym_b: str, sym_c: str) -> dict[str, float]:
        pa = self._last_prices.get(sym_a, 0)
        pb = self._last_prices.get(sym_b, 0)
        pc = self._last_prices.get(sym_c, 0)
        if pa <= 0 or pb <= 0 or pc <= 0:
            return {"arbitrage_pips": 0.0, "direction": "none"}
        synthetic = pa / pb
        implied = pc
        diff = synthetic - implied
        pip_sizes = {"6EM6": 0.0001, "6BM6": 0.0001, "6JM6": 0.01, "6AM6": 0.0001, "6CM6": 0.0001, "6NM6": 0.0001, "6SM6": 0.0001}
        pip = pip_sizes.get(sym_c, 0.0001)
        arb_pips = abs(diff) / pip if pip > 0 else 0
        return {"arbitrage_pips": round(arb_pips, 2), "direction": "buy_implied" if diff > 0 else "sell_implied"}

    def get_status(self) -> dict[str, Any]:
        return {
            "symbols": list(self._price_history.keys()),
            "cointegrated_pairs": sum(1 for r in self._cointegration_results.values() if r.get("cointegrated")),
            "active_signals": len(self.get_active_signals()),
        }
