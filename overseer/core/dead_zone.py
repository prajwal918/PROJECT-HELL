import os
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_ENABLED = os.getenv("DEAD_ZONE_ENABLED", "true").lower() == "true"
_DEAD_ZONE_START = int(os.getenv("DEAD_ZONE_START_HOUR", "12"))
_DEAD_ZONE_END = int(os.getenv("DEAD_ZONE_END_HOUR", "14"))
_DEAD_ZONE_MULTIPLIER = float(os.getenv("DEAD_ZONE_MULTIPLIER", "0.60"))


def is_dead_zone(now_utc=None):
    if not _ENABLED:
        return False, 1.0
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    if _DEAD_ZONE_START <= hour < _DEAD_ZONE_END:
        return True, _DEAD_ZONE_MULTIPLIER
    return False, 1.0
