from __future__ import annotations

import os
from collections import deque
from typing import Any

from .base_gate import BaseGate

NET_DELTA_WINDOW = int(os.getenv("GATE_N_WINDOW", "20"))
NET_DELTA_MAX_ABS = float(os.getenv("GATE_N_MAX_ABS", "500"))


class GateN(BaseGate):
    gate_name = "gate_N"
    priority = 14

    def __init__(self) -> None:
        self._deltas: deque[float] = deque(maxlen=NET_DELTA_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        delta = float(tick.get("delta", 0.0))
        self._deltas.append(delta)
        if len(self._deltas) < 3:
            return True
        net = sum(self._deltas)
        return abs(net) <= NET_DELTA_MAX_ABS
