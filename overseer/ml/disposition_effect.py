import os
import logging

log = logging.getLogger(__name__)

_ENABLED = os.getenv("DISPOSITION_EFFECT_ENABLED", "true").lower() == "true"
_BIG_MOVE_ATR_MULT = float(os.getenv("DISPOSITION_MOVE_ATR_MULT", "1.5"))
_PENALTY_PER_ATR = float(os.getenv("DISPOSITION_PENALTY_PER_ATR", "0.03"))
_MAX_PENALTY = float(os.getenv("DISPOSITION_MAX_PENALTY", "0.10"))


class DispositionEffect:
    def __init__(self):
        self._session_open = {}
        self._atr = {}

    def set_session_open(self, symbol, price):
        self._session_open[symbol] = price

    def set_atr(self, symbol, atr):
        self._atr[symbol] = atr

    def get_penalty(self, symbol, direction, current_price):
        if not _ENABLED:
            return 0.0
        open_price = self._session_open.get(symbol)
        atr = self._atr.get(symbol, 0.001)
        if open_price is None or atr <= 0:
            return 0.0
        move = (current_price - open_price) / atr
        if abs(move) < _BIG_MOVE_ATR_MULT:
            return 0.0
        magnitude = abs(move) - _BIG_MOVE_ATR_MULT + 1.0
        penalty = magnitude * _PENALTY_PER_ATR
        penalty = min(penalty, _MAX_PENALTY)
        if move > 0 and direction == "BUY":
            return -penalty
        elif move < 0 and direction == "SELL":
            return -penalty
        return 0.0


disposition_effect = DispositionEffect()
