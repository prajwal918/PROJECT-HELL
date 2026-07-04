from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, Optional, Tuple

LOGGER = logging.getLogger("overseer.ruin_calc")

_ENABLED = os.getenv("RUIN_CALC_ENABLED", "true").lower() == "true"
_RUIN_THRESHOLD = float(os.getenv("RUIN_PROBABILITY_THRESHOLD", "0.01"))
_MIN_TRADES = int(os.getenv("RUIN_MIN_TRADES", "20"))
_DEFAULT_WIN_RATE = float(os.getenv("RUIN_DEFAULT_WIN_RATE", "0.50"))
_DEFAULT_AVG_WIN = float(os.getenv("RUIN_DEFAULT_AVG_WIN", "1.0"))
_DEFAULT_AVG_LOSS = float(os.getenv("RUIN_DEFAULT_AVG_LOSS", "1.0"))
_KELLY_FRACTION = float(os.getenv("RUIN_KELLY_FRACTION", "0.75"))


class RuinCalculator:
    def __init__(self) -> None:
        self._win_rate = _DEFAULT_WIN_RATE
        self._avg_win = _DEFAULT_AVG_WIN
        self._avg_loss = _DEFAULT_AVG_LOSS
        self._n_trades = 0
        self._n_wins = 0
        self._total_win = 0.0
        self._total_loss = 0.0
        self._last_ruin_prob = 0.0

    def update_stats(self, win_rate: float, avg_win: float, avg_loss: float) -> None:
        if not _ENABLED:
            return
        self._win_rate = max(0.001, min(0.999, win_rate))
        self._avg_win = max(0.0001, avg_win)
        self._avg_loss = max(0.0001, avg_loss)

    def update_from_trade(self, pnl: float) -> None:
        if not _ENABLED:
            return
        self._n_trades += 1
        if pnl >= 0:
            self._n_wins += 1
            self._total_win += pnl
        else:
            self._total_loss += abs(pnl)
        if self._n_trades >= _MIN_TRADES:
            self._win_rate = self._n_wins / self._n_trades
            n_losses = self._n_trades - self._n_wins
            if self._n_wins > 0:
                self._avg_win = self._total_win / self._n_wins
            if n_losses > 0:
                self._avg_loss = self._total_loss / n_losses

    def compute_ruin_probability(self, bet_fraction: float) -> float:
        if not _ENABLED:
            return 0.0
        if bet_fraction <= 0.0:
            return 1.0
        if bet_fraction >= 1.0:
            return 1.0
        wr = self._win_rate
        if wr <= 0.0 or wr >= 1.0:
            return 1.0 if wr <= 0.0 else 0.0
        avg_w = self._avg_win
        avg_l = self._avg_loss
        payoff_ratio = avg_w / avg_l if avg_l > 0 else 1.0
        edge = wr * payoff_ratio - (1.0 - wr)
        if edge <= 0:
            p_loss_per_unit = 1.0 - wr
            if p_loss_per_unit <= 0 or p_loss_per_unit >= 1:
                ruin_prob = 1.0
            else:
                ruin_prob = 1.0 - (edge * bet_fraction)
            self._last_ruin_prob = min(1.0, max(0.0, ruin_prob))
            return self._last_ruin_prob
        if wr >= 1.0:
            self._last_ruin_prob = 0.0
            return 0.0
        p_loss = 1.0 - wr
        if p_loss <= 0 or p_loss >= 1:
            self._last_ruin_prob = 0.5
            return self._last_ruin_prob
        try:
            ratio = p_loss / wr
            if ratio <= 0 or ratio >= 1:
                if ratio >= 1:
                    self._last_ruin_prob = 1.0
                else:
                    self._last_ruin_prob = 0.0
                return self._last_ruin_prob
            exponent = 1.0 / bet_fraction
            if exponent > 500:
                ruin_prob = 0.0
            else:
                ruin_prob = ratio ** exponent
        except (OverflowError, ZeroDivisionError, ValueError):
            ruin_prob = 1.0
        self._last_ruin_prob = min(1.0, max(0.0, ruin_prob))
        return self._last_ruin_prob

    def get_safe_size(self, account_balance: float) -> float:
        if not _ENABLED:
            return account_balance * _KELLY_FRACTION
        wr = self._win_rate
        avg_w = self._avg_win
        avg_l = self._avg_loss
        if avg_l <= 0:
            return account_balance * _KELLY_FRACTION
        full_kelly = wr - ((1.0 - wr) / (avg_w / avg_l))
        full_kelly = max(0.0, min(1.0, full_kelly))
        frac_kelly = full_kelly * _KELLY_FRACTION
        bet_fraction = frac_kelly
        ruin_prob = self.compute_ruin_probability(bet_fraction if bet_fraction > 0 else 0.01)
        if ruin_prob > _RUIN_THRESHOLD:
            target_ruin = _RUIN_THRESHOLD
            if self._win_rate > 0.5:
                ratio = (1.0 - self._win_rate) / self._win_rate
                if 0 < ratio < 1:
                    try:
                        max_frac = math.log(target_ruin) / math.log(ratio)
                        bet_fraction = min(bet_fraction, max(1.0 / account_balance if account_balance > 0 else 0.001, max_frac))
                    except (ValueError, ZeroDivisionError):
                        bet_fraction = 0.01
                else:
                    bet_fraction = 0.01
            else:
                bet_fraction = 0.01
        safe_size = account_balance * max(bet_fraction, 0.0)
        safe_size = min(safe_size, account_balance * 0.25)
        return safe_size

    def is_ruin_risk_acceptable(self, bet_fraction: float) -> Tuple[bool, float]:
        prob = self.compute_ruin_probability(bet_fraction)
        return prob <= _RUIN_THRESHOLD, prob

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": _ENABLED,
            "win_rate": round(self._win_rate, 4),
            "avg_win": round(self._avg_win, 4),
            "avg_loss": round(self._avg_loss, 4),
            "n_trades": self._n_trades,
            "last_ruin_prob": round(self._last_ruin_prob, 6),
            "ruin_threshold": _RUIN_THRESHOLD,
        }


ruin_calc = RuinCalculator()
