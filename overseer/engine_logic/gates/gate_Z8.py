from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z8_THRESHOLD = float(os.getenv("GATE_Z8_THRESHOLD", "30"))


class GateZ8(BaseGate):
    gate_name = "gate_Z8"
    priority = 35

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("iceberg_hidden_depth", 0.0))
        return value > Z8_THRESHOLD
