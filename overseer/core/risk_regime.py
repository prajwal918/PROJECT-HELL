"""VIX / Risk-Regime Feed for OVERSEER v12.

``RiskRegimeClassifier`` determines the current risk regime using either
a live VIX value (if available) or proxy signals derived from spread
widening, tick-velocity changes, and cross-asset correlation breakdown.

Framework 15 thresholds:
    VIX < 14  → risk_on   (support AUD/NZD longs)
    14 ≤ VIX ≤ 22  → neutral
    VIX > 22  → risk_off  (suppress AUD/NZD longs, favour JPY/CHF)
"""

from __future__ import annotations

import logging
import math
import os
import statistics
from collections import deque
from typing import Any

LOGGER = logging.getLogger("overseer.risk_regime")

# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------

_VIX_RISK_ON = float(os.getenv("VIX_RISK_ON_THRESHOLD", "14"))
_VIX_RISK_OFF = float(os.getenv("VIX_RISK_OFF_THRESHOLD", "22"))

_PROXY_BASELINE_VIX = float(os.getenv("PROXY_BASELINE_VIX", "16"))
_SPREAD_COEFF = float(os.getenv("PROXY_SPREAD_COEFF", "3.0"))
_VELOCITY_COEFF = float(os.getenv("PROXY_VELOCITY_COEFF", "2.0"))
_CORRELATION_COEFF = float(os.getenv("PROXY_CORRELATION_COEFF", "8.0"))

_BASELINE_WINDOW = int(os.getenv("RISK_BASELINE_WINDOW", "200"))
_CORRELATION_THRESHOLD = float(os.getenv("RISK_CORR_THRESHOLD", "0.5"))


