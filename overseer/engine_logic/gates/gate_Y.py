from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

DEPTH_IMBALANCE_MAX = float(os.getenv("GATE_Y_MAX_IMBALANCE", "0.85"))


class GateY(BaseGate):
    gate_name = "gate_Y"
    priority = 25

    def evaluate(self, tick: dict[str, Any]) -> bool:
        obi = float(tick.get("obi_5", tick.get("obi_3", 0.0)))
        return abs(obi) < DEPTH_IMBALANCE_MAX
