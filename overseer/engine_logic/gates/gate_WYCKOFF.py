from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_WYCKOFF")

_WYCKOFF_LOOKBACK = int(__import__("os").getenv("WYCKOFF_LOOKBACK_CANDLES", "30"))
_WYCKOFF_VOLUME_RATIO = float(__import__("os").getenv("WYCKOFF_VOLUME_RATIO", "1.5"))
_WYCKOFF_SPRING_PIPS = float(__import__("os").getenv("WYCKOFF_SPRING_PIPS", "3.0"))


class GateWyckoff(BaseGate):
    gate_name = "gate_WYCKOFF"
    priority = 33

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")
        candles = tick.get("_candles_daily", [])
        if not candles or len(candles) < 10:
            candles = tick.get("_candles_1h", [])
        if not candles or len(candles) < 10:
            return False
        pip_size = float(tick.get("pip_size", 0.0001))
        spring_pips = _WYCKOFF_SPRING_PIPS * pip_size
        lookback = min(_WYCKOFF_LOOKBACK, len(candles))
        recent = candles[-lookback:]
        if len(recent) < 10:
            return False

        support_levels = []
        resistance_levels = []
        for i in range(2, len(recent) - 2):
            c = recent[i]
            if not isinstance(c, dict):
                continue
            c_low = float(c.get("low", 0))
            c_high = float(c.get("high", 0))
            p1_low = float(recent[i - 1].get("low", 0)) if isinstance(recent[i - 1], dict) else 0
            p2_low = float(recent[i - 2].get("low", 0)) if isinstance(recent[i - 2], dict) else 0
            n1_low = float(recent[i + 1].get("low", 0)) if isinstance(recent[i + 1], dict) else 0
            n2_low = float(recent[i + 2].get("low", 0)) if isinstance(recent[i + 2], dict) else 0
            p1_high = float(recent[i - 1].get("high", 0)) if isinstance(recent[i - 1], dict) else 0
            p2_high = float(recent[i - 2].get("high", 0)) if isinstance(recent[i - 2], dict) else 0
            n1_high = float(recent[i + 1].get("high", 0)) if isinstance(recent[i + 1], dict) else 0
            n2_high = float(recent[i + 2].get("high", 0)) if isinstance(recent[i + 2], dict) else 0
            if c_low < p1_low and c_low < p2_low and c_low < n1_low and c_low < n2_low:
                support_levels.append(c_low)
            if c_high > p1_high and c_high > p2_high and c_high > n1_high and c_high > n2_high:
                resistance_levels.append(c_high)

        if not support_levels and not resistance_levels:
            return False

        last = recent[-1]
        if not isinstance(last, dict):
            return False
        last_close = float(last.get("close", 0))
        last_low = float(last.get("low", 0))
        last_high = float(last.get("high", 0))
        last_vol = float(last.get("volume", 0))
        avg_vol = sum(float(c.get("volume", 0)) for c in recent[-5:] if isinstance(c, dict)) / 5.0 if len(recent) >= 5 else 1.0

        if direction == "BUY":
            if not support_levels:
                return False
            nearest_support = min(support_levels, key=lambda s: abs(s - last_close))
            if last_low < nearest_support and last_close > nearest_support:
                if last_low < nearest_support - spring_pips * 0.5:
                    if last_vol > avg_vol * _WYCKOFF_VOLUME_RATIO:
                        return True
                if last_close > nearest_support:
                    return True

        if direction == "SELL":
            if not resistance_levels:
                return False
            nearest_resist = min(resistance_levels, key=lambda r: abs(r - last_close))
            if last_high > nearest_resist and last_close < nearest_resist:
                if last_high > nearest_resist + spring_pips * 0.5:
                    if last_vol > avg_vol * _WYCKOFF_VOLUME_RATIO:
                        return True
                if last_close < nearest_resist:
                    return True

        return False
