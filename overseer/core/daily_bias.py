import os
import logging
from datetime import datetime, timezone
from collections import deque

log = logging.getLogger(__name__)

_ENABLED = os.getenv("DAILY_BIAS_ENABLED", "true").lower() == "true"
_DXY_CHANGE_PIPS = float(os.getenv("DAILY_BIAS_DXY_PIPS", "5.0"))
_YIELD_CHANGE_THRESHOLD = float(os.getenv("DAILY_BIAS_YIELD_THRESHOLD", "0.02"))


class DailyBias:
    def __init__(self):
        self.bias = {}
        self._dxy_close = None
        self._dxy_current = None
        self._overnight_premium = {}
        self._yield_direction = {}
        self._last_update_date = None
        self._dxy_history = deque(maxlen=200)

    def update_dxy(self, dxy_value):
        self._dxy_current = dxy_value
        self._dxy_history.append(dxy_value)
        if self._dxy_close is None:
            self._dxy_close = dxy_value

    def set_dxy_prior_close(self, close_val):
        self._dxy_close = close_val

    def update_yield_direction(self, symbol, yield_change):
        self._yield_direction[symbol] = yield_change

    def update_overnight_premium(self, symbol, premium):
        self._overnight_premium[symbol] = premium

    def compute_bias(self, symbol):
        if not _ENABLED:
            return "NEUTRAL", 0.0
        direction = "NEUTRAL"
        strength = 0.0
        dxy_dir = 0.0
        if self._dxy_close is not None and self._dxy_current is not None:
            dxy_change = self._dxy_current - self._dxy_close
            dxy_dir = 1.0 if dxy_change > _DXY_CHANGE_PIPS * 0.0001 else (-1.0 if dxy_change < -_DXY_CHANGE_PIPS * 0.0001 else 0.0)
        is_usd_base = symbol.endswith("M6") and symbol.startswith("6J") or symbol in ("6JM6", "6CM6", "6SM6")
        if is_usd_base:
            dxy_signal = dxy_dir
        else:
            dxy_signal = -dxy_dir
        yield_dir = self._yield_direction.get(symbol, 0.0)
        combined = dxy_signal * 0.6 + yield_dir * 0.4
        if combined > 0.3:
            direction = "BUY"
            strength = min(combined, 1.0)
        elif combined < -0.3:
            direction = "SELL"
            strength = min(abs(combined), 1.0)
        self.bias[symbol] = (direction, strength)
        return direction, strength

    def should_block_direction(self, symbol, trade_direction):
        if not _ENABLED:
            return False
        direction, _ = self.bias.get(symbol, ("NEUTRAL", 0.0))
        if direction == "NEUTRAL":
            return False
        return direction != trade_direction

    def get_bonus(self, symbol, trade_direction):
        if not _ENABLED:
            return 0.0
        direction, strength = self.bias.get(symbol, ("NEUTRAL", 0.0))
        if direction == trade_direction:
            return 0.05 * strength
        elif direction != "NEUTRAL":
            return -0.04 * strength
        return 0.0

    def on_new_day(self):
        if self._dxy_current is not None:
            self._dxy_close = self._dxy_current
        self.bias.clear()


daily_bias = DailyBias()
