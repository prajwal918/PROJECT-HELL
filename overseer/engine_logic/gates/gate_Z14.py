from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z14_THRESHOLD = float(os.getenv("GATE_Z14_THRESHOLD", "3.0"))


class GateZ14(BaseGate):
    gate_name = "gate_Z14"
    priority = 41

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("liquidity_vacuum_cv", 0.0))
        return value > Z14_THRESHOLD
