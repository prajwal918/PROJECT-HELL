from __future__ import annotations

import numpy as np
from typing import List
from data.models import Candle, VolumeProfile
from config import VOLUME_PROFILE_LOOKBACK


def calculate_volume_profile(candles: List[Candle], bins: int = 50) -> VolumeProfile:
    """
    Calculate Volume Profile from recent candles.
    Returns VAH, VAL, POC — the three key structural levels.
    """
    recent = candles[-VOLUME_PROFILE_LOOKBACK:] if len(candles) >= VOLUME_PROFILE_LOOKBACK else candles

    if len(recent) < 5:
        return None

    price_low  = min(c.low  for c in recent)
    price_high = max(c.high for c in recent)

    if price_high == price_low:
        return None

    price_levels = np.linspace(price_low, price_high, bins)
    volume_at_level = np.zeros(bins)

    for candle in recent:
        for i, price in enumerate(price_levels):
            if candle.low <= price <= candle.high:
                proximity = 1.0 - abs(price - candle.close) / (candle.high - candle.low + 1e-10)
                volume_at_level[i] += candle.volume * max(0.1, proximity)

    poc_index = int(np.argmax(volume_at_level))
    poc = float(price_levels[poc_index])

    total_volume = float(np.sum(volume_at_level))
    target_va_volume = total_volume * 0.70

    upper = poc_index
    lower = poc_index
    accumulated = float(volume_at_level[poc_index])

    while accumulated < target_va_volume:
        upper_add = float(volume_at_level[upper + 1]) if upper + 1 < bins else 0
        lower_add = float(volume_at_level[lower - 1]) if lower - 1 >= 0 else 0

        if upper_add >= lower_add and upper + 1 < bins:
            upper += 1
            accumulated += upper_add
        elif lower - 1 >= 0:
            lower -= 1
            accumulated += lower_add
        else:
            break

    vah = float(price_levels[upper])
    val = float(price_levels[lower])

    return VolumeProfile(
        vah                = vah,
        val                = val,
        poc                = poc,
        value_area_volume  = accumulated
    )
