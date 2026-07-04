"""Synthetic DXY (USD Index) Calculator for OVERSEER v12.

Computes a synthetic USD Index from live tick data using the standard
DXY geometric-weighted basket formula.  Since we may lack USDSEK, we
redistribute its 4.2 % weight across the remaining five components.

Class ``DXYCalculator``:
    - ``update(symbol, mid_price)`` → call on every tick
    - ``get_dxy_trend()``          → 'strong_up' | 'up' | 'neutral' | 'down' | 'strong_down'
    - ``get_cross_pair_isolation(target_symbol)`` → Framework 12 broad-USD vs idiosyncratic
"""

from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any, Optional

LOGGER = logging.getLogger("overseer.dxy_calculator")

# ---------------------------------------------------------------------------
# DXY basket weights (official ICE weights)
# ---------------------------------------------------------------------------
# Full basket: EUR 57.6%, JPY 13.6%, GBP 11.9%, CAD 9.1%, SEK 4.2%, CHF 3.6%
# Without SEK the remaining weights sum to 95.8%.
# We redistribute proportionally so they sum to 100%.

_FULL_WEIGHTS: dict[str, float] = {
    "EURUSD": -0.576,   # negative exponent (EUR in denominator of USD index)
    "USDJPY":  0.136,
    "GBPUSD": -0.119,   # negative exponent
    "USDCAD":  0.091,
    "USDCHF":  0.036,
}

_WEIGHT_SUM_NO_SEK = sum(abs(w) for w in _FULL_WEIGHTS.values())  # 0.958
_ADJUSTED_WEIGHTS: dict[str, float] = {
    pair: w / _WEIGHT_SUM_NO_SEK for pair, w in _FULL_WEIGHTS.items()
}

# DXY multiplicative constant (ICE reference = 50.14348112)
_DXY_CONSTANT = 50.14348112

# Trend detection
_TREND_WINDOW = int(os.getenv("DXY_TREND_WINDOW", "50"))
_TREND_THRESHOLD = float(os.getenv("DXY_TREND_THRESHOLD", "0.001"))
_DXY_HISTORY_MAXLEN = int(os.getenv("DXY_HISTORY_MAXLEN", "200"))

# ---------------------------------------------------------------------------
# Symbol mapping: futures code → spot pair used in DXY calculation
# ---------------------------------------------------------------------------

_FUTURES_TO_SPOT: dict[str, str] = {
    "6E": "EURUSD",
    "6B": "GBPUSD",
    "6J": "USDJPY",   # 6J is 1/USDJPY, we'll invert
    "6C": "USDCAD",   # 6C is 1/USDCAD, we'll invert
}

# Pairs where the futures price is the *inverse* of the spot convention
_INVERTED_FUTURES: set[str] = {"6J", "6C"}

# Minimum required pairs to compute DXY (EUR, JPY, GBP at minimum)
_MIN_REQUIRED = {"EURUSD", "USDJPY", "GBPUSD"}


