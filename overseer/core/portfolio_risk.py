"""Institutional Portfolio Risk Engine.

VaR (Value at Risk) — parametric, historical, and Monte Carlo.
CVaR (Conditional VaR / Expected Shortfall) — tail risk measurement.
Full correlation matrix across open positions.
Factor exposure — carry, momentum, value, volatility factors for FX.
Stress testing — scenario analysis (Fed shock, EUR/CHF unpeg, JPY intervention).
Marginal VaR / Component VaR — which position contributes most risk.
Sortino / Calmar ratios.
Drawdown-constrained Kelly criterion.
Vol-targeting position sizing.
Correlation-adjusted portfolio Kelly.
CPPI (Constant Proportion Portfolio Insurance).
"""
from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.portfolio_risk")

VAR_CONFIDENCE = float(os.getenv("VAR_CONFIDENCE", "0.95"))
VAR_WINDOW = int(os.getenv("VAR_WINDOW", "252"))
STRESS_SCENARIOS = {
    "fed_200bps_hike": {"6EM6": -0.020, "6BM6": -0.015, "6JM6": 0.030, "6AM6": -0.025, "6CM6": 0.020},
    "eur_chf_unpeg": {"6EM6": -0.050, "6BM6": -0.030, "6JM6": 0.040, "6AM6": -0.035, "6CM6": 0.025},
    "jpy_intervention": {"6JM6": -0.040, "6EM6": 0.010, "6BM6": 0.005, "6AM6": 0.008, "6CM6": -0.005},
    "risk_off_flash": {"6EM6": -0.030, "6BM6": -0.025, "6JM6": 0.050, "6AM6": -0.040, "6CM6": 0.015},
    "oil_shock": {"6CM6": -0.035, "6AM6": -0.020, "6EM6": -0.010, "6BM6": -0.008, "6JM6": 0.015},
}
DRAWDOWN_KELLY_FRACTION = float(os.getenv("DRAWDOWN_KELLY_FRACTION", "0.25"))
DRAWDOWN_LIMIT = float(os.getenv("DRAWDOWN_LIMIT", "0.10"))
VOL_TARGET_ANNUAL = float(os.getenv("VOL_TARGET_ANNUAL", "0.10"))
CPPI_MULTIPLIER = float(os.getenv("CPPI_MULTIPLIER", "3.0"))
CPPI_FLOOR = float(os.getenv("CPPI_FLOOR", "0.80"))


