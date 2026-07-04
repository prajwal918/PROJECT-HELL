from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z3_THRESHOLD = float(os.getenv("GATE_Z3_THRESHOLD", "0.5"))


class GateZ3(BaseGate):
    gate_name = "gate_Z3"
    priority = 30

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("queue_attrition_pct", 0.0))
        return value > Z3_THRESHOLD
