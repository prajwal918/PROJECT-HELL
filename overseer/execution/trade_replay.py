from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("overseer.trade_replay")

_DB_PATH = Path(__file__).resolve().parent.parent / "database" / "overseer_trades.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS trade_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    ticket INTEGER,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    score REAL NOT NULL,
    raw_score REAL NOT NULL,
    adjusted_score REAL NOT NULL,
    pipeline_stages_json TEXT,
    gate_states_json TEXT,
    framework_scores_json TEXT,
    l3_features_json TEXT,
    bias_breakdown_json TEXT,
    dom_snapshot_json TEXT,
    dom_health TEXT,
    risk_checks_json TEXT,
    latency_json TEXT,
    rejection_reason TEXT,
    outcome TEXT,
    entry_price REAL,
    exit_price REAL,
    pnl REAL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (signal_id) REFERENCES signal_log(id)
);

CREATE INDEX IF NOT EXISTS idx_audit_symbol
ON trade_audit(symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_audit_ticket
ON trade_audit(ticket);
"""


class TradeReplay:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DB_PATH
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.executescript(_CREATE_TABLE)
                conn.commit()
        except Exception as exc:
            LOGGER.error("Failed to create trade_audit table: %s", exc)

    def log_trade_decision(
        self,
        symbol: str,
        direction: str,
        score: float,
        raw_score: float,
        adjusted_score: float,
        gate_states: dict[str, bool] | None = None,
        framework_scores: dict[str, float] | None = None,
        l3_features: dict[str, Any] | None = None,
        bias_breakdown: dict[str, float] | None = None,
        dom_snapshot: dict[str, Any] | None = None,
        dom_health: str = "unknown",
        risk_checks: dict[str, Any] | None = None,
        latency: dict[str, float] | None = None,
        pipeline_stages: dict[str, str] | None = None,
        rejection_reason: str | None = None,
        signal_id: int | None = None,
        ticket: int | None = None,
    ) -> int:
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO trade_audit
                    (signal_id, ticket, symbol, direction, score, raw_score, adjusted_score,
                     pipeline_stages_json, gate_states_json, framework_scores_json,
                     l3_features_json, bias_breakdown_json, dom_snapshot_json,
                     dom_health, risk_checks_json, latency_json, rejection_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal_id,
                        ticket,
                        symbol,
                        direction,
                        score,
                        raw_score,
                        adjusted_score,
                        json.dumps(pipeline_stages) if pipeline_stages else None,
                        json.dumps(gate_states) if gate_states else None,
                        json.dumps(framework_scores) if framework_scores else None,
                        json.dumps(l3_features) if l3_features else None,
                        json.dumps(bias_breakdown) if bias_breakdown else None,
                        json.dumps(dom_snapshot) if dom_snapshot else None,
                        dom_health,
                        json.dumps(risk_checks) if risk_checks else None,
                        json.dumps(latency) if latency else None,
                        rejection_reason,
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as exc:
            LOGGER.error("Failed to log trade audit: %s", exc)
            return -1

    def update_outcome(self, audit_id: int, outcome: str, entry_price: float = 0, exit_price: float = 0, pnl: float = 0) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    UPDATE trade_audit
                    SET outcome = ?, entry_price = ?, exit_price = ?, pnl = ?
                    WHERE id = ?
                    """,
                    (outcome, entry_price, exit_price, pnl, audit_id),
                )
                conn.commit()
        except Exception as exc:
            LOGGER.error("Failed to update trade audit outcome: %s", exc)

    def replay_trade(self, audit_id: int) -> dict[str, Any] | None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT * FROM trade_audit WHERE id = ?", (audit_id,)
                ).fetchone()
                if row is None:
                    return None
                columns = [desc[0] for desc in conn.execute("SELECT * FROM trade_audit LIMIT 0").description]
                result = dict(zip(columns, row))
                for key in ("pipeline_stages_json", "gate_states_json", "framework_scores_json",
                            "l3_features_json", "bias_breakdown_json", "dom_snapshot_json",
                            "risk_checks_json", "latency_json"):
                    val = result.get(key)
                    if isinstance(val, str):
                        try:
                            result[key] = json.loads(val)
                        except (json.JSONDecodeError, TypeError):
                            pass
                return result
        except Exception as exc:
            LOGGER.error("Failed to replay trade %d: %s", audit_id, exc)
            return None

    def replay_recent(self, limit: int = 20, symbol: str | None = None) -> list[dict[str, Any]]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                query = "SELECT id, symbol, direction, score, raw_score, adjusted_score, rejection_reason, outcome, timestamp FROM trade_audit"
                params: list[Any] = []
                if symbol:
                    query += " WHERE symbol = ?"
                    params.append(symbol)
                query += " ORDER BY id DESC LIMIT ?"
                params.append(limit)
                rows = conn.execute(query, params).fetchall()
                columns = ["id", "symbol", "direction", "score", "raw_score", "adjusted_score", "rejection_reason", "outcome", "timestamp"]
                return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            LOGGER.error("Failed to replay recent trades: %s", exc)
            return []

    def diagnose_rejection(self, audit_id: int) -> dict[str, Any]:
        trade = self.replay_trade(audit_id)
        if trade is None:
            return {"error": f"Trade audit {audit_id} not found"}

        diagnosis: dict[str, Any] = {
            "audit_id": audit_id,
            "symbol": trade.get("symbol"),
            "direction": trade.get("direction"),
            "rejection_reason": trade.get("rejection_reason"),
            "score": trade.get("score"),
            "raw_score": trade.get("raw_score"),
            "checks": [],
        }

        raw = trade.get("raw_score", 0)
        if raw < 0.85:
            diagnosis["checks"].append({"gate": "score_threshold", "pass": False, "detail": f"raw_score={raw:.4f} < 0.85"})

        gate_states = trade.get("gate_states_json", {})
        if isinstance(gate_states, dict):
            critical_gates = {"gate_D": "Directional momentum (REQUIRED)", "gate_Z7": "L3 lag check"}
            for gname, gdesc in critical_gates.items():
                passed = gate_states.get(gname, False)
                diagnosis["checks"].append({"gate": gname, "pass": passed, "detail": gdesc})

        risk_checks = trade.get("risk_checks_json", {})
        if isinstance(risk_checks, dict):
            for check_name, check_result in risk_checks.items():
                if check_result is False or (isinstance(check_result, dict) and not check_result.get("allowed", True)):
                    diagnosis["checks"].append({"gate": check_name, "pass": False, "detail": str(check_result)})

        bias = trade.get("bias_breakdown_json", {})
        if isinstance(bias, dict):
            adverse = bias.get("adverse_selection_risk", bias.get("adverse_risk", 0))
            if adverse > 0.5:
                diagnosis["checks"].append({"gate": "adverse_l3_bias", "pass": False, "detail": f"adverse_risk={adverse:.2f}"})

        dom_health = trade.get("dom_health", "unknown")
        if dom_health != "healthy":
            diagnosis["checks"].append({"gate": "dom_health", "pass": dom_health == "healthy", "detail": dom_health})

        return diagnosis

    def get_rejection_stats(self, hours: int = 24) -> dict[str, Any]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT rejection_reason, COUNT(*) AS cnt
                    FROM trade_audit
                    WHERE rejection_reason IS NOT NULL
                    AND timestamp >= datetime('now', ?)
                    GROUP BY rejection_reason
                    ORDER BY cnt DESC
                    """,
                    (f"-{hours} hours",),
                ).fetchall()
                total = conn.execute(
                    """
                    SELECT COUNT(*) FROM trade_audit
                    WHERE timestamp >= datetime('now', ?)
                    """,
                    (f"-{hours} hours",),
                ).fetchone()[0]
                return {
                    "total_decisions": total,
                    "rejection_breakdown": {row[0]: row[1] for row in rows},
                }
        except Exception as exc:
            LOGGER.error("Failed to get rejection stats: %s", exc)
            return {"total_decisions": 0}

    def get_status(self) -> dict[str, Any]:
        return {
            "rejection_stats_24h": self.get_rejection_stats(24),
            "recent_trades": self.replay_recent(5),
        }
