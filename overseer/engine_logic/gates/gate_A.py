from __future__ import annotations

import os
from collections import deque
from typing import Any

from .base_gate import BaseGate

TREND_ALIGN_WINDOW = int(os.getenv("GATE_A_WINDOW", "10"))


class GateA(BaseGate):
    gate_name = "gate_A"
    priority = 1

    def __init__(self) -> None:
        self._mids: deque[float] = deque(maxlen=TREND_ALIGN_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        if bid <= 0 or ask <= 0 or ask <= bid:
            return False
        mid = (bid + ask) / 2.0
        self._mids.append(mid)
        if len(self._mids) < TREND_ALIGN_WINDOW:
            return True
        direction = tick.get("direction", "BUY")
        first = self._mids[0]
        last = self._mids[-1]
        trend = last - first
        pip_size = float(tick.get("pip_size", 0.0001))
        if direction == "BUY":
            return trend > pip_size
        elif direction == "SELL":
            return trend < -pip_size
        return abs(trend) > pip_size
