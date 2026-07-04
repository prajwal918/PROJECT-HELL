import os
import logging
from collections import deque

log = logging.getLogger(__name__)

_ENABLED = os.getenv("TAPE_ACCELERATION_ENABLED", "true").lower() == "true"
_LOOKBACK = int(os.getenv("TAPE_ACCELERATION_LOOKBACK", "10"))
_EXHAUSTED_RATIO = float(os.getenv("TAPE_ACCELERATION_EXHAUSTED_RATIO", "0.4"))
_ACCELERATING_RATIO = float(os.getenv("TAPE_ACCELERATION_RATIO", "1.8"))
_ACCELERATION_BONUS = float(os.getenv("TAPE_ACCELERATION_BONUS", "0.04"))


class TapeAcceleration:
    def __init__(self):
        self._velocity = {}

    def on_tick(self, symbol, mid, volume, direction, tick_count):
        if symbol not in self._velocity:
            self._velocity[symbol] = deque(maxlen=_LOOKBACK * 2)
        move = 1 if direction == "BUY" else -1
        self._velocity[symbol].append({"mid": mid, "volume": volume, "dir": move, "tick": tick_count})

    def get_acceleration(self, symbol, trade_direction):
        if not _ENABLED:
            return 1.0, 0.0
        vels = self._velocity.get(symbol, deque())
        if len(vels) < _LOOKBACK:
            return 1.0, 0.0
        recent = list(vels)
        first_half = recent[:len(recent) // 2]
        second_half = recent[len(recent) // 2:]
        if not first_half or not second_half:
            return 1.0, 0.0
        recent_vel = sum(1 for v in second_half if v["dir"] == (1 if trade_direction == "BUY" else -1))
        older_vel = sum(1 for v in first_half if v["dir"] == (1 if trade_direction == "BUY" else -1))
        if older_vel == 0:
            return 1.0, 0.0
        ratio = recent_vel / older_vel
        if ratio >= _ACCELERATING_RATIO:
            return ratio, _ACCELERATION_BONUS
        elif ratio <= _EXHAUSTED_RATIO:
            return ratio, -0.05
        return ratio, 0.0


tape_acceleration = TapeAcceleration()
