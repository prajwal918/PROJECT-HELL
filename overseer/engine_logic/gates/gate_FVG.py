from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_FVG")

_FVG_MIN_GAP_PIPS = float(__import__("os").getenv("FVG_MIN_GAP_PIPS", "2.0"))
_FVG_LOOKBACK_CANDLES = int(__import__("os").getenv("FVG_LOOKBACK_CANDLES", "10"))


class GateFVG(BaseGate):
    gate_name = "gate_FVG"
    priority = 30

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")
        candles = tick.get("_candles_15m", [])
        if not candles or len(candles) < 3:
            return False
        pip_size = float(tick.get("pip_size", 0.0001))
        min_gap = _FVG_MIN_GAP_PIPS * pip_size
        lookback = min(_FVG_LOOKBACK_CANDLES, len(candles))

        for i in range(max(0, len(candles) - lookback), len(candles) - 2):
            c1 = candles[i]
            c3 = candles[i + 2]
            if not isinstance(c1, dict) or not isinstance(c3, dict):
                continue
            c1_low = float(c1.get("low", 0))
            c3_high = float(c3.get("high", 0))
            c1_high = float(c1.get("high", 0))
            c3_low = float(c3.get("low", 0))
            c2 = candles[i + 1]
            c2_body_low = float(c2.get("low", 0))
            c2_body_high = float(c2.get("high", 0))

            if direction == "BUY":
                if c1_low > c3_high and (c1_low - c3_high) >= min_gap:
                    current_mid = (float(tick.get("bid", 0)) + float(tick.get("ask", 0))) / 2.0
                    if c3_high <= current_mid <= c1_low:
                        return True

            if direction == "SELL":
                if c3_low > c1_high and (c3_low - c1_high) >= min_gap:
                    current_mid = (float(tick.get("bid", 0)) + float(tick.get("ask", 0))) / 2.0
                    if c1_high <= current_mid <= c3_low:
                        return True

        return False
