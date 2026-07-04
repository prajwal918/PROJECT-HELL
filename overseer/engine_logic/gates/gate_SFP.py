from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_SFP")

_SFP_LOOKBACK_CANDLES = int(__import__("os").getenv("SFP_LOOKBACK_CANDLES", "20"))
_SFP_WICK_RATIO = float(__import__("os").getenv("SFP_WICK_RATIO", "0.5"))


class GateSFP(BaseGate):
    gate_name = "gate_SFP"
    priority = 32

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")
        candles = tick.get("_candles_1h", [])
        if not candles or len(candles) < 5:
            candles = tick.get("_candles_15m", [])
        if not candles or len(candles) < 5:
            return False
        lookback = min(_SFP_LOOKBACK_CANDLES, len(candles))
        recent = candles[-lookback:]

        if len(recent) < 5:
            return False

        swing_highs = []
        swing_lows = []
        for i in range(1, len(recent) - 1):
            c = recent[i]
            prev = recent[i - 1]
            nxt = recent[i + 1]
            if not isinstance(c, dict) or not isinstance(prev, dict) or not isinstance(nxt, dict):
                continue
            c_high = float(c.get("high", 0))
            c_low = float(c.get("low", 0))
            prev_high = float(prev.get("high", 0))
            prev_low = float(prev.get("low", 0))
            nxt_high = float(nxt.get("high", 0))
            nxt_low = float(nxt.get("low", 0))
            if c_high > prev_high and c_high > nxt_high:
                swing_highs.append((i, c_high))
            if c_low < prev_low and c_low < nxt_low:
                swing_lows.append((i, c_low))

        if not swing_highs and not swing_lows:
            return False

        last = recent[-1]
        if not isinstance(last, dict):
            return False
        last_high = float(last.get("high", 0))
        last_low = float(last.get("low", 0))
        last_open = float(last.get("open", 0))
        last_close = float(last.get("close", 0))
        last_range = last_high - last_low
        if last_range <= 0:
            return False

        if direction == "BUY":
            for _, sh in swing_highs:
                if last_high > sh and last_close < sh:
                    wick_upper = last_high - max(last_open, last_close)
                    if last_range > 0 and wick_upper / last_range >= _SFP_WICK_RATIO:
                        return True

        if direction == "SELL":
            for _, sl in swing_lows:
                if last_low < sl and last_close > sl:
                    wick_lower = min(last_open, last_close) - last_low
                    if last_range > 0 and wick_lower / last_range >= _SFP_WICK_RATIO:
                        return True

        return False
