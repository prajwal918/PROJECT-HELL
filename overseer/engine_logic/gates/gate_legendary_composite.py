from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_legendary_composite")

_PLATINUM_GATES = [
    "gate_Z15", "gate_A", "gate_D",
    "gate_stacked_imbalance", "gate_CVD", "gate_M",
]
_SUPPORTING_GATES = [
    "gate_FVG", "gate_ORDER_BLOCK", "gate_SFP",
    "gate_WYCKOFF", "gate_PO3",
    "gate_iceberg_monitor", "gate_H", "gate_I",
]
_MIN_PLATINUM = int(__import__("os").getenv("LEGENDARY_MIN_PLATINUM", "6"))
_MIN_SUPPORTING = int(__import__("os").getenv("LEGENDARY_MIN_SUPPORTING", "2"))


class GateLegendaryComposite(BaseGate):
    gate_name = "gate_legendary_composite"
    priority = 5

    def evaluate(self, tick: dict[str, Any]) -> bool:
        gate_states = tick.get("_gate_states_cache", {})
        if not gate_states:
            return False

        platinum_passed = sum(1 for g in _PLATINUM_GATES if gate_states.get(g, False))
        if platinum_passed < _MIN_PLATINUM:
            return False

        supporting_passed = sum(1 for g in _SUPPORTING_GATES if gate_states.get(g, False))
        if supporting_passed < _MIN_SUPPORTING:
            return False

        score = tick.get("_raw_model_score", 0)
        threshold = float(__import__("os").getenv("LEGENDARY_SCORE_THRESHOLD", "0.95"))
        if score < threshold:
            return False

        kz_quality = float(tick.get("_killzone_quality", 0))
        peak_only = __import__("os").getenv("LEGENDARY_KILLZONE_PEAK_ONLY", "true").lower() == "true"
        if peak_only and not tick.get("_in_peak_killzone", False):
            return False

        roll_status = tick.get("_roll_status", "ACTIVE")
        if roll_status in ("NEAR_EXPIRY", "ROLL_NOW"):
            return False

        return True
