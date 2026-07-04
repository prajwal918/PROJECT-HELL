from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z4_THRESHOLD = float(os.getenv("GATE_Z4_THRESHOLD", "0.5"))


class GateZ4(BaseGate):
    gate_name = "gate_Z4"
    priority = 31

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("queue_exhaustion_signal", 0.0))
        return value > Z4_THRESHOLD
