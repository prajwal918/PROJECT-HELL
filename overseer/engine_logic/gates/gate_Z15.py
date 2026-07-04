from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z15_THRESHOLD = float(os.getenv("GATE_Z15_THRESHOLD", "0.5"))


class GateZ15(BaseGate):
    gate_name = "gate_Z15"
    priority = 42

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("liquidity_vacuum_signal", 0.0))
        return value > Z15_THRESHOLD
