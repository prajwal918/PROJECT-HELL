from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z6_THRESHOLD = float(os.getenv("GATE_Z6_THRESHOLD", "0.5"))


class GateZ6(BaseGate):
    gate_name = "gate_Z6"
    priority = 33

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("iceberg_detected", 0.0))
        return value > Z6_THRESHOLD
