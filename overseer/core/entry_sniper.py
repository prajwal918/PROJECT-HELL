import os
import logging
from collections import deque

log = logging.getLogger(__name__)

_ENABLED = os.getenv("ENTRY_SNIPER_ENABLED", "true").lower() == "true"
_MAX_WAIT_TICKS = int(os.getenv("ENTRY_SNIPER_MAX_WAIT_TICKS", "5"))
_PULLBACK_PIPS = float(os.getenv("ENTRY_SNIPER_PULLBACK_PIPS", "1.0"))
_MIN_RETRACE_RATIO = float(os.getenv("ENTRY_SNIPER_MIN_RETRACE", "0.3"))


class EntrySniper:
    def __init__(self):
        self._pending = {}
        self._recent_mids = {}

    def register_signal(self, symbol, direction, entry_price, pip_size, tick_count):
        if not _ENABLED:
            return True, entry_price
        key = symbol
        self._pending[key] = {
            "direction": direction,
            "entry_price": entry_price,
            "pip_size": pip_size,
            "tick_count": tick_count,
            "best_price": entry_price,
            "ticks_waited": 0,
        }
        if symbol not in self._recent_mids:
            self._recent_mids[symbol] = deque(maxlen=20)
        self._recent_mids[symbol].append(entry_price)
        return False, None

    def on_tick(self, symbol, mid, pip_size, tick_count):
        if not _ENABLED:
            return None, None
        if symbol in self._recent_mids:
            self._recent_mids[symbol].append(mid)
        if symbol not in self._pending:
            return None, None
        p = self._pending[symbol]
        p["ticks_waited"] += 1
        direction = p["direction"]
        if direction == "BUY":
            if mid < p["best_price"]:
                p["best_price"] = mid
            retrace = p["entry_price"] - mid
            if retrace >= _PULLBACK_PIPS * pip_size:
                fill_price = mid
                del self._pending[symbol]
                return True, fill_price
        else:
            if mid > p["best_price"]:
                p["best_price"] = mid
            retrace = mid - p["entry_price"]
            if retrace >= _PULLBACK_PIPS * pip_size:
                fill_price = mid
                del self._pending[symbol]
                return True, fill_price
        if p["ticks_waited"] >= _MAX_WAIT_TICKS:
            fill_price = mid
            del self._pending[symbol]
            return True, fill_price
        return False, None

    def has_pending(self, symbol):
        return symbol in self._pending

    def cancel(self, symbol):
        self._pending.pop(symbol, None)


entry_sniper = EntrySniper()
