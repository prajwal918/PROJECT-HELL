from __future__ import annotations

import os
from collections import deque
from typing import Any

from .base_gate import BaseGate

DELTA_DIV_WINDOW = int(os.getenv("GATE_U_WINDOW", "20"))
DELTA_DIV_MAX = float(os.getenv("GATE_U_MAX_DIVERGENCE", "3.0"))


class GateU(BaseGate):
    gate_name = "gate_U"
    priority = 21

    def __init__(self) -> None:
        self._deltas: deque[float] = deque(maxlen=DELTA_DIV_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        delta = float(tick.get("delta", 0.0))
        self._deltas.append(delta)
        if len(self._deltas) < 5:
            return True
        mean_d = sum(self._deltas) / len(self._deltas)
        variance = sum((d - mean_d) ** 2 for d in self._deltas) / len(self._deltas)
        std_d = variance ** 0.5
        if std_d <= 0:
            return True
        zscore = (delta - mean_d) / std_d
        return abs(zscore) <= DELTA_DIV_MAX
