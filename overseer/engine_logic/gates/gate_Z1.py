from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z1_THRESHOLD = float(os.getenv("GATE_Z1_THRESHOLD", "0.5"))


class GateZ1(BaseGate):
    gate_name = "gate_Z1"
    priority = 28

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("spoof_reversal_signal", 0.0))
        return value > Z1_THRESHOLD
