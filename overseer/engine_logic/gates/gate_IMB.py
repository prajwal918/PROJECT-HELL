from __future__ import annotations

import os
from collections import deque
from typing import Any

from .base_gate import BaseGate

_IMB_WINDOW = int(os.getenv("GATE_IMB_WINDOW", "20"))
_IMB_RATIO_MIN = float(os.getenv("GATE_IMB_RATIO_MIN", "1.5"))


class GateIMB(BaseGate):
    gate_name = "gate_IMB"
    priority = 28

    def __init__(self) -> None:
        self._bid_sizes: deque[float] = deque(maxlen=_IMB_WINDOW)
        self._ask_sizes: deque[float] = deque(maxlen=_IMB_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid_size = float(tick.get("bid_size", 0.0))
        ask_size = float(tick.get("ask_size", 0.0))
        dom = tick.get("dom", {})
        if dom:
            bids = dom.get("bids", [])
            asks = dom.get("asks", [])
            if bids:
                bid_size = sum(float(b.get("size", b.get("Size", 0))) for b in bids[:5])
            if asks:
                ask_size = sum(float(a.get("size", a.get("Size", 0))) for a in asks[:5])
        self._bid_sizes.append(bid_size)
        self._ask_sizes.append(ask_size)
        if len(self._bid_sizes) < 5:
            return True
        avg_bid = sum(self._bid_sizes) / len(self._bid_sizes)
        avg_ask = sum(self._ask_sizes) / len(self._ask_sizes)
        if avg_bid <= 0 or avg_ask <= 0:
            return True
        ratio = avg_bid / avg_ask
        tick["imb_ratio"] = ratio
        direction = tick.get("direction", "BUY")
        if direction == "BUY" and ratio < (1.0 / _IMB_RATIO_MIN):
            return False
        if direction == "SELL" and ratio > _IMB_RATIO_MIN:
            return False
        return True