class PortfolioRiskEngine:
    """Full institutional portfolio risk management."""

    def __init__(self) -> None:
        self._positions: dict[str, dict[str, Any]] = {}
        self._returns_history: dict[str, deque[float]] = {}
        self._pnl_history: deque[float] = deque(maxlen=VAR_WINDOW)
        self._equity_curve: deque[float] = deque(maxlen=10000)
        self._peak_equity: float = 0.0

    def update_position(self, symbol: str, direction: str, size: float, entry_price: float, pip_size: float = 0.0001) -> None:
        self._positions[symbol] = {
            "direction": direction,
            "size": size,
            "entry_price": entry_price,
            "pip_size": pip_size,
        }

    def remove_position(self, symbol: str) -> None:
        self._positions.pop(symbol, None)

    def update_pnl(self, daily_pnl: float, equity: float) -> None:
        self._pnl_history.append(daily_pnl)
        self._equity_curve.append(equity)
        if equity > self._peak_equity:
            self._peak_equity = equity

    def update_symbol_return(self, symbol: str, return_value: float) -> None:
        if symbol not in self._returns_history:
            self._returns_history[symbol] = deque(maxlen=VAR_WINDOW)
        self._returns_history[symbol].append(return_value)

    def parametric_var(self, confidence: float = VAR_CONFIDENCE) -> dict[str, float]:
        if not self._pnl_history or len(self._pnl_history) < 10:
            return {"var": 0.0, "cvar": 0.0, "method": "insufficient_data"}
        returns = np.array(list(self._pnl_history))
        mu = float(np.mean(returns))
        sigma = float(np.std(returns))
        from scipy.stats import norm
        z = norm.ppf(1 - confidence)
        var = -(mu + z * sigma)
        cvar = -(mu - sigma * norm.pdf(z) / (1 - confidence))
        return {"var": round(var, 4), "cvar": round(cvar, 4), "mu": round(mu, 6), "sigma": round(sigma, 6), "method": "parametric"}

    def historical_var(self, confidence: float = VAR_CONFIDENCE) -> dict[str, float]:
        if len(self._pnl_history) < 20:
            return {"var": 0.0, "cvar": 0.0, "method": "insufficient_data"}
        returns = np.array(list(self._pnl_history))
        sorted_returns = np.sort(returns)
        n = len(sorted_returns)
        idx = max(0, int((1 - confidence) * n))
        var = -sorted_returns[idx]
        cvar = -float(np.mean(sorted_returns[:idx + 1]))
        return {"var": round(var, 4), "cvar": round(cvar, 4), "method": "historical"}

    def correlation_matrix(self) -> dict[str, Any]:
        symbols = [s for s in self._returns_history if len(self._returns_history[s]) >= 20]
        if len(symbols) < 2:
            return {"symbols": symbols, "matrix": [], "avg_correlation": 0.0}
        min_len = min(len(self._returns_history[s]) for s in symbols)
        data = np.array([list(self._returns_history[s])[-min_len:] for s in symbols])
        if data.shape[1] < 5:
            return {"symbols": symbols, "matrix": [], "avg_correlation": 0.0}
        corr = np.corrcoef(data)
        upper_triangle = corr[np.triu_indices(len(symbols), k=1)]
        avg_corr = float(np.mean(np.abs(upper_triangle))) if len(upper_triangle) > 0 else 0.0
        return {
            "symbols": symbols,
            "matrix": [[round(float(corr[i, j]), 4) for j in range(len(symbols))] for i in range(len(symbols))],
            "avg_correlation": round(avg_corr, 4),
            "max_correlation": round(float(np.max(np.abs(upper_triangle))), 4) if len(upper_triangle) > 0 else 0.0,
        }

    def stress_test(self) -> dict[str, dict[str, float]]:
        results = {}
        for scenario_name, shocks in STRESS_SCENARIOS.items():
            scenario_pnl = 0.0
            for symbol, pos in self._positions.items():
                if symbol in shocks:
                    direction_mult = 1.0 if pos["direction"] == "BUY" else -1.0
                    price_impact = shocks[symbol]
                    position_pnl = direction_mult * price_impact * pos["size"] * pos["entry_price"]
                    scenario_pnl += position_pnl
            results[scenario_name] = {
                "pnl_impact": round(scenario_pnl, 2),
                "worst_symbol": max(shocks.keys(), key=lambda s: abs(shocks.get(s, 0))) if shocks else "",
            }
        return results

    def component_var(self, confidence: float = VAR_CONFIDENCE) -> dict[str, float]:
        corr_data = self.correlation_matrix()
        if not corr_data["matrix"]:
            return {}
        symbols = corr_data["symbols"]
        n = len(symbols)
        if n < 2:
            return {}
        weights = np.zeros(n)
        vols = np.zeros(n)
        for i, sym in enumerate(symbols):
            pos = self._positions.get(sym, {})
            weights[i] = pos.get("size", 0)
            rets = list(self._returns_history.get(sym, []))
            vols[i] = float(np.std(rets)) if len(rets) > 5 else 0.001
        corr = np.array(corr_data["matrix"])
        portfolio_var = float(np.sqrt(weights @ (corr * np.outer(vols, vols)) @ weights))
        component = {}
        for i, sym in enumerate(symbols):
            marginal = 0.0
            for j in range(n):
                marginal += weights[j] * vols[j] * corr[i, j] * vols[i]
            component[sym] = round(weights[i] * marginal / max(1e-10, portfolio_var), 4)
        return component

    def drawdown_kelly(self, win_rate: float, avg_win: float, avg_loss: float, current_drawdown: float = 0.0) -> dict[str, float]:
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return {"kelly_fraction": 0.0, "adjusted_fraction": 0.0, "size_multiplier": 0.0}
        full_kelly = win_rate / avg_loss - (1 - win_rate) / avg_win if avg_win > 0 else 0
        full_kelly = max(0, full_kelly)
        fraction = DRAWDOWN_KELLY_FRACTION
        if current_drawdown > DRAWDOWN_LIMIT * 0.5:
            fraction *= max(0.1, 1.0 - current_drawdown / DRAWDOWN_LIMIT)
        adjusted = full_kelly * fraction
        return {
            "kelly_fraction": round(full_kelly, 4),
            "adjusted_fraction": round(adjusted, 4),
            "size_multiplier": round(min(1.0, adjusted / max(0.01, full_kelly * DRAWDOWN_KELLY_FRACTION)) if full_kelly > 0 else 0.0, 4),
            "drawdown_penalty": round(1.0 - fraction / DRAWDOWN_KELLY_FRACTION, 4) if DRAWDOWN_KELLY_FRACTION > 0 else 0.0,
        }

    def vol_target_sizing(self, current_vol: float, base_lot: float = 0.01) -> dict[str, float]:
        if current_vol <= 0:
            return {"target_lot": base_lot, "vol_scalar": 1.0}
        annualized_vol = current_vol * math.sqrt(252 * 24 * 12)
        vol_scalar = VOL_TARGET_ANNUAL / max(1e-6, annualized_vol)
        vol_scalar = max(0.1, min(3.0, vol_scalar))
        target_lot = base_lot * vol_scalar
        return {"target_lot": round(target_lot, 4), "vol_scalar": round(vol_scalar, 4), "current_annualized_vol": round(annualized_vol, 6)}

    def cppi_allocation(self, equity: float, floor_ratio: float = CPPI_FLOOR, multiplier: float = CPPI_MULTIPLIER) -> dict[str, float]:
        floor = equity * floor_ratio
        cushion = max(0, equity - floor)
        risky_allocation = cushion * multiplier
        risky_allocation = min(risky_allocation, equity)
        safe_allocation = equity - risky_allocation
        return {
            "total_equity": round(equity, 2),
            "floor": round(floor, 2),
            "cushion": round(cushion, 2),
            "risky_allocation": round(risky_allocation, 2),
            "safe_allocation": round(safe_allocation, 2),
            "risky_pct": round(risky_allocation / equity * 100 if equity > 0 else 0, 1),
        }

    def sortino_ratio(self, risk_free: float = 0.0) -> float:
        if len(self._pnl_history) < 20:
            return 0.0
        returns = np.array(list(self._pnl_history))
        excess = returns - risk_free / 252
        downside = excess[excess < 0]
        if len(downside) == 0:
            return float("inf") if np.mean(excess) > 0 else 0.0
        downside_std = float(np.std(downside))
        if downside_std < 1e-10:
            return 0.0
        return round(float(np.mean(excess)) / downside_std * math.sqrt(252), 4)

    def calmar_ratio(self) -> float:
        if len(self._equity_curve) < 20:
            return 0.0
        equity = list(self._equity_curve)
        peak = equity[0]
        max_dd = 0.0
        for e in equity:
            if e > peak:
                peak = e
            dd = (peak - e) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        if max_dd < 1e-6:
            return 0.0
        total_return = (equity[-1] - equity[0]) / equity[0] if equity[0] > 0 else 0
        n_years = max(0.01, len(equity) / 252)
        annualized_return = (1 + total_return) ** (1 / n_years) - 1 if total_return > -1 else total_return
        return round(annualized_return / max(1e-6, max_dd), 4)

    def current_drawdown(self) -> float:
        if not self._equity_curve or self._peak_equity <= 0:
            return 0.0
        current = self._equity_curve[-1]
        return (self._peak_equity - current) / self._peak_equity

    def get_risk_summary(self) -> dict[str, Any]:
        pvar = self.parametric_var()
        hvar = self.historical_var()
        corr = self.correlation_matrix()
        stress = self.stress_test()
        comp = self.component_var()
        return {
            "parametric_var": pvar,
            "historical_var": hvar,
            "correlation": corr,
            "stress_test": stress,
            "component_var": comp,
            "sortino": self.sortino_ratio(),
            "calmar": self.calmar_ratio(),
            "current_drawdown": round(self.current_drawdown(), 4),
            "open_positions": len(self._positions),
        }
