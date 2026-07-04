#!/usr/bin/env python3
"""
Layer Performance Tracking — measure the actual lift each bonus
layer provides and auto-adjust weights.

When multiple bonus layers are active (legendary, gate combos,
initial balance, MM spread, etc.), we need to know which ones
actually improve win rate and which are noise.

Per-layer lift = wr_with_layer - wr_without_layer

If a layer has negative lift: auto-disable it.
If a layer has +8% lift: increase its bonus weight.

This is the feedback loop that turns theoretical edges into
measured, validated edges.
"""

import logging
import os
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

LOGGER = logging.getLogger("overseer.layer_performance")

LAYER_PERFORMANCE_ENABLED = os.getenv(
    "LAYER_PERFORMANCE_ENABLED", "true"
).lower() in ("true", "1", "yes")

LAYER_LIFT_DISABLE_THRESHOLD = float(
    os.getenv("LAYER_LIFT_DISABLE_THRESHOLD", "-0.05")
)
LAYER_LIFT_BOOST_THRESHOLD = float(
    os.getenv("LAYER_LIFT_BOOST_THRESHOLD", "0.08")
)
LAYER_MIN_SAMPLES = int(os.getenv("LAYER_MIN_SAMPLES", "20"))
LAYER_WEIGHT_BOOST_STEP = float(
    os.getenv("LAYER_WEIGHT_BOOST_STEP", "0.02")
)
LAYER_WEIGHT_MAX = float(os.getenv("LAYER_WEIGHT_MAX", "0.15"))
LAYER_WEIGHT_DEFAULT = float(os.getenv("LAYER_WEIGHT_DEFAULT", "0.05"))

# Known bonus layers in the OVERSEER system
DEFAULT_LAYERS = [
    "legendary",
    "gate_combo",
    "initial_balance",
    "mm_spread",
    "kalman",
    "killzone_peak",
    "psych_level",
    "session_level",
    "fundamental",
]


