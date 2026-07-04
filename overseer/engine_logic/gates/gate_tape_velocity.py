from __future__ import annotations

import logging
import os
import time
from collections import deque
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_tape_velocity")

_VELOCITY_WINDOW_SECONDS = float(os.getenv("TAPE_VELOCITY_WINDOW_SECONDS", "3.0"))
_EXHAUSTION_TPS_THRESHOLD = float(os.getenv("TAPE_EXHAUSTION_TPS", "2.0"))
_SURGE_TPS_THRESHOLD = float(os.getenv("TAPE_SURGE_TPS", "15.0"))


class GateTapeVelocity(BaseGate):
    gate_name = "gate_tape_velocity"
    priority = 31

    def __init__(self) -> None:
        self._tick_timestamps: dict[str, deque] = {}
        self._prev_tps: dict[str, float] = {}

    def _get_tps(self, symbol: str) -> float:
        now = time.monotonic()
        if symbol not in self._tick_timestamps:
            self._tick_timestamps[symbol] = deque()
        ts = self._tick_timestamps[symbol]
        ts.append(now)
        while ts and ts[0] < now - _VELOCITY_WINDOW_SECONDS:
            ts.popleft()
        return len(ts) / _VELOCITY_WINDOW_SECONDS if _VELOCITY_WINDOW_SECONDS > 0 else 0.0

    def evaluate(self, tick: dict[str, Any]) -> bool:
        symbol = tick.get("symbol", "")
        direction = tick.get("direction", "BUY")

        current_tps = self._get_tps(symbol)
        prev_tps = self._prev_tps.get(symbol, 0.0)
        self._prev_tps[symbol] = current_tps

        mid = (float(tick.get("bid", 0)) + float(tick.get("ask", 0))) / 2.0
        session_extreme = tick.get("_session_extreme", False)

        if session_extreme and current_tps < _EXHAUSTION_TPS_THRESHOLD and prev_tps > _EXHAUSTION_TPS_THRESHOLD * 2:
            LOGGER.info("Tape exhaustion at session extreme: %s TPS=%.1f->%.1f dir=%s", symbol, prev_tps, current_tps, direction)
            return False

        if current_tps < _EXHAUSTION_TPS_THRESHOLD and not session_extreme:
            return True

        if current_tps >= _SURGE_TPS_THRESHOLD:
            return True

        return True
