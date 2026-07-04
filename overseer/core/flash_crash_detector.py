import os
import logging

log = logging.getLogger(__name__)

_ENABLED = os.getenv("FLASH_CRASH_DETECTOR_ENABLED", "true").lower() == "true"
_PRICE_SIGMA = float(os.getenv("FLASH_CRASH_PRICE_SIGMA", "5.0"))
_VOLUME_MULTIPLIER = float(os.getenv("FLASH_CRASH_VOLUME_MULT", "10.0"))
_SPREAD_MULTIPLIER = float(os.getenv("FLASH_CRASH_SPREAD_MULT", "5.0"))
_HALT_TICKS = int(os.getenv("FLASH_CRASH_HALT_TICKS", "30"))


class FlashCrashDetector:
    def __init__(self):
        self._baseline = {}
        self._halt_until = {}

    def update_baseline(self, symbol, rolling_std, avg_volume, avg_spread):
        self._baseline[symbol] = {
            "std": rolling_std,
            "vol": avg_volume,
            "spread": avg_spread,
        }

    def check_tick(self, symbol, price_change, volume, spread, tick_count):
        if not _ENABLED:
            return False
        if tick_count <= self._halt_until.get(symbol, 0):
            return True
        base = self._baseline.get(symbol)
        if base is None or base["std"] <= 0:
            return False
        price_sigma = abs(price_change) / base["std"]
        vol_mult = volume / base["vol"] if base["vol"] > 0 else 0
        spread_mult = spread / base["spread"] if base["spread"] > 0 else 0
        if price_sigma > _PRICE_SIGMA and vol_mult > _VOLUME_MULTIPLIER and spread_mult > _SPREAD_MULTIPLIER:
            self._halt_until[symbol] = tick_count + _HALT_TICKS
            log.warning(f"FLASH CRASH DETECTED: {symbol} sigma={price_sigma:.1f} vol×{vol_mult:.0f} spread×{spread_mult:.0f} — halting {_HALT_TICKS} ticks")
            return True
        return False

    def is_halted(self, symbol, tick_count):
        return tick_count <= self._halt_until.get(symbol, 0)


flash_crash_detector = FlashCrashDetector()
