from __future__ import annotations

import os
from collections import deque
from typing import Any

from .base_gate import BaseGate

TREND_WINDOW = int(os.getenv("GATE_T_WINDOW", "20"))
TREND_MIN_SLOPE = float(os.getenv("GATE_T_MIN_SLOPE", "0.00001"))


class GateT(BaseGate):
    gate_name = "gate_T"
    priority = 20

    def __init__(self) -> None:
        self._mids: deque[float] = deque(maxlen=TREND_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        if bid <= 0 or ask <= 0:
            return False
        mid = (bid + ask) / 2.0
        self._mids.append(mid)
        if len(self._mids) < TREND_WINDOW:
            return True
        direction = tick.get("direction", "BUY")
        first = self._mids[0]
        last = self._mids[-1]
        slope = (last - first) / len(self._mids)
        pip_size = float(tick.get("pip_size", 0.0001))
        if direction == "BUY" and slope >= pip_size * 0.1:
            return True
        if direction == "SELL" and slope <= -pip_size * 0.1:
            return True
        if abs(slope) < pip_size * 0.01:
            return True
        return False
