from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z12_THRESHOLD = float(os.getenv("GATE_Z12_THRESHOLD", "0.5"))


class GateZ12(BaseGate):
    gate_name = "gate_Z12"
    priority = 39

    def evaluate(self, tick: dict[str, Any]) -> bool:
        value = float(tick.get("hft_cluster_detected", 0.0))
        return value > Z12_THRESHOLD
