from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

MIN_RR_RATIO = float(os.getenv("GATE_P_MIN_RR", "1.5"))


class GateP(BaseGate):
    gate_name = "gate_P"
    priority = 16

    def evaluate(self, tick: dict[str, Any]) -> bool:
        rr_ratio = float(tick.get("risk_reward_ratio", 0.0))
        if rr_ratio <= 0:
            return True
        min_rr = float(tick.get("risk_reward_min", MIN_RR_RATIO))
        return rr_ratio >= min_rr
