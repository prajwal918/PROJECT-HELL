"""signal_logger.py — Comprehensive signal journal for OVERSEER.

Logs every signal (signal-only AND executed) to the signal_log table with:
- 16 framework scores
- L3 order flow features (spoof, queue, iceberg, adverse, HFT, vacuum)
- Bias breakdown
- DOM snapshot
- Tick context (spread, delta, volume, DXY, risk regime, session)
- Outcome tracking (price movement at 10/50/200 ticks after signal)

This creates the dataset needed to:
1. Retrain XGBoost on REAL trade outcomes (not synthetic)
2. Analyze which order flow patterns predict direction
3. Optimize bias weights from live data
4. Dashboard visualization of signal quality over time
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from ml.framework_scorer import aggregate_framework_scores

LOGGER = logging.getLogger("overseer.signal_logger")

_pending_outcomes: dict[int, dict[str, Any]] = {}

_mid_price_history: dict[str, list[tuple[float, int]]] = {}
_MAX_MID_HISTORY = 250


def load_pending_from_db(conn: sqlite3.Connection) -> None:
    """Load signals with NULL outcomes from DB into _pending_outcomes on startup."""
    try:
        rows = conn.execute(
            """
            SELECT id, symbol, direction, tick_bid, tick_ask, framework_scores_json
            FROM signal_log
            WHERE outcome_200ticks IS NULL
            ORDER BY id
            """
        ).fetchall()
        loaded = 0
        for r in rows:
            sig_id = r[0]
            symbol = r[1]
            direction = r[2]
            bid = float(r[3]) if r[3] else 0
            ask = float(r[4]) if r[5] else 0
            entry_mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0
            fw = json.loads(r[5]) if r[5] else {}
            pip_size = 0.0001
            if "JPY" in symbol or symbol.startswith("6J") or symbol.startswith("XAU"):
                pip_size = 0.01
            _pending_outcomes[sig_id] = {
                "symbol": symbol,
                "direction": direction,
                "entry_mid": entry_mid,
                "entry_tick": 0,
                "pip_size": pip_size,
                "tick_count": 0,
                "ticks_seen": 0,
            }
            loaded += 1
        if loaded:
            LOGGER.info("Loaded %d pending signals from DB for outcome tracking", loaded)
    except sqlite3.Error:
        LOGGER.exception("Failed to load pending signals from DB")


def log_signal(
    conn: sqlite3.Connection,
    tick: dict[str, Any],
    direction: str,
    score: float,
    adjusted_score: float,
    gate_states: dict[str, bool],
    l3_info: dict[str, Any],
    bias_breakdown: dict[str, float],
    executed: bool = False,
    entry_price: float | None = None,
    tick_count: int = 0,
) -> int | None:
    """Log a signal to the signal_log table.

    Returns the signal ID for outcome tracking, or None on failure.
    """
    framework_scores = aggregate_framework_scores(gate_states)

    l3_features = {
        "spoof_reversal_signal": l3_info.get("spoof_reversal_signal", l3_info.get("spoof_signal", 0.0)),
        "spoof_volume_vanished": l3_info.get("spoof_volume_vanished", 0.0),
        "queue_exhaustion_signal": l3_info.get("queue_exhaustion_signal", l3_info.get("queue_exhaustion", 0.0)),
        "queue_attrition_pct": l3_info.get("queue_attrition_pct", 0.0),
        "queue_absorbed_volume": l3_info.get("queue_absorbed_volume", 0.0),
        "iceberg_detected": l3_info.get("iceberg_detected", l3_info.get("iceberg_signal", 0.0)),
        "iceberg_replenish_count": l3_info.get("iceberg_replenish_count", 0.0),
        "iceberg_hidden_depth": l3_info.get("iceberg_hidden_depth", 0.0),
        "adverse_selection_risk": l3_info.get("adverse_selection_risk", l3_info.get("adverse_risk", 0.0)),
        "institutional_flight_volume": l3_info.get("institutional_flight_volume", 0.0),
        "adverse_selection_ratio": l3_info.get("adverse_selection_ratio", 0.0),
        "hft_cluster_detected": l3_info.get("hft_cluster_detected", l3_info.get("hft_signal", 0.0)),
        "hft_synchronized_volume": l3_info.get("hft_synchronized_volume", 0.0),
        "liquidity_vacuum_signal": l3_info.get("liquidity_vacuum_signal", l3_info.get("vacuum_signal", 0.0)),
        "liquidity_vacuum_cv": l3_info.get("liquidity_vacuum_cv", 0.0),
        "vacuum_cascade_depth": l3_info.get("vacuum_cascade_depth", 0.0),
        "l3_prediction": l3_info.get("l3_prediction", 0),
        "l3_confidence": l3_info.get("l3_confidence", 0.0),
        "l3_ready": l3_info.get("l3_ready", False),
    }

    bid = float(tick.get("bid", 0))
    ask = float(tick.get("ask", 0))
    mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else float(tick.get("price", 0))
    spread_bps = ((ask - bid) / mid * 10000) if mid > 0 and bid > 0 and ask > 0 else 0.0

    dom = tick.get("dom", {})
    dom_json = json.dumps(dom) if dom else None
    if dom_json and len(dom_json) > 100000:
        dom_json = None

    try:
        cursor = conn.execute(
            """
            INSERT INTO signal_log
            (symbol, direction, score, adjusted_score, executed, entry_price,
             gate_states_json, framework_scores_json, l3_features_json,
             bias_breakdown_json, dom_snapshot_json,
             tick_bid, tick_ask, tick_delta, tick_volume, spread_bps,
             risk_regime, session, dxy, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'live')
            """,
            (
                tick.get("symbol", "?"),
                direction,
                round(score, 6),
                round(adjusted_score, 6),
                1 if executed else 0,
                entry_price,
                json.dumps(gate_states, sort_keys=True),
                json.dumps(framework_scores, sort_keys=True),
                json.dumps(l3_features, sort_keys=True),
                json.dumps(bias_breakdown, sort_keys=True),
                dom_json,
                bid,
                ask,
                float(tick.get("delta", 0)),
                float(tick.get("volume", tick.get("ask_size", 0) + tick.get("bid_size", 0))),
                round(spread_bps, 2),
                tick.get("risk_regime", ""),
                tick.get("session", ""),
                float(tick.get("dxy", 0)),
            ),
        )
        signal_id = cursor.lastrowid

        symbol = tick.get("symbol", "?")
        _pending_outcomes[signal_id] = {
            "symbol": symbol,
            "direction": direction,
            "entry_mid": mid,
            "entry_tick": tick_count,
            "pip_size": float(tick.get("pip_size", 0.0001)),
            "tick_count": 0,
            "ticks_seen": 0,
        }

        LOGGER.info(
            "Signal logged: id=%d %s %s score=%.4f adj=%.4f exec=%s fw_count=%d",
            signal_id, direction, symbol, score, adjusted_score,
            executed, len(framework_scores),
        )
        return signal_id

    except sqlite3.Error:
        LOGGER.exception("Failed to log signal to signal_log")
        return None


def update_mid_price(symbol: str, mid: float, tick_count: int) -> None:
    """Track mid-price history per symbol for outcome calculation."""
    if symbol not in _mid_price_history:
        _mid_price_history[symbol] = []
    history = _mid_price_history[symbol]
    history.append((mid, tick_count))
    if len(history) > _MAX_MID_HISTORY:
        _mid_price_history[symbol] = history[-_MAX_MID_HISTORY:]
    for sig_id, pending in _pending_outcomes.items():
        if pending["symbol"] == symbol:
            pending["ticks_seen"] += 1


def check_outcomes(conn: sqlite3.Connection, tick_count: int) -> None:
    """Evaluate pending signal outcomes at 10/50/200 tick horizons.

    Outcome is "WIN" if price moved in signal direction by >= 1 pip,
    "LOSS" if moved against by >= 1 pip, "FLAT" otherwise.
    """
    if not _pending_outcomes:
        return

    completed_signals: list[int] = []

    for signal_id, pending in list(_pending_outcomes.items()):
        symbol = pending["symbol"]
        history = _mid_price_history.get(symbol, [])
        if not history:
            continue

        entry_mid = pending["entry_mid"]
        if entry_mid <= 0:
            continue

        direction = pending["direction"]
        is_buy = direction == "BUY"

        ticks_elapsed = pending.get("ticks_seen", 0)

        latest_mid = history[-1][0]

        pip_size = pending.get("pip_size", 0.0001)
        if pip_size <= 0:
            if "JPY" in symbol or symbol.startswith("6J") or symbol.startswith("XAU"):
                pip_size = 0.01
            else:
                pip_size = 0.0001
        move_pips = (latest_mid - entry_mid) / pip_size if pip_size > 0 else 0

        if is_buy:
            outcome_now = "WIN" if move_pips >= 1.0 else ("LOSS" if move_pips <= -1.0 else "FLAT")
        else:
            outcome_now = "WIN" if move_pips <= -1.0 else ("LOSS" if move_pips >= 1.0 else "FLAT")

        updates: dict[str, str] = {}
        if pending.get("outcome_10") is None and ticks_elapsed >= 10:
            updates["outcome_10ticks"] = outcome_now
            pending["outcome_10"] = outcome_now
        if pending.get("outcome_50") is None and ticks_elapsed >= 50:
            updates["outcome_50ticks"] = outcome_now
            pending["outcome_50"] = outcome_now
        if pending.get("outcome_200") is None and ticks_elapsed >= 200:
            updates["outcome_200ticks"] = outcome_now
            pending["outcome_200"] = outcome_now
            completed_signals.append(signal_id)

        if updates:
            try:
                set_clauses = ", ".join(f"{k} = ?" for k in updates)
                values = list(updates.values()) + [signal_id]
                conn.execute(
                    f"UPDATE signal_log SET {set_clauses} WHERE id = ?",
                    values,
                )
            except sqlite3.Error:
                LOGGER.debug("Failed to update outcome for signal %d", signal_id)

    for sid in completed_signals:
        del _pending_outcomes[sid]


def mark_signal_closed(
    conn: sqlite3.Connection,
    signal_id: int,
    exit_price: float,
    pnl: float,
    close_reason: str,
) -> None:
    """Mark a signal as closed with final P&L."""
    try:
        conn.execute(
            """
            UPDATE signal_log
            SET exit_price = ?, pnl = ?, close_reason = ?,
                closed_at = datetime('now')
            WHERE id = ?
            """,
            (exit_price, pnl, close_reason, signal_id),
        )
    except sqlite3.Error:
        LOGGER.exception("Failed to close signal %d", signal_id)
    _pending_outcomes.pop(signal_id, None)


def get_signal_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return aggregate signal statistics for dashboard."""
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_signals,
                COALESCE(SUM(CASE WHEN executed = 1 THEN 1 ELSE 0 END), 0) AS executed_count,
                COALESCE(SUM(CASE WHEN executed = 0 THEN 1 ELSE 0 END), 0) AS signal_only_count,
                COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
                COALESCE(SUM(pnl), 0) AS total_pnl,
                COALESCE(AVG(score), 0) AS avg_score,
                COALESCE(AVG(adjusted_score), 0) AS avg_adj_score,
                COALESCE(AVG(CASE WHEN pnl > 0 THEN pnl END), 0) AS avg_win,
                COALESCE(AVG(CASE WHEN pnl < 0 THEN pnl END), 0) AS avg_loss,
                COALESCE(MAX(score), 0) AS max_score,
                COALESCE(MIN(score), 0) AS min_score,
                COUNT(CASE WHEN outcome_10ticks = 'WIN' THEN 1 END) AS outcome10_wins,
                COUNT(CASE WHEN outcome_10ticks = 'LOSS' THEN 1 END) AS outcome10_losses,
                COUNT(CASE WHEN outcome_50ticks = 'WIN' THEN 1 END) AS outcome50_wins,
                COUNT(CASE WHEN outcome_50ticks = 'LOSS' THEN 1 END) AS outcome50_losses,
                COUNT(CASE WHEN outcome_200ticks = 'WIN' THEN 1 END) AS outcome200_wins,
                COUNT(CASE WHEN outcome_200ticks = 'LOSS' THEN 1 END) AS outcome200_losses
            FROM signal_log
            """
        ).fetchone()

        by_symbol = conn.execute(
            """
            SELECT symbol, COUNT(*), COALESCE(SUM(pnl), 0),
                   COALESCE(AVG(score), 0), COALESCE(AVG(adjusted_score), 0)
            FROM signal_log
            GROUP BY symbol
            ORDER BY COUNT(*) DESC
            """
        ).fetchall()

        return {
            "total_signals": row[0] if row else 0,
            "executed_count": row[1] if row else 0,
            "signal_only_count": row[2] if row else 0,
            "wins": row[3] if row else 0,
            "losses": (row[0] or 0) - (row[3] or 0),
            "total_pnl": round(row[4], 2) if row else 0,
            "avg_score": round(row[5], 4) if row else 0,
            "avg_adj_score": round(row[6], 4) if row else 0,
            "avg_win": round(row[7], 2) if row else 0,
            "avg_loss": round(row[8], 2) if row else 0,
            "max_score": round(row[9], 4) if row else 0,
            "min_score": round(row[10], 4) if row else 0,
            "outcome_10_wr": round(
                (row[11] or 0) / max(1, (row[11] or 0) + (row[12] or 0)) * 100, 1
            ),
            "outcome_50_wr": round(
                (row[13] or 0) / max(1, (row[13] or 0) + (row[14] or 0)) * 100, 1
            ),
            "outcome_200_wr": round(
                (row[15] or 0) / max(1, (row[15] or 0) + (row[16] or 0)) * 100, 1
            ),
            "by_symbol": [
                {"symbol": r[0], "count": r[1], "pnl": round(r[2], 2),
                 "avg_score": round(r[3], 4), "avg_adj": round(r[4], 4)}
                for r in by_symbol
            ],
        }
    except Exception:
        return {
            "total_signals": 0, "executed_count": 0, "signal_only_count": 0,
            "wins": 0, "losses": 0, "total_pnl": 0,
            "avg_score": 0, "avg_adj_score": 0, "avg_win": 0, "avg_loss": 0,
            "max_score": 0, "min_score": 0,
            "outcome_10_wr": 0, "outcome_50_wr": 0, "outcome_200_wr": 0,
            "by_symbol": [],
        }


def get_recent_signals(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent signals for dashboard display."""
    try:
        rows = conn.execute(
            """
            SELECT id, symbol, direction, score, adjusted_score, executed,
                   entry_price, exit_price, pnl, close_reason,
                   framework_scores_json, l3_features_json, bias_breakdown_json,
                   spread_bps, risk_regime, session, dxy,
                   outcome_10ticks, outcome_50ticks, outcome_200ticks,
                   timestamp
            FROM signal_log
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0], "symbol": r[1], "direction": r[2],
                "score": r[3], "adjusted_score": r[4], "executed": bool(r[5]),
                "entry_price": r[6], "exit_price": r[7], "pnl": r[8],
                "close_reason": r[9],
                "framework_scores": json.loads(r[10]) if r[10] else {},
                "l3_features": json.loads(r[11]) if r[11] else {},
                "bias_breakdown": json.loads(r[12]) if r[12] else {},
                "spread_bps": r[13], "risk_regime": r[14],
                "session": r[15], "dxy": r[16],
                "outcome_10": r[17], "outcome_50": r[18], "outcome_200": r[19],
                "timestamp": r[20],
            }
            for r in rows
        ]
    except Exception:
        return []
