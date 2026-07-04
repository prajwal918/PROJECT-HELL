from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z11_THRESHOLD = float(os.getenv("GATE_Z11_THRESHOLD", "50"))


class GateZ11(BaseGate):
    gate_name = "gate_Z11"
    priority = 38

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("institutional_flight_volume", 0.0))
        return value > Z11_THRESHOLD
