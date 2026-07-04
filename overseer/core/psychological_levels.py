#!/usr/bin/env python3
"""
Psychological Price Levels — behavioral finance meets institutional hunting.

Round numbers are not mythology. Every retail stop, limit, and TP
clusters at round numbers. Institutions know this and hunt them
systematically.

Hierarchy:
  BIG_FIGURE    (1.3000)   — most powerful, largest stop cluster
  HALF_FIGURE   (1.2500)   — second tier
  QUARTER_FIGURE (1.2250)  — third tier
  00_LEVEL      (1.2300)   — weakest but still meaningful
"""

import logging
from typing import Dict, Optional

LOGGER = logging.getLogger("overseer.psychological_levels")

LEVEL_HIERARCHY = {
    "BIG_FIGURE": {"pip_tolerance": 5, "significance": 1.0},
    "HALF_FIGURE": {"pip_tolerance": 4, "significance": 0.75},
    "QUARTER_FIGURE": {"pip_tolerance": 3, "significance": 0.50},
    "00_LEVEL": {"pip_tolerance": 2, "significance": 0.25},
}


def classify_level(price: float, pip_size: float) -> Dict:
    """
    Classify which type of psychological level the price is near.
    Returns level type, significance, and whether price is at a level.
    """
    if price <= 0 or pip_size <= 0:
        return {"type": "NONE", "significance": 0.0, "at_level": False, "nearest_level": 0.0}

    pips_from_whole = price / pip_size
    remainder_100 = pips_from_whole % 100

    to_00 = min(remainder_100, 100 - remainder_100)
    to_50 = abs(remainder_100 - 50)
    to_25 = min(abs(remainder_100 - 25), abs(remainder_100 - 75))

    if to_00 <= 5:
        level_type = "BIG_FIGURE"
    elif to_50 <= 4:
        level_type = "HALF_FIGURE"
    elif to_25 <= 3:
        level_type = "QUARTER_FIGURE"
    else:
        level_type = "NONE"

    if level_type == "NONE":
        nearest_00_pips = min(to_00, 100 - to_00)
        nearest_50_pips = to_50
        if nearest_00_pips <= nearest_50_pips:
            nearest_level = (pips_from_whole - remainder_100 + (100 if to_00 > 50 else 0)) * pip_size
            level_type = "00_LEVEL"
        else:
            nearest_level = (pips_from_whole - remainder_100 + 50) * pip_size
            if abs(remainder_100 - 50) <= 4:
                level_type = "HALF_FIGURE"
            else:
                level_type = "00_LEVEL"

    config = LEVEL_HIERARCHY.get(level_type, {})
    significance = config.get("significance", 0)

    if level_type == "00_LEVEL" and to_00 > 2:
        significance = 0.15

    nearest_big = round(price / (100 * pip_size)) * 100 * pip_size

    return {
        "type": level_type,
        "significance": significance,
        "at_level": significance > 0,
        "nearest_big_figure": nearest_big,
        "pips_to_nearest": min(to_00, to_50, to_25) if level_type != "NONE" else to_00,
    }


def get_stop_hunt_probability(
    price: float, direction: str, pip_size: float
) -> Dict:
    """
    Detect if price is approaching a big figure where stops cluster.
    Institutions push price through big figures to grab stops, then reverse.
    """
    if price <= 0 or pip_size <= 0:
        return {"hunt_likely": False, "pips_to_level": 999}

    above = _nearest_level_above(price, pip_size)
    below = _nearest_level_below(price, pip_size)

    pips_to_above = (above - price) / pip_size
    pips_to_below = (price - below) / pip_size

    if pips_to_above < 10 and direction == "SELL":
        return {
            "hunt_likely": True,
            "target_level": above,
            "pips_to_level": round(pips_to_above, 1),
            "reason": "SELL_STOPS_ABOVE_BIG_FIGURE",
            "strength": min(1.0, (10 - pips_to_above) / 10),
        }
    elif pips_to_below < 10 and direction == "BUY":
        return {
            "hunt_likely": True,
            "target_level": below,
            "pips_to_level": round(pips_to_below, 1),
            "reason": "BUY_STOPS_BELOW_BIG_FIGURE",
            "strength": min(1.0, (10 - pips_to_below) / 10),
        }

    return {
        "hunt_likely": False,
        "pips_to_level": round(min(pips_to_above, pips_to_below), 1),
        "target_level": above if pips_to_above < pips_to_below else below,
    }


def _nearest_level_above(price: float, pip_size: float) -> float:
    big_fig = round(price / (100 * pip_size)) * 100 * pip_size
    if big_fig > price:
        return big_fig
    return big_fig + 100 * pip_size


def _nearest_level_below(price: float, pip_size: float) -> float:
    big_fig = round(price / (100 * pip_size)) * 100 * pip_size
    if big_fig < price:
        return big_fig
    return big_fig - 100 * pip_size
