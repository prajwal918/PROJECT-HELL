from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

MIN_QUEUE_QUALITY = float(os.getenv("GATE_Q_MIN_QUALITY", "0.3"))


class GateQ(BaseGate):
    gate_name = "gate_Q"
    priority = 17

    def evaluate(self, tick: dict[str, Any]) -> bool:
        attrition = float(tick.get("queue_attrition_pct", 0.0))
        adverse = float(tick.get("adverse_selection_risk", 0.0))
        quality = 1.0 - attrition - adverse
        return quality >= MIN_QUEUE_QUALITY
