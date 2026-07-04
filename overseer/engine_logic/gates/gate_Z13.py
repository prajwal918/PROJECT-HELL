from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z13_THRESHOLD = float(os.getenv("GATE_Z13_THRESHOLD", "100"))


class GateZ13(BaseGate):
    gate_name = "gate_Z13"
    priority = 40

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("hft_synchronized_volume", 0.0))
        return value > Z13_THRESHOLD
