from __future__ import annotations

import os
from collections import deque
from typing import Any

from .base_gate import BaseGate

MOMENTUM_WINDOW = int(os.getenv("GATE_M_WINDOW", "10"))
MOMENTUM_MIN_CONSISTENCY = float(os.getenv("GATE_M_MIN_CONSISTENCY", "0.6"))


class GateM(BaseGate):
    gate_name = "gate_M"
    priority = 13

    def __init__(self) -> None:
        self._deltas: deque[float] = deque(maxlen=MOMENTUM_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        delta = float(tick.get("delta", 0.0))
        self._deltas.append(delta)
        if len(self._deltas) < MOMENTUM_WINDOW:
            return True
        direction = tick.get("direction", "BUY")
        positive = sum(1 for d in self._deltas if d > 0)
        negative = sum(1 for d in self._deltas if d < 0)
        if direction == "BUY":
            consistency = positive / len(self._deltas)
        else:
            consistency = negative / len(self._deltas)
        return consistency >= MOMENTUM_MIN_CONSISTENCY