class LayerPerformanceTracker:
    """Track per-layer lift and auto-adjust weights."""

    def __init__(self):
        # Per-layer: {layer_name: {"with": [outcomes], "without": [outcomes]}}
        self._outcomes: Dict[str, Dict[str, List[bool]]] = {}
        # Per-layer weights and enabled status
        self._weights: Dict[str, float] = {}
        self._enabled: Dict[str, bool] = {}
        # Initialize known layers
        for layer in DEFAULT_LAYERS:
            self._ensure_layer(layer)

    def _ensure_layer(self, layer_name: str) -> None:
        """Initialize tracking state for a layer."""
        if layer_name not in self._outcomes:
            self._outcomes[layer_name] = {"with": [], "without": []}
        if layer_name not in self._weights:
            self._weights[layer_name] = LAYER_WEIGHT_DEFAULT
        if layer_name not in self._enabled:
            self._enabled[layer_name] = True

    def record_trade(
        self,
        layers_active: List[str],
        outcome: str,
    ) -> None:
        """
        Record a closed trade with which layers were active.

        Args:
            layers_active: list of layer names that were active
            outcome: "WIN", "LOSS", or "FLAT"
        """
        if not LAYER_PERFORMANCE_ENABLED:
            return

        if outcome == "FLAT":
            return

        is_win = outcome == "WIN"
        active_set = set(layers_active)

        # Record for ALL known layers + any new ones
        all_layers = set(self._outcomes.keys()) | active_set
        for layer in all_layers:
            self._ensure_layer(layer)
            if layer in active_set:
                self._outcomes[layer]["with"].append(is_win)
            else:
                self._outcomes[layer]["without"].append(is_win)

        self._auto_adjust()

    def _auto_adjust(self) -> None:
        """Auto-adjust layer weights and enabled status based on lift."""
        for layer_name, data in self._outcomes.items():
            with_wins = sum(data["with"])
            with_total = len(data["with"])
            without_wins = sum(data["without"])
            without_total = len(data["without"])

            if with_total < LAYER_MIN_SAMPLES:
                continue

            wr_with = with_wins / with_total if with_total > 0 else 0.0
            wr_without = (
                without_wins / without_total if without_total > 0 else 0.0
            )
            lift = wr_with - wr_without

            # Disable layers with negative lift
            if lift < LAYER_LIFT_DISABLE_THRESHOLD and with_total >= LAYER_MIN_SAMPLES:
                if self._enabled.get(layer_name, True):
                    self._enabled[layer_name] = False
                    LOGGER.warning(
                        "Layer %s auto-disabled: lift=%.4f (wr_with=%.2f wr_without=%.2f n=%d)",
                        layer_name,
                        lift,
                        wr_with,
                        wr_without,
                        with_total,
                    )

            # Boost layers with strong positive lift
            if lift > LAYER_LIFT_BOOST_THRESHOLD and with_total >= LAYER_MIN_SAMPLES:
                current_weight = self._weights.get(layer_name, LAYER_WEIGHT_DEFAULT)
                new_weight = min(
                    LAYER_WEIGHT_MAX,
                    current_weight + LAYER_WEIGHT_BOOST_STEP,
                )
                if new_weight > current_weight:
                    self._weights[layer_name] = new_weight
                    LOGGER.info(
                        "Layer %s weight boosted: %.4f -> %.4f (lift=%.4f n=%d)",
                        layer_name,
                        current_weight,
                        new_weight,
                        lift,
                        with_total,
                    )

            # Re-enable previously disabled layers if lift recovered
            if lift > 0.0 and not self._enabled.get(layer_name, True):
                self._enabled[layer_name] = True
                LOGGER.info(
                    "Layer %s re-enabled: lift=%.4f recovered",
                    layer_name,
                    lift,
                )

    def get_layer_weight(self, layer_name: str) -> float:
        """Get the current bonus weight for a layer."""
        if not LAYER_PERFORMANCE_ENABLED:
            return LAYER_WEIGHT_DEFAULT
        self._ensure_layer(layer_name)
        return self._weights.get(layer_name, LAYER_WEIGHT_DEFAULT)

    def is_layer_enabled(self, layer_name: str) -> bool:
        """Check if a layer is currently enabled."""
        if not LAYER_PERFORMANCE_ENABLED:
            return True
        self._ensure_layer(layer_name)
        return self._enabled.get(layer_name, True)

    def get_layer_stats(self, layer_name: str) -> Dict:
        """Detailed stats for a single layer."""
        self._ensure_layer(layer_name)
        data = self._outcomes.get(layer_name, {"with": [], "without": []})

        with_wins = sum(data["with"])
        with_total = len(data["with"])
        without_wins = sum(data["without"])
        without_total = len(data["without"])

        wr_with = with_wins / with_total if with_total > 0 else None
        wr_without = without_wins / without_total if without_total > 0 else None
        lift = (wr_with - wr_without) if (wr_with is not None and wr_without is not None) else None

        return {
            "layer": layer_name,
            "enabled": self._enabled.get(layer_name, True),
            "weight": self._weights.get(layer_name, LAYER_WEIGHT_DEFAULT),
            "wr_with": round(wr_with, 4) if wr_with is not None else None,
            "wr_without": round(wr_without, 4) if wr_without is not None else None,
            "lift": round(lift, 4) if lift is not None else None,
            "with_samples": with_total,
            "without_samples": without_total,
        }

    def get_all_stats(self) -> Dict[str, Dict]:
        """Stats for all tracked layers."""
        return {layer: self.get_layer_stats(layer) for layer in self._outcomes}

    def get_status(self) -> Dict:
        """Summary status for dashboards."""
        enabled_count = sum(1 for v in self._enabled.values() if v)
        total_count = len(self._enabled)
        return {
            "enabled": LAYER_PERFORMANCE_ENABLED,
            "layers_tracked": total_count,
            "layers_enabled": enabled_count,
            "layers_disabled": total_count - enabled_count,
        }

    def reset(self) -> None:
        """Reset all tracking state."""
        self._outcomes.clear()
        self._weights.clear()
        self._enabled.clear()
        for layer in DEFAULT_LAYERS:
            self._ensure_layer(layer)


layer_performance_tracker = LayerPerformanceTracker()
