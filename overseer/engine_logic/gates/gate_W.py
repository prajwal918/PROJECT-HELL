from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

MIN_ML_CONFIDENCE = float(os.getenv("GATE_W_MIN_CONFIDENCE", "0.68"))


class GateW(BaseGate):
    gate_name = "gate_W"
    priority = 23

    def evaluate(self, tick: dict[str, Any]) -> bool:
        ml_confidence = float(tick.get("ml_confidence", 0.0))
        if ml_confidence <= 0:
            return True
        return ml_confidence >= MIN_ML_CONFIDENCE
