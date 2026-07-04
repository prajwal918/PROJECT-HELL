#!/usr/bin/env python3
"""
Kalman Price Filter — 2-state Kalman filter for price and velocity.

States: [price, velocity]
The Kalman filter provides:
  - filtered_price: denoised price estimate
  - price_velocity: rate of price change (directional confidence)
  - uncertainty: covariance measure (high = skip signal)

When uncertainty is high, the filter has not converged or the
market is erratic — signals should be skipped.

Uses only numpy (no additional dependencies).
"""

import logging
import os
from typing import Dict, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger("overseer.kalman_tracker")

KALMAN_TRACKER_ENABLED = os.getenv(
    "KALMAN_TRACKER_ENABLED", "true"
).lower() in ("true", "1", "yes")

# Process noise — how much we expect price/velocity to drift
KALMAN_PROCESS_NOISE = float(os.getenv("KALMAN_PROCESS_NOISE", "1e-4"))
# Measurement noise — how noisy the price feed is
KALMAN_MEASUREMENT_NOISE = float(os.getenv("KALMAN_MEASUREMENT_NOISE", "1e-3"))
# Skip signal when uncertainty (P[0,0]) exceeds this
KALMAN_UNCERTAINTY_THRESHOLD = float(
    os.getenv("KALMAN_UNCERTAINTY_THRESHOLD", "0.01")
)
# Velocity confirmation: |velocity| > this confirms direction
KALMAN_VELOCITY_THRESHOLD = float(
    os.getenv("KALMAN_VELOCITY_THRESHOLD", "1e-5")
)


class KalmanPriceFilter:
    """
    2-state Kalman filter for a single symbol.

    State vector: [price, velocity]
    Measurement: [price]
    """

    def __init__(
        self,
        symbol: str,
        process_noise: float = KALMAN_PROCESS_NOISE,
        measurement_noise: float = KALMAN_MEASUREMENT_NOISE,
    ):
        self.symbol = symbol
        self._initialized = False

        # State vector [price, velocity]
        self._x = np.zeros(2, dtype=float)

        # Covariance matrix
        self._P = np.eye(2, dtype=float) * 1.0

        # State transition: price_new = price + velocity * dt
        # dt = 1 tick
        self._F = np.array([[1.0, 1.0], [0.0, 1.0]], dtype=float)

        # Measurement matrix: we observe price only
        self._H = np.array([[1.0, 0.0]], dtype=float)

        # Process noise covariance
        self._Q = np.eye(2, dtype=float) * process_noise

        # Measurement noise covariance
        self._R = np.array([[measurement_noise]], dtype=float)

        self._tick_count = 0

    def update(self, price: float) -> Dict:
        """
        Predict + update cycle for one price observation.

        Returns dict with:
          - filtered_price: denoised price
          - velocity: price change rate per tick
          - uncertainty: P[0,0] (position variance)
          - velocity_confidence: 1 - P[1,1] normalized
          - should_skip: uncertainty > threshold
        """
        if price <= 0:
            return self._last_result()

        if not self._initialized:
            self._x = np.array([price, 0.0], dtype=float)
            self._P = np.eye(2, dtype=float) * 0.01
            self._initialized = True
            self._tick_count = 1
            return self._build_result()

        # === PREDICT ===
        x_pred = self._F @ self._x
        P_pred = self._F @ self._P @ self._F.T + self._Q

        # === UPDATE ===
        z = np.array([price], dtype=float)
        y = z - self._H @ x_pred  # innovation

        S = self._H @ P_pred @ self._H.T + self._R
        if S[0, 0] != 0:
            K = P_pred @ self._H.T @ np.linalg.inv(S)
        else:
            K = np.zeros((2, 1), dtype=float)

        self._x = x_pred + (K @ y).flatten()
        I_KH = np.eye(2) - K @ self._H
        self._P = I_KH @ P_pred @ I_KH.T + K @ self._R @ K.T

        self._tick_count += 1
        return self._build_result()

    def _build_result(self) -> Dict:
        filtered_price = float(self._x[0])
        velocity = float(self._x[1])
        uncertainty = float(self._P[0, 0])
        vel_uncertainty = float(self._P[1, 1])

        should_skip = uncertainty > KALMAN_UNCERTAINTY_THRESHOLD

        return {
            "filtered_price": round(filtered_price, 6),
            "velocity": round(velocity, 8),
            "uncertainty": round(uncertainty, 8),
            "velocity_uncertainty": round(vel_uncertainty, 8),
            "should_skip": should_skip,
            "velocity_confirms_direction": abs(velocity) > KALMAN_VELOCITY_THRESHOLD,
            "ticks": self._tick_count,
        }

    def _last_result(self) -> Dict:
        return {
            "filtered_price": 0.0,
            "velocity": 0.0,
            "uncertainty": 1.0,
            "velocity_uncertainty": 1.0,
            "should_skip": True,
            "velocity_confirms_direction": False,
            "ticks": 0,
        }

    def get_state(self) -> Tuple[float, float, float]:
        """Quick access: (filtered_price, velocity, uncertainty)."""
        return (
            float(self._x[0]),
            float(self._x[1]),
            float(self._P[0, 0]),
        )


