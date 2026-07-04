from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z2_THRESHOLD = float(os.getenv("GATE_Z2_THRESHOLD", "100"))


class GateZ2(BaseGate):
    gate_name = "gate_Z2"
    priority = 29

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("spoof_volume_vanished", 0.0))
        return value > Z2_THRESHOLD
