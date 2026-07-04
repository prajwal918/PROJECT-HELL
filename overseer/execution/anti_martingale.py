import os
import logging

log = logging.getLogger(__name__)

_ENABLED = os.getenv("ANTI_MARTINGALE_ENABLED", "true").lower() == "true"
_WIN_SIZE_UP_PCT = float(os.getenv("ANTI_MARTINGALE_WIN_UP_PCT", "0.05"))
_MAX_WIN_MULT = float(os.getenv("ANTI_MARTINGALE_MAX_WIN_MULT", "1.25"))
_LOSS_SIZE_DOWN_PCT = float(os.getenv("ANTI_MARTINGALE_LOSS_DOWN_PCT", "0.10"))
_MIN_LOSS_MULT = float(os.getenv("ANTI_MARTINGALE_MIN_LOSS_MULT", "0.50"))


class AntiMartingale:
    def __init__(self):
        self._consecutive_wins = 0
        self._consecutive_losses = 0

    def record_outcome(self, pnl):
        if not _ENABLED:
            return
        if pnl > 0:
            self._consecutive_wins += 1
            self._consecutive_losses = 0
        elif pnl < 0:
            self._consecutive_losses += 1
            self._consecutive_wins = 0

    def get_size_multiplier(self):
        if not _ENABLED:
            return 1.0
        if self._consecutive_wins >= 3:
            mult = 1.0 + (self._consecutive_wins - 2) * _WIN_SIZE_UP_PCT
            return min(mult, _MAX_WIN_MULT)
        elif self._consecutive_losses >= 2:
            mult = 1.0 - (self._consecutive_losses - 1) * _LOSS_SIZE_DOWN_PCT
            return max(mult, _MIN_LOSS_MULT)
        return 1.0

    def reset(self):
        self._consecutive_wins = 0
        self._consecutive_losses = 0


anti_martingale = AntiMartingale()
