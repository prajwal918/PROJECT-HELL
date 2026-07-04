from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_DXY_TREND")

_DXY_STRENGTH_THRESHOLD = float(__import__("os").getenv("DXY_STRENGTH_THRESHOLD", "0.3"))


class GateDxyTrend(BaseGate):
    gate_name = "gate_DXY_TREND"
    priority = 38

    _quote_is_usd = {"6E", "6B", "6A", "6N"}
    _base_is_usd = {"6J", "6C", "6S"}

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")
        symbol = tick.get("symbol", "")

        dxy_trend = tick.get("dxy_trend", "neutral")
        if dxy_trend == "neutral":
            return False

        dxy_strength = 0.0
        try:
            _dxy_calc = __import__("core.dxy_calculator", fromlist=["DXYCalculator"])
        except Exception:
            return False

        root = symbol[:2] if len(symbol) >= 2 else ""

        dxy_bullish = dxy_trend in ("bullish", "rising", "strong_bullish")
        dxy_bearish = dxy_trend in ("bearish", "falling", "strong_bearish")

        if not dxy_bullish and not dxy_bearish:
            return False

        if direction == "BUY":
            if root in self._quote_is_usd and dxy_bearish:
                return True
            if root in self._base_is_usd and dxy_bullish:
                return True

        if direction == "SELL":
            if root in self._quote_is_usd and dxy_bullish:
                return True
            if root in self._base_is_usd and dxy_bearish:
                return True

        return False
