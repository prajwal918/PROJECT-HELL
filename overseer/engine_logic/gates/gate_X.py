from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

MIN_CORRELATION = float(os.getenv("GATE_X_MIN_CORRELATION", "0.70"))


class GateX(BaseGate):
    gate_name = "gate_X"
    priority = 24

    def evaluate(self, tick: dict[str, Any]) -> bool:
        cross_corr = float(tick.get("cross_market_correlation", 1.0))
        return abs(cross_corr) >= MIN_CORRELATION
