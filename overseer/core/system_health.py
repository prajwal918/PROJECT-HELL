import os
import logging

log = logging.getLogger(__name__)

_ENABLED = os.getenv("SYSTEM_HEALTH_FILTER_ENABLED", "true").lower() == "true"
_CPU_THRESHOLD = float(os.getenv("SYSTEM_HEALTH_CPU_THRESHOLD", "80.0"))
_MEM_THRESHOLD = float(os.getenv("SYSTEM_HEALTH_MEM_THRESHOLD", "85.0"))


def get_system_health():
    if not _ENABLED:
        return 1.0
    try:
        import psutil
        cpu_pct = psutil.cpu_percent(interval=0.1)
        mem_pct = psutil.virtual_memory().percent
        health = 1.0
        if cpu_pct > _CPU_THRESHOLD:
            health *= 0.85
            log.warning(f"SystemHealth: CPU at {cpu_pct:.0f}% — signal staleness risk")
        if mem_pct > _MEM_THRESHOLD:
            health *= 0.90
            log.warning(f"SystemHealth: Memory at {mem_pct:.0f}% — pipeline degradation risk")
        return health
    except ImportError:
        return 1.0


def should_skip_entry():
    if not _ENABLED:
        return False
    health = get_system_health()
    return health < 0.80
