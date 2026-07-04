from __future__ import annotations

import numpy as np
from typing import List
from data.models import Candle
from config import MIN_VOLUME_ZSCORE


def calculate_volume_zscore(candles: List[Candle], window: int = 20) -> float:
    """
    Calculates Z-score of current candle volume vs recent rolling mean/std.
    """
    if len(candles) < window + 1:
        return 0.0

    recent_volumes = [c.volume for c in candles[-(window + 1):-1]]
    current_volume = candles[-1].volume

    mean = float(np.mean(recent_volumes))
    std  = float(np.std(recent_volumes))

    if std == 0:
        if current_volume <= mean:
            return 0.0
        return (current_volume - mean) / max(mean * 0.10, 1.0)

    return (current_volume - mean) / std


def is_volume_spike(candles: List[Candle], window: int = 20) -> tuple[bool, float]:
    """Returns (is_spike, zscore)."""
    zscore = calculate_volume_zscore(candles, window)
    return zscore >= MIN_VOLUME_ZSCORE, zscore
