from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_PO3")

_PO3_LOOKBACK_CANDLES = int(__import__("os").getenv("PO3_LOOKBACK_CANDLES", "6"))


class GatePO3(BaseGate):
    gate_name = "gate_PO3"
    priority = 34

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")
        candles = tick.get("_candles_1h", [])
        if not candles or len(candles) < 3:
            candles = tick.get("_candles_15m", [])
        if not candles or len(candles) < 3:
            return False
        lookback = min(_PO3_LOOKBACK_CANDLES, len(candles))
        if lookback < 3:
            return False
        recent = candles[-lookback:]
        if len(recent) < 3:
            return False

        first = recent[0]
        last = recent[-1]
        if not isinstance(first, dict) or not isinstance(last, dict):
            return False

        accumulation_high = 0.0
        accumulation_low = float("inf")
        for c in recent[: len(recent) // 2]:
            if not isinstance(c, dict):
                continue
            h = float(c.get("high", 0))
            l = float(c.get("low", 0))
            if h > accumulation_high:
                accumulation_high = h
            if l < accumulation_low:
                accumulation_low = l

        if accumulation_high <= 0 or accumulation_low == float("inf"):
            return False

        first_low = float(first.get("low", 0))
        last_close = float(last.get("close", 0))
        last_high = float(last.get("high", 0))
        last_low = float(last.get("low", 0))
        first_high = float(first.get("high", 0))
        range_val = accumulation_high - accumulation_low

        if range_val <= 0:
            return False

        if direction == "BUY":
            mid_candles = recent[len(recent) // 2:-1]
            swept_low = False
            for c in mid_candles:
                if not isinstance(c, dict):
                    continue
                cl = float(c.get("low", 0))
                if cl < accumulation_low:
                    swept_low = True
                    break
            if not swept_low and first_low < accumulation_low:
                swept_low = True

            if last_close > accumulation_high:
                if swept_low:
                    return True

        if direction == "SELL":
            mid_candles = recent[len(recent) // 2:-1]
            swept_high = False
            for c in mid_candles:
                if not isinstance(c, dict):
                    continue
                ch = float(c.get("high", 0))
                if ch > accumulation_high:
                    swept_high = True
                    break
            if not swept_high and first_high > accumulation_high:
                swept_high = True

            if last_close < accumulation_low:
                if swept_high:
                    return True

        return False
