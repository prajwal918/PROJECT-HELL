from __future__ import annotations

import os
from collections import deque
from typing import Any

from .base_gate import BaseGate

_VWAP_WINDOW = int(os.getenv("GATE_VWAP_WINDOW", "200"))
_VWAP_BAND_PIPS = float(os.getenv("GATE_VWAP_BAND_PIPS", "10.0"))


class GateVWAP(BaseGate):
    gate_name = "gate_VWAP"
    priority = 29

    def __init__(self) -> None:
        self._typicals: deque[float] = deque(maxlen=_VWAP_WINDOW)
        self._volumes: deque[float] = deque(maxlen=_VWAP_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        volume = float(tick.get("volume", 1.0))
        if bid <= 0 or ask <= 0:
            return True
        mid = (bid + ask) / 2.0
        typical = (bid + ask + mid) / 3.0
        vol = max(volume, 1.0)
        self._typicals.append(typical * vol)
        self._volumes.append(vol)
        if len(self._typicals) < 20:
            return True
        cum_tp = sum(self._typicals)
        cum_vol = sum(self._volumes)
        if cum_vol <= 0:
            return True
        vwap = cum_tp / cum_vol
        pip_size = float(tick.get("pip_size", 0.0001))
        band = _VWAP_BAND_PIPS * pip_size
        tick["vwap"] = vwap
        distance_pips = (mid - vwap) / pip_size if pip_size > 0 else 0.0
        tick["vwap_distance_pips"] = distance_pips
        direction = tick.get("direction", "BUY")
        if direction == "BUY":
            if mid < vwap - band:
                return False
        if direction == "SELL":
            if mid > vwap + band:
                return False
        return True
