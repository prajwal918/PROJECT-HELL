"""Bias-weight calibration script for OVERSEER v12.

Analyses historical trade outcomes from the database to suggest optimal
bias weights using a simple grid-search over the parameter space.

Usage::

    python tools/calibrate_biases.py

The script reads all closed trades (where exit_price IS NOT NULL) from
``trade_executions``, replays the L3 signal components stored in
``gate_states_json``, and finds the weight combination that maximises
the Sharpe ratio of the resulting adjusted_score threshold strategy.
"""

from __future__ import annotations

import itertools
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from ml.framework_scorer import aggregate_framework_scores, get_framework_feature_names

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("overseer.calibrate_biases")

_DB_PATH = Path(__file__).resolve().parents[1] / "database" / "overseer_trades.db"

BIAS_NAMES = [
    "BIAS_SPOOF",
    "BIAS_QUEUE",
    "BIAS_ICEBERG",
    "BIAS_ADVERSE",
    "BIAS_HFT",
    "BIAS_VACUUM",
    "BIAS_IV_SKEW",
]

SIGNAL_KEYS = {
    "BIAS_SPOOF": "spoof_reversal_signal",
    "BIAS_QUEUE": "queue_exhaustion_signal",
    "BIAS_ICEBERG": "iceberg_detected",
    "BIAS_ADVERSE": "adverse_selection_risk",
    "BIAS_HFT": "hft_cluster_detected",
    "BIAS_VACUUM": "liquidity_vacuum_signal",
    "BIAS_IV_SKEW": "iv_skew_score",
}

GRID_VALUES = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25]
THRESHOLD = 0.65


def _load_trades() -> list[dict[str, Any]]:
    """Load closed trades with their gate_states_json."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT trade_id, symbol, direction, entry_price, exit_price,
                       pnl, gate_states_json
                FROM trade_executions
                WHERE exit_price IS NOT NULL
                ORDER BY timestamp
                """
            ).fetchall()
    except sqlite3.Error as exc:
        LOGGER.error("Failed to load trades: %s", exc)
        return []

    trades = []
    for row in rows:
        try:
            gate_states = json.loads(row["gate_states_json"]) if row["gate_states_json"] else {}
        except json.JSONDecodeError:
            gate_states = {}

        trades.append({
            "trade_id": row["trade_id"],
            "symbol": row["symbol"],
            "direction": row["direction"],
            "pnl": float(row["pnl"]) if row["pnl"] is not None else 0.0,
            "gate_states": gate_states,
        })

    LOGGER.info("Loaded %d closed trades", len(trades))
    return trades


def _compute_adjusted_score(
    base_score: float,
    l3_signals: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Compute adjusted score given L3 signals and bias weights."""
    adj = base_score
    for bias_name, signal_key in SIGNAL_KEYS.items():
        signal_val = l3_signals.get(signal_key, 0.0)
        weight = weights.get(bias_name, 0.0)
        if bias_name == "BIAS_ADVERSE" or bias_name == "BIAS_VACUUM":
            adj -= signal_val * weight
        elif bias_name == "BIAS_IV_SKEW":
            adj += signal_val * weight
        else:
            adj += signal_val * weight
    return adj


def _sharpe(pnls: list[float]) -> float:
    """Simple Sharpe ratio (assuming zero risk-free rate)."""
    if not pnls:
        return 0.0
    n = len(pnls)
    mean = sum(pnls) / n
    if n < 2:
        return mean
    variance = sum((p - mean) ** 2 for p in pnls) / (n - 1)
    std = variance ** 0.5
    if std < 1e-10:
        return 0.0
    return mean / std


def calibrate() -> dict[str, float]:
    """Run grid-search calibration and return the best weights."""
    trades = _load_trades()
    if len(trades) < 10:
        LOGGER.warning(
            "Only %d closed trades — calibration unreliable. "
            "Need at least 30 trades for meaningful results.",
            len(trades),
        )
        if len(trades) == 0:
            LOGGER.info("Returning default weights.")
            return {
                "BIAS_SPOOF": 0.15, "BIAS_QUEUE": 0.10, "BIAS_ICEBERG": 0.05,
                "BIAS_ADVERSE": 0.20, "BIAS_HFT": 0.08, "BIAS_VACUUM": 0.12,
                "BIAS_IV_SKEW": 0.10,
            }

    best_sharpe = -float("inf")
    best_weights: dict[str, float] = {}

    grid_space = [GRID_VALUES] * len(BIAS_NAMES)
    total_combos = len(GRID_VALUES) ** len(BIAS_NAMES)
    LOGGER.info("Evaluating %d weight combinations ...", total_combos)

    for combo in itertools.product(*grid_space):
        weights = dict(zip(BIAS_NAMES, combo))

        pnls_taken: list[float] = []
        pnls_skipped: list[float] = []

        for trade in trades:
            gs = trade["gate_states"]
            gate_bools = {k: bool(v) for k, v in gs.items()}
            fw_scores = aggregate_framework_scores(gate_bools)
            fw_names = get_framework_feature_names()
            base_score = sum(fw_scores.get(fw, 0.0) for fw in fw_names) / len(fw_names) if fw_names else 0.0

        l3_signals = {
            "spoof_reversal_signal": gs.get("l3_spoof", 0.0),
            "queue_exhaustion_signal": gs.get("l3_queue", 0.0),
            "iceberg_detected": gs.get("l3_iceberg", 0.0),
            "adverse_selection_risk": gs.get("l3_adverse", 0.0),
            "hft_cluster_detected": gs.get("l3_hft", 0.0),
            "liquidity_vacuum_signal": gs.get("l3_vacuum", 0.0),
            "iv_skew_score": gs.get("iv_skew", 0.0),
            }

        adj = _compute_adjusted_score(base_score, l3_signals, weights)

        if adj > THRESHOLD:
            pnls_taken.append(trade["pnl"])
        else:
            pnls_skipped.append(trade["pnl"])

        if not pnls_taken:
            continue

        sharpe = _sharpe(pnls_taken)
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_weights = dict(weights)

    LOGGER.info("Best Sharpe: %.4f", best_sharpe)
    LOGGER.info("Best weights: %s", json.dumps(best_weights, indent=2))

    for name in BIAS_NAMES:
        if name not in best_weights:
            best_weights[name] = 0.0

    return best_weights


if __name__ == "__main__":
    result = calibrate()
    print("\n" + "=" * 60)
    print("RECOMMENDED .env OVERRIDES")
    print("=" * 60)
    for k, v in result.items():
        print(f"  {k}={v:.2f}")
    print()
