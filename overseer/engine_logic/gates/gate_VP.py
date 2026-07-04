from __future__ import annotations

import os
from collections import deque
from typing import Any

import numpy as np

from .base_gate import BaseGate

_VP_WINDOW = int(os.getenv("GATE_VP_WINDOW", "200"))
_VP_BINS = int(os.getenv("GATE_VP_BINS", "50"))
_VP_POC_WEIGHT = float(os.getenv("GATE_VP_POC_WEIGHT", "0.3"))
_VP_VA_RATIO_MIN = float(os.getenv("GATE_VP_VA_RATIO_MIN", "0.6"))


class GateVP(BaseGate):
    gate_name = "gate_VP"
    priority = 25

    def __init__(self) -> None:
        self._mids: deque[float] = deque(maxlen=_VP_WINDOW)
        self._volumes: deque[float] = deque(maxlen=_VP_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        volume = float(tick.get("volume", 0.0))
        if bid <= 0 or ask <= 0:
            return True
        mid = (bid + ask) / 2.0
        self._mids.append(mid)
        self._volumes.append(max(volume, 1.0))
        if len(self._mids) < 30:
            return True
        mids = np.array(self._mids)
        vols = np.array(self._volumes)
        if mids.max() == mids.min():
            return True
        counts, bin_edges = np.histogram(mids, bins=_VP_BINS, weights=vols)
        poc_idx = int(np.argmax(counts))
        poc_price = (bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2.0
        total_vol = counts.sum()
        if total_vol <= 0:
            return True
        sorted_counts = np.sort(counts)[::-1]
        va_vol = 0.0
        va_count = 0
        for c in sorted_counts:
            va_vol += c
            va_count += 1
            if va_vol >= total_vol * _VP_VA_RATIO_MIN:
                break
        va_indices = np.argsort(counts)[::-1][:va_count]
        va_low = bin_edges[va_indices.min() + 1]
        va_high = bin_edges[va_indices.max() + 1]
        tick["vp_poc"] = float(poc_price)
        tick["vp_val"] = float(va_low)
        tick["vp_vah"] = float(va_high)
        current_mid = mid
        distance_to_poc = abs(current_mid - poc_price)
        range_size = max(va_high - va_low, 1e-10)
        proximity = 1.0 - min(distance_to_poc / range_size, 1.0)
        tick["vp_poc_proximity"] = float(proximity)
        direction = tick.get("direction", "BUY")
        if direction == "BUY":
            if current_mid < va_low:
                return proximity >= _VP_POC_WEIGHT
            return current_mid >= va_low
        if current_mid > va_high:
            return proximity >= _VP_POC_WEIGHT
        return current_mid <= va_high
