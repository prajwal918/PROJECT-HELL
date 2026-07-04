from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z16_THRESHOLD = float(os.getenv("GATE_Z16_THRESHOLD", "2"))


class GateZ16(BaseGate):
    gate_name = "gate_Z16"
    priority = 43

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("vacuum_cascade_depth", 0.0))
        return value > Z16_THRESHOLD