class KalmanTracker:
    """
    Manager for per-symbol KalmanPriceFilter instances.

    Provides a unified interface for all symbols.
    """

    def __init__(self):
        self._filters: Dict[str, KalmanPriceFilter] = {}

    def _get_filter(self, symbol: str) -> KalmanPriceFilter:
        if symbol not in self._filters:
            self._filters[symbol] = KalmanPriceFilter(symbol)
        return self._filters[symbol]

    def update(self, symbol: str, price: float) -> Dict:
        """Update Kalman filter for a symbol with new price."""
        if not KALMAN_TRACKER_ENABLED:
            return {
                "filtered_price": price,
                "velocity": 0.0,
                "uncertainty": 0.0,
                "should_skip": False,
                "velocity_confirms_direction": False,
                "ticks": 0,
            }
        kf = self._get_filter(symbol)
        return kf.update(price)

    def get_filtered_price(self, symbol: str) -> float:
        """Get latest filtered price for a symbol."""
        if symbol not in self._filters:
            return 0.0
        return float(self._filters[symbol]._x[0])

    def get_velocity(self, symbol: str) -> float:
        """Get latest price velocity for a symbol."""
        if symbol not in self._filters:
            return 0.0
        return float(self._filters[symbol]._x[1])

    def get_uncertainty(self, symbol: str) -> float:
        """Get current position uncertainty for a symbol."""
        if symbol not in self._filters:
            return 1.0
        return float(self._filters[symbol]._P[0, 0])

    def should_skip_signal(self, symbol: str) -> bool:
        """Whether to skip a signal due to high price uncertainty."""
        if not KALMAN_TRACKER_ENABLED:
            return False
        if symbol not in self._filters:
            return True  # Not initialized yet
        return float(self._filters[symbol]._P[0, 0]) > KALMAN_UNCERTAINTY_THRESHOLD

    def velocity_confirms(self, symbol: str, direction: str) -> bool:
        """Check if velocity confirms the proposed trade direction."""
        if not KALMAN_TRACKER_ENABLED:
            return True  # Don't block if disabled
        if symbol not in self._filters:
            return False
        vel = float(self._filters[symbol]._x[1])
        if direction == "BUY":
            return vel > KALMAN_VELOCITY_THRESHOLD
        elif direction == "SELL":
            return vel < -KALMAN_VELOCITY_THRESHOLD
        return False

    def get_status(self, symbol: str) -> Dict:
        """Full status for dashboards."""
        if symbol not in self._filters:
            return {
                "enabled": KALMAN_TRACKER_ENABLED,
                "symbol": symbol,
                "initialized": False,
            }
        kf = self._filters[symbol]
        return {
            "enabled": KALMAN_TRACKER_ENABLED,
            "symbol": symbol,
            "initialized": kf._initialized,
            "filtered_price": round(float(kf._x[0]), 6),
            "velocity": round(float(kf._x[1]), 8),
            "uncertainty": round(float(kf._P[0, 0]), 8),
            "ticks": kf._tick_count,
        }

    def get_all_status(self) -> Dict[str, Dict]:
        """Status for all tracked symbols."""
        return {sym: self.get_status(sym) for sym in self._filters}

    def reset(self, symbol: Optional[str] = None) -> None:
        if symbol:
            self._filters.pop(symbol, None)
        else:
            self._filters.clear()


kalman_tracker = KalmanTracker()