class RiskRegimeClassifier:
    """Classify the current market regime as risk-on / neutral / risk-off.

    Parameters
    ----------
    vix_value : float or None
        If a VIX value is available at init time (e.g. from ``.env``
        ``VIX_VALUE`` setting), pass it here.  Otherwise the classifier
        will use proxy estimation.
    """

    def __init__(self, vix_value: float | None = None) -> None:
        # Explicit VIX
        self._vix: float | None = vix_value
        if self._vix is None:
            env_vix = os.getenv("VIX_VALUE", "18.0")
            if env_vix:
                try:
                    self._vix = float(env_vix)
                    LOGGER.info("VIX initialised from .env: %.2f", self._vix)
                except ValueError:
                    pass

        # Spread data per symbol (rolling baseline + recent)
        self._spread_baseline: dict[str, deque[float]] = {}
        self._spread_recent: dict[str, deque[float]] = {}

        # Tick velocity per symbol
        self._velocity_baseline: dict[str, deque[float]] = {}
        self._velocity_recent: dict[str, deque[float]] = {}

        # Correlation pairs
        self._correlations: dict[tuple[str, str], float] = {}

        # Cached classification
        self._cached_regime: str = "neutral"
        self._cached_score: int = 0
        self._proxy_vix: float = _PROXY_BASELINE_VIX

        LOGGER.info(
            "RiskRegimeClassifier initialised  vix=%s  thresholds=(%s, %s)",
            self._vix, _VIX_RISK_ON, _VIX_RISK_OFF,
        )

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------

    def update_vix(self, value: float) -> None:
        """Manually set/update the VIX value from an external source."""
        self._vix = value
        LOGGER.debug("VIX updated to %.2f", value)
        self._recalculate()

    def update_spread(self, symbol: str, spread: float) -> None:
        """Feed a new spread observation for *symbol*."""
        sym = symbol.upper()
        if sym not in self._spread_baseline:
            self._spread_baseline[sym] = deque(maxlen=_BASELINE_WINDOW)
            self._spread_recent[sym] = deque(maxlen=20)
        self._spread_baseline[sym].append(spread)
        self._spread_recent[sym].append(spread)
        self._recalculate()

    def update_tick_velocity(self, symbol: str, ticks_per_second: float) -> None:
        """Feed a new tick-velocity observation for *symbol*."""
        sym = symbol.upper()
        if sym not in self._velocity_baseline:
            self._velocity_baseline[sym] = deque(maxlen=_BASELINE_WINDOW)
            self._velocity_recent[sym] = deque(maxlen=20)
        self._velocity_baseline[sym].append(ticks_per_second)
        self._velocity_recent[sym].append(ticks_per_second)
        self._recalculate()

    def update_correlation(self, pair_a: str, pair_b: str, correlation: float) -> None:
        """Feed a correlation measurement between two symbols."""
        key = (pair_a.upper(), pair_b.upper())
        self._correlations[key] = correlation
        self._recalculate()

    # ------------------------------------------------------------------
    # Proxy VIX estimation
    # ------------------------------------------------------------------

    def _estimate_proxy_vix(self) -> float:
        """Estimate a VIX-equivalent value from proxy signals.

        proxy_vix = baseline + spread_z * coeff + velocity_z * coeff
                    + correlation_breakdown * coeff

        A higher proxy_vix means more stress → risk_off.
        """
        spread_z = self._calc_spread_z_score()
        velocity_z = self._calc_velocity_z_score()
        corr_breakdown = self._calc_correlation_breakdown()

        proxy = (
            _PROXY_BASELINE_VIX
            + spread_z * _SPREAD_COEFF
            + velocity_z * _VELOCITY_COEFF
            + corr_breakdown * _CORRELATION_COEFF
        )
        # Clamp to reasonable range
        proxy = max(8.0, min(80.0, proxy))
        self._proxy_vix = round(proxy, 2)
        return self._proxy_vix

    def _calc_spread_z_score(self) -> float:
        """Average z-score of recent spreads vs baseline across all symbols."""
        z_scores: list[float] = []
        for sym in self._spread_baseline:
            baseline = self._spread_baseline[sym]
            recent = self._spread_recent.get(sym)
            if not baseline or len(baseline) < 30 or not recent:
                continue
            bl_list = list(baseline)
            bl_mean = statistics.mean(bl_list)
            bl_std = statistics.stdev(bl_list) if len(bl_list) > 1 else 1e-10
            if bl_std < 1e-10:
                continue
            recent_mean = statistics.mean(list(recent))
            z_scores.append((recent_mean - bl_mean) / bl_std)

        return statistics.mean(z_scores) if z_scores else 0.0

    def _calc_velocity_z_score(self) -> float:
        """Average z-score of recent tick velocity vs baseline."""
        z_scores: list[float] = []
        for sym in self._velocity_baseline:
            baseline = self._velocity_baseline[sym]
            recent = self._velocity_recent.get(sym)
            if not baseline or len(baseline) < 30 or not recent:
                continue
            bl_list = list(baseline)
            bl_mean = statistics.mean(bl_list)
            bl_std = statistics.stdev(bl_list) if len(bl_list) > 1 else 1e-10
            if bl_std < 1e-10:
                continue
            recent_mean = statistics.mean(list(recent))
            z_scores.append((recent_mean - bl_mean) / bl_std)

        return statistics.mean(z_scores) if z_scores else 0.0

    def _calc_correlation_breakdown(self) -> float:
        """Fraction of pair correlations that have broken down (|r| < threshold)."""
        if not self._correlations:
            return 0.0
        broken = sum(
            1 for r in self._correlations.values() if abs(r) < _CORRELATION_THRESHOLD
        )
        return broken / len(self._correlations)

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _recalculate(self) -> None:
        """Re-derive regime from VIX or proxy."""
        vix = self._vix if self._vix is not None else self._estimate_proxy_vix()

        if vix < _VIX_RISK_ON:
            self._cached_regime = "risk_on"
            self._cached_score = 1
        elif vix > _VIX_RISK_OFF:
            self._cached_regime = "risk_off"
            self._cached_score = -1
        else:
            self._cached_regime = "neutral"
            self._cached_score = 0

    def classify(self) -> str:
        """Return the current risk regime.

        Returns:
            ``'risk_on'``, ``'risk_off'``, or ``'neutral'``.
        """
        self._recalculate()
        return self._cached_regime

    def get_regime_score(self) -> int:
        """Return a numeric regime score.

        Returns:
            -1 → risk_off  (suppress AUD/NZD longs, favour JPY/CHF)
             0 → neutral
            +1 → risk_on   (support AUD/NZD longs)
        """
        self._recalculate()
        return self._cached_score

    def get_detailed_regime(self) -> dict[str, Any]:
        """Return a comprehensive regime summary dict."""
        self._recalculate()
        spread_z = self._calc_spread_z_score()
        velocity_z = self._calc_velocity_z_score()
        corr_breakdown = self._calc_correlation_breakdown()

        # Classify individual signals
        def _signal(z: float) -> str:
            if z > 1.5:
                return "elevated"
            if z > 0.5:
                return "slightly_elevated"
            if z < -0.5:
                return "subdued"
            return "normal"

        # Confidence based on data availability
        data_points = sum(len(d) for d in self._spread_baseline.values())
        data_points += sum(len(d) for d in self._velocity_baseline.values())
        data_points += len(self._correlations)
        confidence = min(1.0, data_points / 500.0) if self._vix is None else 0.95

        return {
            "regime": self._cached_regime,
            "score": self._cached_score,
            "vix_value": self._vix,
            "proxy_vix": self._proxy_vix,
            "spread_signal": _signal(spread_z),
            "velocity_signal": _signal(velocity_z),
            "correlation_signal": (
                "breakdown" if corr_breakdown > 0.4
                else "weakening" if corr_breakdown > 0.2
                else "intact"
            ),
            "confidence": round(confidence, 2),
        }

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"RiskRegimeClassifier(regime={self._cached_regime!r}, "
            f"score={self._cached_score}, vix={self._vix}, "
            f"proxy_vix={self._proxy_vix})"
        )


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    print("=" * 60)
    print("OVERSEER — Risk Regime Classifier (demo)")
    print("=" * 60)

    # Demo 1: Direct VIX
    print("\n--- With VIX = 12 (risk-on) ---")
    clf = RiskRegimeClassifier(vix_value=12.0)
    print(f"  classify()  = {clf.classify()}")
    print(f"  score()     = {clf.get_regime_score()}")
    print(f"  detailed()  = {clf.get_detailed_regime()}")

    print("\n--- With VIX = 28 (risk-off) ---")
    clf.update_vix(28.0)
    print(f"  classify()  = {clf.classify()}")
    print(f"  score()     = {clf.get_regime_score()}")

    # Demo 2: Proxy estimation
    print("\n--- Proxy mode (no VIX) ---")
    clf2 = RiskRegimeClassifier()

    # Feed normal spreads for baseline
    import random
    for i in range(250):
        clf2.update_spread("EURUSD", 0.00012 + random.gauss(0, 0.00001))
        clf2.update_spread("GBPUSD", 0.00015 + random.gauss(0, 0.00002))
        clf2.update_tick_velocity("EURUSD", 5.0 + random.gauss(0, 0.5))

    print(f"  Baseline regime: {clf2.classify()}")
    print(f"  Proxy VIX: {clf2._proxy_vix}")

    # Simulate stress: spreads widen
    for i in range(25):
        clf2.update_spread("EURUSD", 0.00035 + random.gauss(0, 0.00003))
        clf2.update_spread("GBPUSD", 0.00045 + random.gauss(0, 0.00004))
        clf2.update_tick_velocity("EURUSD", 15.0 + random.gauss(0, 2.0))

    # Add correlation breakdown
    clf2.update_correlation("EURUSD", "GBPUSD", 0.3)
    clf2.update_correlation("EURUSD", "AUDUSD", 0.2)
    clf2.update_correlation("GBPUSD", "NZDUSD", 0.85)

    print(f"\n  After stress:")
    print(f"  classify()  = {clf2.classify()}")
    print(f"  score()     = {clf2.get_regime_score()}")
    detailed = clf2.get_detailed_regime()
    for k, v in detailed.items():
        print(f"    {k}: {v}")

    print("\nDone.")
