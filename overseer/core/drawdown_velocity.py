#!/usr/bin/env python3
"""
Drawdown Velocity Monitor — detects accelerating losses
and automatically raises the quality threshold.

When PnL is declining at >$50/trade pace, the system is
trading into an adverse regime. Rather than stopping entirely,
the threshold is raised to reduce trade frequency while
still allowing the highest-conviction signals through.

This is the institutional equivalent of "size down when cold."
"""

import logging
import os
from collections import deque
from typing import Deque, Dict, Optional

LOGGER = logging.getLogger("overseer.drawdown_velocity")

DRAWDOWN_VELOCITY_ENABLED = os.getenv(
    "DRAWDOWN_VELOCITY_ENABLED", "true"
).lower() in ("true", "1", "yes")

VELOCITY_WINDOW = int(os.getenv("DRAWDOWN_VELOCITY_WINDOW", "20"))
VELOCITY_RECENT = int(os.getenv("DRAWDOWN_VELOCITY_RECENT", "5"))
VELOCITY_LONGER = int(os.getenv("DRAWDOWN_VELOCITY_LONGER", "10"))
EMERGENCY_VELOCITY_THRESHOLD = float(
    os.getenv("DRAWDOWN_VELOCITY_THRESHOLD", "-50.0")
)
THRESHOLD_ADJUSTMENT_STEP = float(
    os.getenv("DRAWDOWN_THRESHOLD_ADJUSTMENT", "0.05")
)
MAX_THRESHOLD_ADJUSTMENT = float(
    os.getenv("DRAWDOWN_MAX_THRESHOLD_ADJUSTMENT", "0.15")
)


class DrawdownVelocity:
    """Tracks PnL trajectory velocity and adjusts thresholds."""

    def __init__(self):
        self._pnl_history: Deque[float] = deque(maxlen=VELOCITY_WINDOW)
        self._current_velocity: float = 0.0
        self._threshold_adjustment: float = 0.0
        self._total_trades: int = 0

    def record_pnl(self, pnl: float) -> None:
        """Record a closed trade PnL value."""
        if not DRAWDOWN_VELOCITY_ENABLED:
            return
        self._pnl_history.append(pnl)
        self._total_trades += 1
        self._update_velocity()

    def _update_velocity(self) -> None:
        """Recalculate drawdown velocity from recent PnL."""
        n = len(self._pnl_history)
        if n < VELOCITY_LONGER:
            self._current_velocity = 0.0
            return

        history = list(self._pnl_history)
        recent_start = n - VELOCITY_RECENT
        longer_start = n - VELOCITY_LONGER

        recent_avg = sum(history[recent_start:]) / VELOCITY_RECENT
        longer_avg = sum(history[longer_start:]) / VELOCITY_LONGER

        self._current_velocity = (recent_avg - longer_avg) / VELOCITY_RECENT

        if self._current_velocity < EMERGENCY_VELOCITY_THRESHOLD:
            if self._threshold_adjustment < MAX_THRESHOLD_ADJUSTMENT:
                self._threshold_adjustment = min(
                    MAX_THRESHOLD_ADJUSTMENT,
                    self._threshold_adjustment + THRESHOLD_ADJUSTMENT_STEP,
                )
                LOGGER.warning(
                    "Drawdown velocity emergency: %.2f/trade — raising threshold by %.2f",
                    self._current_velocity,
                    self._threshold_adjustment,
                )
        elif self._current_velocity > 0:
            recovery_step = THRESHOLD_ADJUSTMENT_STEP * 0.5
            self._threshold_adjustment = max(
                0.0, self._threshold_adjustment - recovery_step
            )

    def get_velocity(self) -> float:
        """Current PnL velocity ($/trade)."""
        return self._current_velocity

    def should_raise_threshold(self) -> bool:
        """Whether the quality threshold should be raised."""
        if not DRAWDOWN_VELOCITY_ENABLED:
            return False
        return (
            self._current_velocity < EMERGENCY_VELOCITY_THRESHOLD
            or self._threshold_adjustment > 0.0
        )

    def get_threshold_adjustment(self) -> float:
        """
        Amount to add to the quality threshold.

        Returns 0.0 when velocity is positive (winning).
        Returns up to MAX_THRESHOLD_ADJUSTMENT when losing fast.
        """
        if not DRAWDOWN_VELOCITY_ENABLED:
            return 0.0
        return self._threshold_adjustment

    def get_status(self) -> Dict:
        """Full status dict for dashboards and logging."""
        return {
            "enabled": DRAWDOWN_VELOCITY_ENABLED,
            "velocity": round(self._current_velocity, 2),
            "threshold_adjustment": round(self._threshold_adjustment, 4),
            "total_trades": self._total_trades,
            "pnl_samples": len(self._pnl_history),
            "emergency_active": self._current_velocity < EMERGENCY_VELOCITY_THRESHOLD,
            "emergency_threshold": EMERGENCY_VELOCITY_THRESHOLD,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._pnl_history.clear()
        self._current_velocity = 0.0
        self._threshold_adjustment = 0.0
        self._total_trades = 0


drawdown_velocity = DrawdownVelocity()
