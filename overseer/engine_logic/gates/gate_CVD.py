from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_CVD")


class GateCVD(BaseGate):
    gate_name = "gate_CVD"
    priority = 28

    def evaluate(self, tick: dict[str, Any]) -> bool:
        cvd = float(tick.get("cumulative_delta", 0.0))
        direction = tick.get("direction", "BUY")
        mid_now = (float(tick.get("bid", 0)) + float(tick.get("ask", 0))) / 2.0
        prev_mid = float(tick.get("prev_mid", 0.0))

        price_making_lower_lows = mid_now < prev_mid and prev_mid > 0
        price_making_higher_highs = mid_now > prev_mid and prev_mid > 0
        cvd_making_higher_lows = cvd > 0
        cvd_making_lower_highs = cvd < 0

        if direction == "BUY":
            if price_making_higher_highs and cvd_making_higher_lows:
                return True
            if price_making_lower_lows and cvd_making_higher_lows:
                return True

        if direction == "SELL":
            if price_making_lower_lows and cvd_making_lower_highs:
                return True
            if price_making_higher_highs and cvd_making_lower_highs:
                return True

        if direction == "BUY" and cvd >= 0:
            return True
        if direction == "SELL" and cvd <= 0:
            return True

        return False
