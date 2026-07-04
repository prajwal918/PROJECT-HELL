from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger("overseer.es_risk")

_ENABLED = os.getenv("ES_RISK_ENABLED", "true").lower() == "true"
_CONFIDENCE = float(os.getenv("ES_CONFIDENCE", "0.95"))
_MAX_PNL = int(os.getenv("ES_MAX_PNL_HISTORY", "1000"))
_MIN_PNL = int(os.getenv("ES_MIN_PNL_HISTORY", "30"))
_RISK_DIVISOR = float(os.getenv("ES_RISK_DIVISOR", "3.0"))
_FLOOR_ES = float(os.getenv("ES_FLOOR_ES", "0.001"))


class ESRisk:
    def __init__(self) -> None:
        self._pnl_history: deque = deque(maxlen=_MAX_PNL)
        self._last_es: float = 0.0
        self._last_var: float = 0.0

    def update_pnl(self, pnl: float) -> None:
        if not _ENABLED:
            return
        self._pnl_history.append(pnl)

    def compute_es(self, confidence: float = 0.95) -> float:
        if not _ENABLED:
            return 0.0
        if len(self._pnl_history) < _MIN_PNL:
            LOGGER.debug("ES: only %d PnL samples, need %d", len(self._pnl_history), _MIN_PNL)
            return self._last_es
        arr = np.array(self._pnl_history, dtype=np.float64)
        sorted_arr = np.sort(arr)
        n = len(sorted_arr)
        cutoff_idx = max(1, int(n * (1.0 - confidence)))
        tail = sorted_arr[:cutoff_idx]
        if len(tail) == 0:
            return self._last_es
        es = float(-np.mean(tail))
        var = float(-sorted_arr[cutoff_idx - 1])
        self._last_es = max(es, _FLOOR_ES)
        self._last_var = max(var, _FLOOR_ES)
        LOGGER.debug("ES_%.0f: %.4f, VaR_%.0f: %.4f (n=%d)", confidence * 100, self._last_es, confidence * 100, self._last_var, n)
        return self._last_es

    def compute_var(self, confidence: float = 0.95) -> float:
        if not _ENABLED:
            return 0.0
        if len(self._pnl_history) < _MIN_PNL:
            return self._last_var
        arr = np.array(self._pnl_history, dtype=np.float64)
        sorted_arr = np.sort(arr)
        n = len(sorted_arr)
        cutoff_idx = max(1, int(n * (1.0 - confidence)))
        var = float(-sorted_arr[cutoff_idx - 1])
        self._last_var = max(var, _FLOOR_ES)
        return self._last_var

    def get_max_position_size(self, daily_risk_budget: float) -> float:
        if not _ENABLED:
            return 1.0
        es = self.compute_es(_CONFIDENCE)
        if es <= _FLOOR_ES:
            return 1.0
        max_loss_per_unit = es / _RISK_DIVISOR
        if max_loss_per_unit <= 0:
            return 0.0
        max_units = daily_risk_budget / max_loss_per_unit
        max_units = max(0.0, min(max_units, 100.0))
        return max_units

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": _ENABLED,
            "n_pnl_samples": len(self._pnl_history),
            "last_es": round(self._last_es, 6),
            "last_var": round(self._last_var, 6),
            "confidence": _CONFIDENCE,
        }


es_risk = ESRisk()
