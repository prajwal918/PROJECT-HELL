from __future__ import annotations

import os
import time
from typing import Any

from .base_gate import BaseGate

SESSION_UTC_START = int(os.getenv("SESSION_UTC_START", "7"))
SESSION_UTC_END = int(os.getenv("SESSION_UTC_END", "20"))
SESSION_ALLOW_ASIA = os.getenv("SESSION_ALLOW_ASIA", "false").lower() == "true"


class GateH(BaseGate):
    gate_name = "gate_H"
    priority = 8

    def evaluate(self, tick: dict[str, Any]) -> bool:
        now_utc = time.gmtime()
        hour = now_utc.tm_hour
        allow_asia = tick.get("session_allow_asia", SESSION_ALLOW_ASIA)
        if allow_asia:
            return True
        if SESSION_UTC_START <= hour < SESSION_UTC_END:
            return True
        return False
