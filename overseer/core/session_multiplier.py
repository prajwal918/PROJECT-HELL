import os
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_ENABLED = os.getenv("SESSION_MULTIPLIER_ENABLED", "true").lower() == "true"


_MULTIPLIERS = {
    "london_ny_overlap": float(os.getenv("MULT_LONDON_NY_OVERLAP", "1.15")),
    "dead_zone": float(os.getenv("MULT_DEAD_ZONE", "0.60")),
    "pre_news_30min": float(os.getenv("MULT_PRE_NEWS", "0.40")),
    "post_news_continuation": float(os.getenv("MULT_POST_NEWS", "1.20")),
    "weekly_level_proximity": float(os.getenv("MULT_WEEKLY_LEVEL", "1.25")),
    "london_fix": float(os.getenv("MULT_LONDON_FIX", "1.08")),
    "asian_dead": float(os.getenv("MULT_ASIAN_DEAD", "0.70")),
}

LONDON_OPEN = 7
NY_OPEN = 13
LONDON_CLOSE = 16
NY_CLOSE = 21
ASIAN_OPEN = 0
ASIAN_CLOSE = 6


def get_session_multiplier(tick, killzone_quality=1.0, near_weekly_level=False, pre_news_minutes=None, post_news_window=False):
    if not _ENABLED:
        return 1.0
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    minute = now_utc.minute
    mult = 1.0
    if LONDON_OPEN <= hour < NY_OPEN:
        mult = 1.05
    elif NY_OPEN <= hour < LONDON_CLOSE:
        mult = _MULTIPLIERS["london_ny_overlap"]
    elif NY_OPEN <= hour < NY_CLOSE:
        mult = 1.05
    elif ASIAN_OPEN <= hour < ASIAN_CLOSE:
        mult = _MULTIPLIERS["asian_dead"]
    elif hour >= ASIAN_CLOSE and hour < LONDON_OPEN:
        mult = _MULTIPLIERS["dead_zone"]
    if 12 <= hour < 14:
        mult = min(mult, _MULTIPLIERS["dead_zone"])
    if near_weekly_level:
        mult *= _MULTIPLIERS["weekly_level_proximity"]
    if pre_news_minutes is not None and pre_news_minutes <= 30:
        mult *= _MULTIPLIERS["pre_news_30min"]
    if post_news_window:
        mult *= _MULTIPLIERS["post_news_continuation"]
    if 15 <= hour and 45 <= minute and hour == 15 and minute <= 55:
        mult *= _MULTIPLIERS["london_fix"]
    mult *= (0.7 + 0.3 * killzone_quality)
    return mult
