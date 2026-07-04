from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

MIN_DEPTH_CONTRACTS = float(os.getenv("GATE_L_MIN_DEPTH", "50"))


class GateL(BaseGate):
    gate_name = "gate_L"
    priority = 12

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid_depth = float(tick.get("depth_bid_3", tick.get("bid_size", 0.0)))
        ask_depth = float(tick.get("depth_ask_3", tick.get("ask_size", 0.0)))
        total = bid_depth + ask_depth
        min_depth = float(tick.get("depth_min_contracts", MIN_DEPTH_CONTRACTS))
        return total >= min_depth
