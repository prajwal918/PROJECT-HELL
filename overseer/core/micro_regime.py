#!/usr/bin/env python3
"""
Microstructure Regime Shift Detection — early warning when
market microstructure transitions from one state to another.

Tracks 5 rolling microstructure metrics and compares each to
a 200-tick baseline using z-sores. When any metric deviates
significantly (|z| > 2.5), a regime shift is flagged.

The 5 metrics:
  1. spread_variability    — std of recent spreads vs baseline
  2. delta_autocorrelation — serial correlation of delta
  3. volume_clustering     — concentration of volume in bursts
  4. price_impact          — mid change per unit of volume
  5. quote_intensity       — rate of DOM updates (stuffing proxy)

Regime shifts often precede volatility expansion and are
critical moments to adjust risk or wait for clarity.
"""

import logging
import os
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger("overseer.micro_regime")

MICRO_REGIME_SHIFT_ENABLED = os.getenv(
    "MICRO_REGIME_SHIFT_ENABLED", "true"
).lower() in ("true", "1", "yes")

BASELINE_TICKS = int(os.getenv("MICRO_REGIME_BASELINE_TICKS", "200"))
RECENT_WINDOW = int(os.getenv("MICRO_REGIME_RECENT_WINDOW", "20"))
ZSCORE_THRESHOLD = float(os.getenv("MICRO_REGIME_ZSCORE_THRESHOLD", "2.5"))
MIN_BASELINE_SAMPLES = int(os.getenv("MICRO_REGIME_MIN_BASELINE_SAMPLES", "50"))


class _SymbolState:
    """Per-symbol rolling metric state."""

    __slots__ = (
        "spreads",
        "deltas",
        "volumes",
        "price_changes",
        "quote_counts",
        "shift_detected",
        "warning_metrics",
    )

    def __init__(self):
        self.spreads: Deque[float] = deque(maxlen=BASELINE_TICKS)
        self.deltas: Deque[float] = deque(maxlen=BASELINE_TICKS)
        self.volumes: Deque[float] = deque(maxlen=BASELINE_TICKS)
        self.price_changes: Deque[float] = deque(maxlen=BASELINE_TICKS)
        self.quote_counts: Deque[int] = deque(maxlen=BASELINE_TICKS)
        self.shift_detected: bool = False
        self.warning_metrics: List[str] = []


