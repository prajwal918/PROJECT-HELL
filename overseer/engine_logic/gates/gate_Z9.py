from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z9_THRESHOLD = float(os.getenv("GATE_Z9_THRESHOLD", "0.2"))


class GateZ9(BaseGate):
    gate_name = "gate_Z9"
    priority = 36

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("adverse_selection_risk", 0.0))
        return value > Z9_THRESHOLD
