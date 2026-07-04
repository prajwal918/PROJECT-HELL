from __future__ import annotations

import os
from collections import deque
from typing import Any

import numpy as np

from .base_gate import BaseGate

_SR_WINDOW = int(os.getenv("GATE_SR_WINDOW", "200"))
_SR_PIP_PROXIMITY = float(os.getenv("GATE_SR_PIP_PROXIMITY", "5.0"))
_SR_MIN_TOUCHES = int(os.getenv("GATE_SR_MIN_TOUCHES", "3"))
_SR_TOLERANCE_PIPS = float(os.getenv("GATE_SR_TOLERANCE_PIPS", "2.0"))


class GateSR(BaseGate):
    gate_name = "gate_SR"
    priority = 33

    def __init__(self) -> None:
        self._mids: deque[float] = deque(maxlen=_SR_WINDOW)

    def _find_levels(self, pip_size: float) -> tuple[list[float], list[float]]:
        if len(self._mids) < 30:
            return [], []
        prices = np.array(self._mids)
        tolerance = _SR_TOLERANCE_PIPS * pip_size
        n = len(prices)
        local_max_indices = []
        local_min_indices = []
        for i in range(1, n - 1):
            if prices[i] >= prices[i - 1] and prices[i] >= prices[i + 1]:
                local_max_indices.append(i)
            if prices[i] <= prices[i - 1] and prices[i] <= prices[i + 1]:
                local_min_indices.append(i)
        resistance_levels: list[float] = []
        for idx in local_max_indices:
            price = prices[idx]
            merged = False
            for j, lvl in enumerate(resistance_levels):
                if abs(price - lvl) <= tolerance:
                    resistance_levels[j] = (resistance_levels[j] + price) / 2.0
                    merged = True
                    break
            if not merged:
                resistance_levels.append(float(price))
        support_levels: list[float] = []
        for idx in local_min_indices:
            price = prices[idx]
            merged = False
            for j, lvl in enumerate(support_levels):
                if abs(price - lvl) <= tolerance:
                    support_levels[j] = (support_levels[j] + price) / 2.0
                    merged = True
                    break
            if not merged:
                support_levels.append(float(price))
        return support_levels, resistance_levels

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        if bid <= 0 or ask <= 0:
            return True
        mid = (bid + ask) / 2.0
        self._mids.append(mid)
        pip_size = float(tick.get("pip_size", 0.0001))
        if pip_size <= 0:
            pip_size = 0.0001
        support, resistance = self._find_levels(pip_size)
        proximity_pips = _SR_PIP_PROXIMITY * pip_size
        nearest_support = None
        nearest_resistance = None
        for s in support:
            dist = mid - s
            if 0 < dist <= proximity_pips:
                if nearest_support is None or dist < (mid - nearest_support):
                    nearest_support = s
        for r in resistance:
            dist = r - mid
            if 0 < dist <= proximity_pips:
                if nearest_resistance is None or dist < (nearest_resistance - mid):
                    nearest_resistance = r
        tick["sr_nearest_support"] = nearest_support
        tick["sr_nearest_resistance"] = nearest_resistance
        direction = tick.get("direction", "BUY")
        if direction == "BUY" and nearest_resistance is not None:
            return False
        if direction == "SELL" and nearest_support is not None:
            return False
        return True