class MicroRegimeShift:
    """Microstructure regime shift detector."""

    def __init__(self):
        self._states: Dict[str, _SymbolState] = {}

    def _get_state(self, symbol: str) -> _SymbolState:
        if symbol not in self._states:
            self._states[symbol] = _SymbolState()
        return self._states[symbol]

    @staticmethod
    def _autocorr(series: List[float]) -> float:
        """Lag-1 autocorrelation of a series."""
        if len(series) < 4:
            return 0.0
        arr = np.array(series, dtype=float)
        mean = np.mean(arr)
        if np.std(arr) < 1e-12:
            return 0.0
        centered = arr - mean
        num = np.sum(centered[:-1] * centered[1:])
        den = np.sum(centered ** 2)
        if den < 1e-12:
            return 0.0
        return float(num / den)

    @staticmethod
    def _zscore(recent: List[float], baseline: List[float]) -> float:
        """Z-score of recent values vs baseline distribution."""
        if len(baseline) < MIN_BASELINE_SAMPLES:
            return 0.0
        base_arr = np.array(baseline, dtype=float)
        base_mean = float(np.mean(base_arr))
        base_std = float(np.std(base_arr))
        if base_std < 1e-12:
            return 0.0
        recent_arr = np.array(recent, dtype=float)
        recent_mean = float(np.mean(recent_arr))
        return (recent_mean - base_mean) / base_std

    def on_tick(
        self,
        symbol: str,
        spread: float,
        delta: float,
        volume: float,
        price_change: float,
        quote_updates: int,
    ) -> None:
        """Record per-tick microstructure data for a symbol."""
        if not MICRO_REGIME_SHIFT_ENABLED:
            return
        state = self._get_state(symbol)
        state.spreads.append(spread)
        state.deltas.append(delta)
        state.volumes.append(volume)
        state.price_changes.append(price_change)
        state.quote_counts.append(quote_updates)

    def check_shift(
        self, symbol: str
    ) -> Tuple[bool, List[str]]:
        """
        Check if a microstructure regime shift is detected.

        Returns:
            (shift_detected, warning_metrics) — list of metric
            names that triggered the shift warning.
        """
        if not MICRO_REGIME_SHIFT_ENABLED:
            return False, []

        state = self._get_state(symbol)
        n = len(state.spreads)
        if n < MIN_BASELINE_SAMPLES:
            state.shift_detected = False
            state.warning_metrics = []
            return False, []

        recent_start = max(0, n - RECENT_WINDOW)
        warnings = []

        # 1. spread_variability: std of recent spreads vs baseline std
        recent_spreads = list(state.spreads)[recent_start:]
        baseline_spreads = list(state.spreads)
        recent_std = float(np.std(recent_spreads)) if len(recent_spreads) >= 3 else 0.0
        base_std = float(np.std(baseline_spreads))
        if base_std > 1e-12:
            z = (recent_std - base_std) / base_std
            if abs(z) > ZSCORE_THRESHOLD:
                warnings.append("spread_variability")

        # 2. delta_autocorrelation
        recent_deltas = list(state.deltas)[recent_start:]
        baseline_ac = self._autocorr(list(state.deltas))
        recent_ac = self._autocorr(recent_deltas)
        ac_diff = recent_ac - baseline_ac
        if abs(ac_diff) > 0.4:
            warnings.append("delta_autocorrelation")

        # 3. volume_clustering: ratio of max to mean in recent window
        recent_vols = list(state.volumes)[recent_start:]
        baseline_vols = list(state.volumes)
        if len(recent_vols) >= 3 and np.mean(recent_vols) > 0:
            recent_cluster = float(np.max(recent_vols)) / float(np.mean(recent_vols))
            if np.mean(baseline_vols) > 0:
                base_cluster = float(np.max(baseline_vols)) / float(np.mean(baseline_vols))
                if base_cluster > 0:
                    cluster_z = (recent_cluster - base_cluster) / base_cluster
                    if abs(cluster_z) > ZSCORE_THRESHOLD:
                        warnings.append("volume_clustering")

        # 4. price_impact: |price_change| per unit volume
        recent_pc = list(state.price_changes)[recent_start:]
        if len(recent_pc) >= 3 and np.mean(recent_vols) > 0:
            recent_impact = float(np.mean(np.abs(recent_pc))) / float(np.mean(recent_vols))
            baseline_pc = list(state.price_changes)
            if np.mean(baseline_vols) > 0 and len(baseline_pc) >= MIN_BASELINE_SAMPLES:
                base_impact = float(np.mean(np.abs(baseline_pc))) / float(np.mean(baseline_vols))
                if base_impact > 1e-12:
                    impact_z = (recent_impact - base_impact) / base_impact
                    if abs(impact_z) > ZSCORE_THRESHOLD:
                        warnings.append("price_impact")

        # 5. quote_intensity: DOM update rate change
        recent_qc = list(state.quote_counts)[recent_start:]
        baseline_qc = list(state.quote_counts)
        z_qc = self._zscore(recent_qc, baseline_qc)
        if abs(z_qc) > ZSCORE_THRESHOLD:
            warnings.append("quote_intensity")

        shift = len(warnings) > 0
        state.shift_detected = shift
        state.warning_metrics = warnings

        if shift:
            LOGGER.info(
                "Microstructure regime shift detected: %s metrics=%s",
                symbol,
                ",".join(warnings),
            )

        return shift, warnings

    def get_status(self, symbol: str) -> Dict:
        """Full status dict for dashboards."""
        state = self._get_state(symbol)
        return {
            "enabled": MICRO_REGIME_SHIFT_ENABLED,
            "symbol": symbol,
            "samples": len(state.spreads),
            "shift_detected": state.shift_detected,
            "warning_metrics": state.warning_metrics,
            "baseline_ticks": BASELINE_TICKS,
            "zscore_threshold": ZSCORE_THRESHOLD,
        }

    def reset(self, symbol: Optional[str] = None) -> None:
        if symbol:
            self._states.pop(symbol, None)
        else:
            self._states.clear()


micro_regime_shift = MicroRegimeShift()