class DXYCalculator:
    """Tick-by-tick synthetic DXY calculator."""

    def __init__(self) -> None:
        self._latest: dict[str, float] = {}          # spot pair → latest mid price
        self._dxy_history: deque[float] = deque(maxlen=_DXY_HISTORY_MAXLEN)
        self._pair_histories: dict[str, deque[float]] = {
            pair: deque(maxlen=_DXY_HISTORY_MAXLEN)
            for pair in _ADJUSTED_WEIGHTS
        }
        self._last_dxy: float | None = None
        LOGGER.info(
            "DXYCalculator initialised — adjusted weights (no SEK): %s",
            {k: round(v, 4) for k, v in _ADJUSTED_WEIGHTS.items()},
        )

    # ------------------------------------------------------------------
    # Tick update
    # ------------------------------------------------------------------

    def update(self, symbol: str, mid_price: float) -> float | None:
        """Feed a new tick.  *symbol* can be a futures code or spot pair.

        Returns the recalculated DXY value, or ``None`` if we don't yet
        have enough component prices.
        """
        spot_pair = self._resolve_pair(symbol, mid_price)
        if spot_pair is None:
            return self._last_dxy

        if spot_pair in self._pair_histories:
            self._pair_histories[spot_pair].append(self._latest[spot_pair])

        # Check we have the minimum components
        if not _MIN_REQUIRED.issubset(self._latest):
            return None

        dxy = self._compute_dxy()
        if dxy is not None:
            self._dxy_history.append(dxy)
            self._last_dxy = dxy
        return dxy

    def _resolve_pair(self, symbol: str, mid_price: float) -> str | None:
        """Map *symbol* to its DXY spot-pair name, correcting price if needed."""
        sym_upper = symbol.upper()

        # Direct spot pair
        if sym_upper in _ADJUSTED_WEIGHTS:
            self._latest[sym_upper] = mid_price
            return sym_upper

        # Futures code
        if sym_upper in _FUTURES_TO_SPOT:
            spot = _FUTURES_TO_SPOT[sym_upper]
            if sym_upper in _INVERTED_FUTURES and mid_price > 0:
                # Futures price is 1/spot → invert
                self._latest[spot] = 1.0 / mid_price
            else:
                self._latest[spot] = mid_price
            if spot in self._pair_histories:
                self._pair_histories[spot].append(self._latest[spot])
            return spot  # already stored

        # Also accept USDCHF directly (it's in the basket but has no futures code mapped)
        if sym_upper == "USDCHF":
            self._latest[sym_upper] = mid_price
            return sym_upper

        return None

    def _compute_dxy(self) -> float | None:
        """Geometric-weighted DXY = constant × ∏ pair^weight."""
        try:
            log_sum = 0.0
            for pair, weight in _ADJUSTED_WEIGHTS.items():
                price = self._latest.get(pair)
                if price is None or price <= 0:
                    # Use a reasonable default only if pair is optional
                    if pair in _MIN_REQUIRED:
                        return None
                    continue
                log_sum += weight * math.log(price)
            dxy = _DXY_CONSTANT * math.exp(log_sum)
            return round(dxy, 4)
        except (ValueError, OverflowError) as exc:
            LOGGER.debug("DXY compute error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Trend analysis
    # ------------------------------------------------------------------

    def get_dxy_trend(self) -> str:
        """Classify the recent DXY trajectory.

        Returns one of ``'strong_up'``, ``'up'``, ``'neutral'``,
        ``'down'``, ``'strong_down'``.  Uses linear-regression slope
        over the last ``DXY_TREND_WINDOW`` ticks.
        """
        n = min(len(self._dxy_history), _TREND_WINDOW)
        if n < 5:
            return "neutral"

        values = list(self._dxy_history)[-n:]
        slope = self._linreg_slope(values)

        if slope > 2 * _TREND_THRESHOLD:
            return "strong_up"
        if slope > _TREND_THRESHOLD:
            return "up"
        if slope < -2 * _TREND_THRESHOLD:
            return "strong_down"
        if slope < -_TREND_THRESHOLD:
            return "down"
        return "neutral"

    @staticmethod
    def _linreg_slope(values: list[float]) -> float:
        """Simple OLS slope (avoids numpy dependency in hot path)."""
        n = len(values)
        if n < 2:
            return 0.0
        sx = n * (n - 1) / 2.0        # sum of 0..n-1
        sx2 = n * (n - 1) * (2 * n - 1) / 6.0
        sy = sum(values)
        sxy = sum(i * v for i, v in enumerate(values))
        denom = n * sx2 - sx * sx
        if denom == 0:
            return 0.0
        return (n * sxy - sx * sy) / denom

    # ------------------------------------------------------------------
    # Framework 12 — Cross-pair isolation
    # ------------------------------------------------------------------

    def get_cross_pair_isolation(self, target_symbol: str) -> dict[str, Any]:
        """Determine whether *target_symbol*'s move is broad-USD or idiosyncratic.

        Returns::

            {
                "classification": "broad_usd" | "idiosyncratic" | "mixed",
                "dxy_contribution": float,  # how much DXY move explains the pair move
                "confidence": float,         # 0.0 – 1.0
            }
        """
        result: dict[str, Any] = {
            "classification": "mixed",
            "dxy_contribution": 0.0,
            "confidence": 0.0,
        }

        # Resolve target to spot pair
        target_upper = target_symbol.upper()
        spot = _FUTURES_TO_SPOT.get(target_upper, target_upper)

        # Need enough history
        pair_hist = self._pair_histories.get(spot)
        n_dxy = len(self._dxy_history)
        n_pair = len(pair_hist) if pair_hist else 0
        window = min(n_dxy, n_pair, _TREND_WINDOW)
        if window < 10:
            result["confidence"] = 0.0
            return result

        dxy_vals = list(self._dxy_history)[-window:]
        pair_vals = list(pair_hist)[-window:]  # type: ignore[arg-type]

        dxy_slope = self._linreg_slope(dxy_vals)
        pair_slope = self._linreg_slope(pair_vals)

        # Normalise slopes to comparable scales
        dxy_mean = sum(dxy_vals) / len(dxy_vals) if dxy_vals else 1.0
        pair_mean = sum(pair_vals) / len(pair_vals) if pair_vals else 1.0
        dxy_norm = dxy_slope / dxy_mean if dxy_mean != 0 else 0.0
        pair_norm = pair_slope / pair_mean if pair_mean != 0 else 0.0

        # DXY contribution: how much of the pair move is explained by DXY
        if abs(pair_norm) < 1e-10:
            dxy_contribution = 0.0
        else:
            # For USD-quote pairs (EURUSD, GBPUSD): DXY up → pair down
            # For USD-base pairs (USDJPY, USDCAD): DXY up → pair up
            is_usd_base = spot.startswith("USD")
            if is_usd_base:
                expected_direction = dxy_norm  # same direction
            else:
                expected_direction = -dxy_norm  # opposite direction
            dxy_contribution = expected_direction / pair_norm if abs(pair_norm) > 1e-10 else 0.0
            dxy_contribution = max(-1.0, min(1.0, dxy_contribution))  # clamp

        result["dxy_contribution"] = round(dxy_contribution, 4)

        # Classification
        abs_dxy = abs(dxy_norm)
        abs_pair = abs(pair_norm)

        if abs_dxy > _TREND_THRESHOLD and abs(dxy_contribution) > 0.6:
            result["classification"] = "broad_usd"
            result["confidence"] = min(1.0, abs(dxy_contribution))
        elif abs_dxy < _TREND_THRESHOLD * 0.5 and abs_pair > _TREND_THRESHOLD:
            result["classification"] = "idiosyncratic"
            result["confidence"] = min(1.0, abs_pair / _TREND_THRESHOLD)
        else:
            result["classification"] = "mixed"
            result["confidence"] = 0.5

        return result

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @property
    def current_dxy(self) -> float | None:
        """Latest computed DXY value."""
        return self._last_dxy

    @property
    def history_length(self) -> int:
        return len(self._dxy_history)

    def get_snapshot(self) -> dict[str, Any]:
        """Return a summary dict for logging / dashboards."""
        return {
            "dxy_value": self._last_dxy,
            "trend": self.get_dxy_trend(),
            "history_len": self.history_length,
            "components": {k: v for k, v in self._latest.items()},
        }


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    print("=" * 60)
    print("OVERSEER — Synthetic DXY Calculator (demo)")
    print("=" * 60)

    calc = DXYCalculator()

    # Simulate realistic mid prices
    demo_ticks = [
        ("EURUSD", 1.0850), ("USDJPY", 157.50), ("GBPUSD", 1.2720),
        ("USDCAD", 1.3650), ("USDCHF", 0.9120),
    ]

    for sym, price in demo_ticks:
        dxy = calc.update(sym, price)
        print(f"  update({sym}, {price}) → DXY = {dxy}")

    print(f"\nDXY trend: {calc.get_dxy_trend()}")
    print(f"Snapshot:  {calc.get_snapshot()}")

    # Simulate a trend
    import random
    base_eur = 1.0850
    for i in range(60):
        base_eur -= 0.0002  # EUR weakening → DXY rising
        calc.update("EURUSD", base_eur + random.uniform(-0.0001, 0.0001))
        calc.update("USDJPY", 157.50 + i * 0.02)
        calc.update("GBPUSD", 1.2720 - i * 0.0001)

    print(f"\nAfter 60-tick EUR sell-off:")
    print(f"  DXY = {calc.current_dxy}")
    print(f"  Trend = {calc.get_dxy_trend()}")

    isolation = calc.get_cross_pair_isolation("EURUSD")
    print(f"  EURUSD isolation: {isolation}")

    print("\nDone.")
