from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z5_THRESHOLD = float(os.getenv("GATE_Z5_THRESHOLD", "50"))


class GateZ5(BaseGate):
    gate_name = "gate_Z5"
    priority = 32

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("queue_absorbed_volume", 0.0))
        return value > Z5_THRESHOLD
