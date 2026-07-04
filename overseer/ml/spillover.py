from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any, Dict, List

import numpy as np

LOGGER = logging.getLogger("overseer.spillover")

_ENABLED = os.getenv("SPILLOVER_INDEX_ENABLED", "true").lower() == "true"
_WINDOW = int(os.getenv("SPILLOVER_WINDOW", "100"))
_MIN_RETURNS = int(os.getenv("SPILLOVER_MIN_RETURNS", "50"))
_HIGH_THRESHOLD = float(os.getenv("SPILLOVER_HIGH_THRESHOLD", "0.65"))
_LOW_THRESHOLD = float(os.getenv("SPILLOVER_LOW_THRESHOLD", "0.35"))
_HIGH_WEIGHT = float(os.getenv("SPILLOVER_HIGH_WEIGHT", "1.20"))
_LOW_WEIGHT = float(os.getenv("SPILLOVER_LOW_WEIGHT", "0.70"))
_MAX_SYMBOLS = int(os.getenv("SPILLOVER_MAX_SYMBOLS", "20"))


class SpilloverIndex:
    def __init__(self) -> None:
        self._returns: Dict[str, deque] = {}
        self._index: float = 0.0
        self._directional: Dict[str, float] = {}
        self._last_compute_tick: int = 0

    def update_returns(self, symbol: str, ret: float) -> None:
        if not _ENABLED:
            return
        if symbol not in self._returns:
            if len(self._returns) >= _MAX_SYMBOLS:
                return
            self._returns[symbol] = deque(maxlen=_WINDOW)
        self._returns[symbol].append(ret)

    def compute_index(self) -> float:
        if not _ENABLED:
            return 0.0
        if len(self._returns) < 2:
            return 0.0
        symbols = sorted(self._returns.keys())
        min_len = min(len(self._returns[s]) for s in symbols)
        if min_len < _MIN_RETURNS:
            return self._index
        arrays = []
        for s in symbols:
            data = list(self._returns[s])
            arrays.append(np.array(data[-min_len:], dtype=np.float64))
        matrix = np.column_stack(arrays)
        n = matrix.shape[1]
        if n < 2:
            return self._index
        try:
            corr = np.corrcoef(matrix, rowvar=False)
            if corr.shape[0] < 2:
                return self._index
            abs_corr = np.abs(corr)
            np.fill_diagonal(abs_corr, 0.0)
            total_off = np.sum(abs_corr)
            total_all = total_off + n
            if total_all == 0:
                return self._index
            self._index = float(total_off / total_all)
            for i, s in enumerate(symbols):
                directional_from = float(np.sum(abs_corr[i, :]) / (total_all if total_all > 0 else 1.0))
                self._directional[s] = directional_from
        except Exception as exc:
            LOGGER.warning("Spillover compute failed: %s", exc)
            return self._index
        LOGGER.debug("Spillover index: %.4f (%d symbols)", self._index, len(symbols))
        return self._index

    def get_cross_pair_weight(self) -> float:
        if not _ENABLED:
            return 1.0
        if self._index > _HIGH_THRESHOLD:
            return _HIGH_WEIGHT
        if self._index < _LOW_THRESHOLD:
            return _LOW_WEIGHT
        t = (self._index - _LOW_THRESHOLD) / (_HIGH_THRESHOLD - _LOW_THRESHOLD)
        return _LOW_WEIGHT + t * (_HIGH_WEIGHT - _LOW_WEIGHT)

    def get_directional_spillover(self, symbol: str) -> float:
        return self._directional.get(symbol, 0.0)

    def get_index(self) -> float:
        return self._index

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": _ENABLED,
            "index": round(self._index, 4),
            "cross_pair_weight": round(self.get_cross_pair_weight(), 4),
            "n_symbols": len(self._returns),
            "directional": {k: round(v, 4) for k, v in self._directional.items()},
        }


spillover_index = SpilloverIndex()
