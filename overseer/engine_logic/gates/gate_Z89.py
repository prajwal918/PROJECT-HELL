from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

Z89_MIN_SIGNALS = int(os.getenv("GATE_Z89_MIN_SIGNALS", "1"))


class GateZ89(BaseGate):
    gate_name = "gate_Z89"
    priority = 46

    def evaluate(self, tick: dict[str, Any]) -> bool:
        signals = [
            float(tick.get("spoof_reversal_signal", 0.0)),
            float(tick.get("iceberg_detected", 0.0)),
            float(tick.get("hft_cluster_detected", 0.0)),
            float(tick.get("liquidity_vacuum_signal", 0.0)),
        ]
        active = sum(1 for s in signals if s > 0.0)
        return active >= Z89_MIN_SIGNALS
