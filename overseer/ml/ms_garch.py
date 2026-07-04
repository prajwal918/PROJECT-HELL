from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any, Dict, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger("overseer.ms_garch")

_ENABLED = os.getenv("MS_GARCH_ENABLED", "true").lower() == "true"
_OMEGA_LOW = float(os.getenv("MS_GARCH_OMEGA_LOW", "0.00001"))
_ALPHA_LOW = float(os.getenv("MS_GARCH_ALPHA_LOW", "0.05"))
_BETA_LOW = float(os.getenv("MS_GARCH_BETA_LOW", "0.90"))
_OMEGA_HIGH = float(os.getenv("MS_GARCH_OMEGA_HIGH", "0.00005"))
_ALPHA_HIGH = float(os.getenv("MS_GARCH_ALPHA_HIGH", "0.10"))
_BETA_HIGH = float(os.getenv("MS_GARCH_BETA_HIGH", "0.85"))
_MAX_RETURNS = int(os.getenv("MS_GARCH_MAX_RETURNS", "500"))
_MIN_RETURNS = int(os.getenv("MS_GARCH_MIN_RETURNS", "20"))
_FLOOR = float(os.getenv("MS_GARCH_FLOOR", "1e-8"))


class _GARCH11:
    def __init__(self, omega: float, alpha: float, beta: float) -> None:
        self._omega = omega
        self._alpha = alpha
        self._beta = beta
        self._var = omega / (1.0 - alpha - beta) if (1.0 - alpha - beta) > 0.001 else omega

    def update(self, ret: float) -> float:
        self._var = self._omega + self._alpha * ret * ret + self._beta * self._var
        self._var = max(self._var, _FLOOR)
        return self._var

    def forecast(self) -> float:
        return math.sqrt(self._var)


class MSGARCH:
    def __init__(self) -> None:
        self._models: Dict[str, Dict[str, _GARCH11]] = {}
        self._returns: Dict[str, deque] = {}
        self._last_regime: Dict[str, str] = {}
        self._forecast_cache: Dict[str, Dict[str, float]] = {}

    def _init_symbol(self, symbol: str) -> None:
        if symbol not in self._models:
            self._models[symbol] = {
                "low": _GARCH11(_OMEGA_LOW, _ALPHA_LOW, _BETA_LOW),
                "high": _GARCH11(_OMEGA_HIGH, _ALPHA_HIGH, _BETA_HIGH),
            }
            self._returns[symbol] = deque(maxlen=_MAX_RETURNS)
            self._last_regime[symbol] = "low"

    def update_returns(self, symbol: str, ret: float, regime: str) -> None:
        if not _ENABLED:
            return
        self._init_symbol(symbol)
        self._returns[symbol].append(ret)
        self._last_regime[symbol] = regime
        active = "high" if regime in ("risk_off", "high_vol", "volatile") else "low"
        inactive = "low" if active == "high" else "high"
        self._models[symbol][active].update(ret)
        if len(self._returns[symbol]) > 1:
            self._models[symbol][inactive].update(ret)

    def forecast_vol(self, symbol: str, regime: Optional[str] = None) -> float:
        if not _ENABLED:
            return 0.0
        self._init_symbol(symbol)
        if regime is None:
            regime = self._last_regime.get(symbol, "low")
        active = "high" if regime in ("risk_off", "high_vol", "volatile") else "low"
        if symbol not in self._forecast_cache:
            self._forecast_cache[symbol] = {}
        forecast = self._models[symbol][active].forecast()
        self._forecast_cache[symbol][active] = forecast
        return forecast

    def get_regime_vol(self, symbol: str) -> Dict[str, float]:
        self._init_symbol(symbol)
        result = {}
        for key in ("low", "high"):
            result[key] = self._models[symbol][key].forecast()
        return result

    def get_current_regime(self, symbol: str) -> str:
        return self._last_regime.get(symbol, "low")

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": _ENABLED,
            "symbols": list(self._models.keys()),
            "last_regime": dict(self._last_regime),
            "forecasts": {k: v for k, v in self._forecast_cache.items()},
        }


ms_garch = MSGARCH()
