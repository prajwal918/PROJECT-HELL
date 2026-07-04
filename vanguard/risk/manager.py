from __future__ import annotations

from datetime import datetime, date
from typing import List
from data.models import TradeRecord
from config import MAX_DAILY_TRADES, MAX_DAILY_LOSS_USD, STAKE_USD
from utils.logger import get_logger

log = get_logger(__name__)


class RiskManager:
    """
    Enforces daily trade and loss limits.
    Must approve every trade before execution.
    """

    def __init__(self):
        self.today_trades:  List[TradeRecord] = []
        self.today_pnl:     float = 0.0
        self._today:        date  = date.today()

    def _reset_if_new_day(self):
        today = date.today()
        if today != self._today:
            self._today       = today
            self.today_trades = []
            self.today_pnl    = 0.0
            log.info("🔄 New trading day — risk counters reset")

    def can_trade(self) -> tuple[bool, str]:
        """
        Returns (allowed, reason).
        Called BEFORE every trade attempt.
        """
        self._reset_if_new_day()

        if len(self.today_trades) >= MAX_DAILY_TRADES:
            return False, f"Daily trade limit reached ({MAX_DAILY_TRADES})"

        if self.today_pnl <= -MAX_DAILY_LOSS_USD:
            return False, f"Daily loss limit hit (${self.today_pnl:.2f})"

        potential_loss = self.today_pnl - STAKE_USD
        if potential_loss <= -MAX_DAILY_LOSS_USD:
            return False, f"Next trade would breach daily loss limit"

        return True, "OK"

    def record_trade(self, record: TradeRecord):
        """Call this after every trade result is received."""
        self._reset_if_new_day()
        self.today_trades.append(record)
        if record.profit is not None:
            self.today_pnl += record.profit

        log.info(
            f"Risk | Trades today: {len(self.today_trades)}/{MAX_DAILY_TRADES} | "
            f"P&L today: ${self.today_pnl:+.2f} / -${MAX_DAILY_LOSS_USD}"
        )

    @property
    def stats(self) -> dict:
        wins   = [t for t in self.today_trades if t.result == "WIN"]
        losses = [t for t in self.today_trades if t.result == "LOSS"]
        return {
            "trades":    len(self.today_trades),
            "wins":      len(wins),
            "losses":    len(losses),
            "win_rate":  len(wins) / max(len(self.today_trades), 1),
            "pnl":       self.today_pnl
        }
