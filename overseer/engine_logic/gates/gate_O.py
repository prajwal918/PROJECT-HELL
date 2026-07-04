from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

TOXIC_SPOOF_THRESHOLD = float(os.getenv("GATE_O_SPOOF_THRESHOLD", "0.5"))
TOXIC_VACUUM_THRESHOLD = float(os.getenv("GATE_O_VACUUM_THRESHOLD", "3.0"))


class GateO(BaseGate):
    gate_name = "gate_O"
    priority = 15

    def evaluate(self, tick: dict[str, Any]) -> bool:
        spoof = float(tick.get("spoof_reversal_signal", 0.0))
        vacuum_cv = float(tick.get("liquidity_vacuum_cv", 0.0))
        adverse = float(tick.get("adverse_selection_risk", 0.0))
        toxicity = spoof * 0.4 + min(vacuum_cv / 10.0, 1.0) * 0.3 + adverse * 0.3
        return toxicity < TOXIC_SPOOF_THRESHOLD or vacuum_cv < TOXIC_VACUUM_THRESHOLD
