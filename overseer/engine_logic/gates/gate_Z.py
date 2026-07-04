from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

L3_MIN_SIGNALS = int(os.getenv("GATE_Z_MIN_L3_SIGNALS", "1"))


class GateZ(BaseGate):
    gate_name = "gate_Z"
    priority = 26

    def evaluate(self, tick: dict[str, Any]) -> bool:
        spoof = float(tick.get("spoof_reversal_signal", 0.0))
        queue = float(tick.get("queue_exhaustion_signal", 0.0))
        iceberg = float(tick.get("iceberg_detected", 0.0))
        adverse = float(tick.get("adverse_selection_risk", 0.0))
        hft = float(tick.get("hft_cluster_detected", 0.0))
        vacuum = float(tick.get("liquidity_vacuum_signal", 0.0))
        active_count = sum(1 for v in [spoof, queue, iceberg, hft, vacuum] if v > 0)
        adverse_threshold = float(tick.get("adverse_threshold", 0.4))
        if adverse > adverse_threshold:
            return False
        return active_count >= L3_MIN_SIGNALS
