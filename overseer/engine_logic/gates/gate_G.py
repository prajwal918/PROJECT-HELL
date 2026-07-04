from __future__ import annotations

import os
from collections import deque
from typing import Any

from .base_gate import BaseGate

VOLUME_SPIKE_WINDOW = int(os.getenv("VOLUME_SPIKE_WINDOW", "20"))
VOLUME_SPIKE_RATIO = float(os.getenv("VOLUME_SPIKE_RATIO", "1.5"))


class GateG(BaseGate):
    gate_name = "gate_G"
    priority = 7

    def __init__(self) -> None:
        self._volumes: deque[float] = deque(maxlen=VOLUME_SPIKE_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid_size = float(tick.get("bid_size", 0.0))
        ask_size = float(tick.get("ask_size", 0.0))
        volume = bid_size + ask_size
        self._volumes.append(volume)
        if len(self._volumes) < VOLUME_SPIKE_WINDOW:
            return True
        baseline = float(tick.get("volume_baseline", 5000.0))
        if baseline <= 0:
            baseline = sum(self._volumes) / len(self._volumes)
            if baseline <= 0:
                return False
        avg_recent = sum(list(self._volumes)[-5:]) / 5.0
        avg_older = sum(list(self._volumes)[:-5]) / max(1, len(self._volumes) - 5)
        if avg_older <= 0:
            return avg_recent > 0
        ratio = avg_recent / avg_older
        return ratio >= VOLUME_SPIKE_RATIO
