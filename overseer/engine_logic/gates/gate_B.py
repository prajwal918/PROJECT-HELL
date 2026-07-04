from __future__ import annotations

import os
from collections import deque
from typing import Any

from .base_gate import BaseGate

STRUCTURE_WINDOW = int(os.getenv("GATE_B_WINDOW", "10"))
STRUCTURE_MIN_HIGHS = int(os.getenv("GATE_B_MIN_HIGHS", "2"))


class GateB(BaseGate):
    gate_name = "gate_B"
    priority = 2

    def __init__(self) -> None:
        self._highs: deque[float] = deque(maxlen=STRUCTURE_WINDOW)
        self._lows: deque[float] = deque(maxlen=STRUCTURE_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        if bid <= 0 or ask <= 0 or ask <= bid:
            return False
        mid = (bid + ask) / 2.0
        self._highs.append(mid)
        self._lows.append(mid)
        if len(self._highs) < STRUCTURE_WINDOW:
            return True
        direction = tick.get("direction", "BUY")
        pip_size = float(tick.get("pip_size", 0.0001))
        recent_highs = list(self._highs)[-STRUCTURE_MIN_HIGHS:]
        recent_lows = list(self._lows)[-STRUCTURE_MIN_HIGHS:]
        if direction == "BUY":
            ascending = all(recent_highs[i] <= recent_highs[i + 1] for i in range(len(recent_highs) - 1))
            return ascending
        elif direction == "SELL":
            descending = all(recent_lows[i] >= recent_lows[i + 1] for i in range(len(recent_lows) - 1))
            return descending
        return True
