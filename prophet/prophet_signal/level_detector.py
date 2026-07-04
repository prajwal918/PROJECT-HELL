from __future__ import annotations

from typing import Optional, Tuple
from data.models import VolumeProfile
from config import KEY_LEVEL_TOLERANCE_PIPS


def pip_value(asset: str) -> float:
    """Returns pip size for the given asset."""
    asset_upper = asset.upper()
    if "JPY" in asset_upper:
        return 0.01
    if "BTC" in asset_upper or "XBT" in asset_upper:
        return 1.0
    if "XAU" in asset_upper or "GOLD" in asset_upper:
        return 0.1
    return 0.0001


def is_at_key_level(
    current_price: float,
    profile:       VolumeProfile,
    asset:         str,
    tolerance:     int = KEY_LEVEL_TOLERANCE_PIPS
) -> Tuple[bool, Optional[str], float]:
    """
    Checks if price is within tolerance pips of VAH, VAL, or POC.
    """
    pip  = pip_value(asset)
    tol  = tolerance * pip

    levels = {
        "VAH": profile.vah,
        "VAL": profile.val,
        "POC": profile.poc,
    }

    closest_name     = None
    closest_distance = float("inf")

    for name, level in levels.items():
        dist = abs(current_price - level)
        if dist < closest_distance:
            closest_distance = dist
            closest_name     = name

    is_near = closest_distance <= tol
    dist_pips = closest_distance / pip

    return is_near, (closest_name if is_near else None), dist_pips
