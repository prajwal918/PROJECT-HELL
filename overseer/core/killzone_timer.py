#!/usr/bin/env python3
"""
Kill Zone Precision Timer — WHERE in the kill zone matters.

The first 3 minutes of London open are fundamentally different
from minute 25. Institutional algorithms front-load their orders.

Quality peaks at the session open peak minute, decays toward edges.
Legendary mode only fires in the peak 3-minute window.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional

LOGGER = logging.getLogger("overseer.killzone_timer")

KILL_ZONES = {
    "london_open": {
        "start": (7, 0),
        "end": (7, 30),
        "peak": (7, 2),
        "label": "London Open",
    },
    "london_core": {
        "start": (8, 0),
        "end": (11, 0),
        "peak": (8, 30),
        "label": "London Core",
    },
    "ny_open": {
        "start": (13, 0),
        "end": (13, 30),
        "peak": (13, 3),
        "label": "NY Open",
    },
    "ny_core": {
        "start": (13, 30),
        "end": (17, 0),
        "peak": (14, 0),
        "label": "NY Core",
    },
    "london_close": {
        "start": (15, 30),
        "end": (16, 30),
        "peak": (16, 0),
        "label": "London Close / Fix",
    },
    "asian_open": {
        "start": (0, 0),
        "end": (1, 0),
        "peak": (0, 5),
        "label": "Asian Open",
    },
}

PEAK_TOLERANCE_MINUTES = int(os.getenv("KILLZONE_PEAK_TOLERANCE_MINUTES", "3"))


def get_killzone_quality(utc_now: Optional[datetime] = None) -> Dict:
    """
    Returns quality score 0.0-1.0 based on position within kill zone.
    Peak minute = 1.0. Edges of window = 0.3. Outside = 0.0.
    """
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)

    h, m = utc_now.hour, utc_now.minute
    curr_m = h * 60 + m

    best_zone = None
    best_quality = 0.0

    for zone_name, zone in KILL_ZONES.items():
        start_m = zone["start"][0] * 60 + zone["start"][1]
        end_m = zone["end"][0] * 60 + zone["end"][1]
        peak_m = zone["peak"][0] * 60 + zone["peak"][1]

        if start_m <= curr_m <= end_m:
            window_half = (end_m - start_m) / 2
            if window_half <= 0:
                continue

            distance_from_peak = abs(curr_m - peak_m)
            quality = max(0.3, 1.0 - (distance_from_peak / window_half) * 0.7)

            if quality > best_quality:
                best_quality = quality
                best_zone = {
                    "in_killzone": True,
                    "zone": zone_name,
                    "label": zone["label"],
                    "quality": round(quality, 3),
                    "minutes_from_peak": distance_from_peak,
                    "is_peak_window": distance_from_peak <= PEAK_TOLERANCE_MINUTES,
                    "start": zone["start"],
                    "end": zone["end"],
                    "peak": zone["peak"],
                }

    if best_zone:
        return best_zone

    return {
        "in_killzone": False,
        "zone": None,
        "label": None,
        "quality": 0.0,
        "minutes_from_peak": 999,
        "is_peak_window": False,
    }


def get_session_name(utc_now: Optional[datetime] = None) -> str:
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)

    h = utc_now.hour
    if 0 <= h < 7:
        return "asian"
    elif 7 <= h < 13:
        return "london"
    elif 13 <= h < 22:
        return "new_york"
    else:
        return "dead"


def get_killzone_summary() -> str:
    kz = get_killzone_quality()
    if not kz["in_killzone"]:
        return f"No active kill zone (session: {get_session_name()})"
    peak_str = " [PEAK]" if kz["is_peak_window"] else ""
    return f"{kz['label']} quality={kz['quality']:.2f}{peak_str}"
