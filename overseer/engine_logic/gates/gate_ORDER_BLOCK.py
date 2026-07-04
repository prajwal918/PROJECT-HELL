from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_ORDER_BLOCK")

_OB_LOOKBACK_CANDLES = int(__import__("os").getenv("OB_LOOKBACK_CANDLES", "15"))
_OB_MIN_BODY_PIPS = float(__import__("os").getenv("OB_MIN_BODY_PIPS", "3.0"))


class GateOrderBlock(BaseGate):
    gate_name = "gate_ORDER_BLOCK"
    priority = 31

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")
        candles = tick.get("_candles_1h", [])
        if not candles or len(candles) < 3:
            candles = tick.get("_candles_15m", [])
        if not candles or len(candles) < 3:
            return False
        pip_size = float(tick.get("pip_size", 0.0001))
        min_body = _OB_MIN_BODY_PIPS * pip_size
        current_mid = (float(tick.get("bid", 0)) + float(tick.get("ask", 0))) / 2.0
        if current_mid <= 0:
            return False
        lookback = min(_OB_LOOKBACK_CANDLES, len(candles))

        for i in range(max(0, len(candles) - lookback), len(candles)):
            c = candles[i]
            if not isinstance(c, dict):
                continue
            c_open = float(c.get("open", 0))
            c_close = float(c.get("close", 0))
            c_high = float(c.get("high", 0))
            c_low = float(c.get("low", 0))
            body = abs(c_close - c_open)
            if body < min_body:
                continue

            if direction == "BUY":
                if c_close < c_open:
                    ob_high = c_open
                    ob_low = c_close
                else:
                    ob_high = c_high
                    ob_low = min(c_open, c_close)
                if ob_low <= current_mid <= ob_high:
                    return True

            if direction == "SELL":
                if c_close > c_open:
                    ob_high = c_close
                    ob_low = c_open
                else:
                    ob_low = c_low
                    ob_high = max(c_open, c_close)
                if ob_low <= current_mid <= ob_high:
                    return True

        return False
