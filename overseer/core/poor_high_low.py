import os
import logging
from collections import deque
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_ENABLED = os.getenv("POOR_HIGH_LOW_ENABLED", "true").lower() == "true"
_SINGLE_TICK_TOLERANCE = int(os.getenv("POOR_HIGH_LOW_TICK_TOLERANCE", "2"))
_PROXIMITY_PIPS = float(os.getenv("POOR_HIGH_LOW_PROXIMITY_PIPS", "3.0"))
_THRESHOLD_REDUCE = float(os.getenv("POOR_HIGH_LOW_THRESHOLD_REDUCE", "0.03"))


class PoorHighLow:
    def __init__(self):
        self._session_extremes = {}
        self._poor_levels = {}

    def on_tick(self, symbol, price, tick_count, pip_size, session_start_tick):
        if symbol not in self._session_extremes:
            self._session_extremes[symbol] = {
                "high": price, "low": price,
                "high_tick_count": 0, "low_tick_count": 0,
                "session_start": session_start_tick or tick_count,
            }
        s = self._session_extremes[symbol]
        if price > s["high"]:
            s["high"] = price
            s["high_tick_count"] = 1
        elif abs(price - s["high"]) < pip_size * 0.1:
            s["high_tick_count"] += 1
        if price < s["low"]:
            s["low"] = price
            s["low_tick_count"] = 1
        elif abs(price - s["low"]) < pip_size * 0.1:
            s["low_tick_count"] += 1

    def detect_poor_levels(self, symbol, pip_size):
        if not _ENABLED:
            return []
        s = self._session_extremes.get(symbol)
        if s is None:
            return []
        levels = []
        if s["high_tick_count"] <= _SINGLE_TICK_TOLERANCE:
            levels.append({"type": "POOR_HIGH", "price": s["high"], "confidence": 1.0 - s["high_tick_count"] / 5.0})
        if s["low_tick_count"] <= _SINGLE_TICK_TOLERANCE:
            levels.append({"type": "POOR_LOW", "price": s["low"], "confidence": 1.0 - s["low_tick_count"] / 5.0})
        self._poor_levels[symbol] = levels
        return levels

    def get_threshold_reduction(self, symbol, current_price, pip_size):
        if not _ENABLED:
            return 0.0
        levels = self._poor_levels.get(symbol, [])
        for lvl in levels:
            if abs(current_price - lvl["price"]) / pip_size < _PROXIMITY_PIPS:
                return _THRESHOLD_REDUCE
        return 0.0

    def on_new_session(self, symbol):
        self._session_extremes.pop(symbol, None)
        self._poor_levels.pop(symbol, None)


poor_high_low = PoorHighLow()
