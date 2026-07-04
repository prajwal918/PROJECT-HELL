from __future__ import annotations

import os
from collections import deque
from typing import Any

import numpy as np

from .base_gate import BaseGate

_TPO_WINDOW = int(os.getenv("GATE_TPO_WINDOW", "200"))
_TPO_BINS = int(os.getenv("GATE_TPO_BINS", "30"))
_TPO_VA_RATIO = float(os.getenv("GATE_TPO_VA_RATIO", "0.7"))


class GateTPO(BaseGate):
    gate_name = "gate_TPO"
    priority = 26

    def __init__(self) -> None:
        self._mids: deque[float] = deque(maxlen=_TPO_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        if bid <= 0 or ask <= 0:
            return True
        mid = (bid + ask) / 2.0
        self._mids.append(mid)
        if len(self._mids) < 30:
            return True
        mids = np.array(self._mids)
        if mids.max() == mids.min():
            return True
        counts, bin_edges = np.histogram(mids, bins=_TPO_BINS)
        total = counts.sum()
        if total <= 0:
            return True
        sorted_counts = np.sort(counts)[::-1]
        va_vol = 0
        va_count = 0
        for c in sorted_counts:
            va_vol += c
            va_count += 1
            if va_vol >= total * _TPO_VA_RATIO:
                break
        va_indices = np.argsort(counts)[::-1][:va_count]
        va_low = float(bin_edges[va_indices.min() + 1])
        va_high = float(bin_edges[va_indices.max() + 1])
        poc_idx = int(np.argmax(counts))
        poc_price = float((bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2.0)
        tick["tpo_val"] = va_low
        tick["tpo_vah"] = va_high
        tick["tpo_poc"] = poc_price
        direction = tick.get("direction", "BUY")
        in_value_area = va_low <= mid <= va_high
        if direction == "BUY" and mid < va_low:
            return False
        if direction == "SELL" and mid > va_high:
            return False
        return True
