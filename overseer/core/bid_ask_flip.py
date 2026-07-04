import os
import logging
from collections import deque

log = logging.getLogger(__name__)

_ENABLED = os.getenv("BID_ASK_FLIP_ENABLED", "true").lower() == "true"
_FLIP_WINDOW = int(os.getenv("BID_ASK_FLIP_WINDOW", "5"))
_FLIP_BONUS = float(os.getenv("BID_ASK_FLIP_BONUS", "0.05"))


class BidAskFlip:
    def __init__(self):
        self._history = {}
        self._flip_detected = {}

    def on_tick(self, symbol, bid_size, ask_size):
        if symbol not in self._history:
            self._history[symbol] = deque(maxlen=_FLIP_WINDOW + 2)
        if bid_size + ask_size == 0:
            return
        ratio = ask_size / (bid_size + ask_size)
        self._history[symbol].append(ratio)

    def detect_flip(self, symbol, trade_direction):
        if not _ENABLED:
            return False, 0.0
        hist = self._history.get(symbol, deque())
        if len(hist) < _FLIP_WINDOW:
            return False, 0.0
        recent = list(hist)
        old_avg = sum(recent[:_FLIP_WINDOW // 2]) / max(1, _FLIP_WINDOW // 2)
        new_avg = sum(recent[_FLIP_WINDOW // 2:]) / max(1, _FLIP_WINDOW // 2 + 1)
        flipped = False
        if old_avg > 0.6 and new_avg < 0.4:
            flipped = True
            flip_dir = "SELL"
        elif old_avg < 0.4 and new_avg > 0.6:
            flipped = True
            flip_dir = "BUY"
        else:
            flip_dir = None
        if flipped and flip_dir == trade_direction:
            self._flip_detected[symbol] = True
            return True, _FLIP_BONUS
        self._flip_detected[symbol] = False
        return False, 0.0


bid_ask_flip = BidAskFlip()
