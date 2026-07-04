from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z10_THRESHOLD = float(os.getenv("GATE_Z10_THRESHOLD", "0.3"))


class GateZ10(BaseGate):
    gate_name = "gate_Z10"
    priority = 37

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("adverse_selection_ratio", 0.0))
        return value > Z10_THRESHOLD
