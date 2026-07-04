import os
import logging
from collections import deque

log = logging.getLogger(__name__)

_ENABLED = os.getenv("SPREAD_VELOCITY_ENABLED", "true").lower() == "true"
_COMPRESSING_BONUS = float(os.getenv("SPREAD_VELOCITY_COMPRESSING_BONUS", "0.03"))
_EXPANDING_PENALTY = float(os.getenv("SPREAD_VELOCITY_EXPANDING_PENALTY", "-0.03"))
_WINDOW = int(os.getenv("SPREAD_VELOCITY_WINDOW", "10"))


class SpreadVelocity:
    def __init__(self):
        self._spreads = {}

    def on_tick(self, symbol, spread_bps):
        if symbol not in self._spreads:
            self._spreads[symbol] = deque(maxlen=_WINDOW + 2)
        self._spreads[symbol].append(spread_bps)

    def get_velocity(self, symbol):
        spreads = self._spreads.get(symbol, deque())
        if len(spreads) < _WINDOW:
            return 0.0, 0.0
        recent = list(spreads)
        current = recent[-1]
        old = recent[-_WINDOW]
        velocity = current - old
        return velocity, current

    def get_bonus(self, symbol):
        if not _ENABLED:
            return 0.0
        velocity, current = self.get_velocity(symbol)
        if velocity < -0.5:
            return _COMPRESSING_BONUS
        elif velocity > 1.0:
            return _EXPANDING_PENALTY
        return 0.0


spread_velocity = SpreadVelocity()
