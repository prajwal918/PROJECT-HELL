from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from backtest.simulator import SimExecutor

LOGGER = logging.getLogger("overseer.paper_trading")

_DB_PATH = Path(__file__).resolve().parent.parent / "database" / "overseer_trades.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    lot_size REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    sl_price REAL,
    tp_price REAL,
    pnl REAL,
    pnl_pips REAL,
    exit_reason TEXT,
    score REAL,
    raw_score REAL,
    gate_states_json TEXT,
    framework_scores_json TEXT,
    slippage_pips REAL,
    spread_at_entry REAL,
    entry_tick INTEGER,
    exit_tick INTEGER,
    is_open INTEGER NOT NULL DEFAULT 1 CHECK (is_open IN (0, 1)),
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_paper_symbol
ON paper_trades(symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_paper_open
ON paper_trades(is_open);
"""

_PAPER_LOT_SIZE = float(os.getenv("PAPER_LOT_SIZE", "0.01"))
_PAPER_SLIPPAGE_PIPS = float(os.getenv("PAPER_SLIPPAGE_PIPS", "1.0"))
_PAPER_MAX_SPREAD_PIPS = float(os.getenv("PAPER_MAX_SPREAD_PIPS", "5.0"))
_PAPER_COMMISSION_PER_LOT = float(os.getenv("PAPER_COMMISSION_PER_LOT", "7.0"))
_PAPER_ENABLED = os.getenv("PAPER_TRADING_ENABLED", "true").lower() == "true"


class PaperTradingEngine:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DB_PATH
        self.enabled = _PAPER_ENABLED
        self._sim = SimExecutor(
            account_balance=10000.0,
            slippage_pips=_PAPER_SLIPPAGE_PIPS,
            max_spread_pips=_PAPER_MAX_SPREAD_PIPS,
            commission_per_lot=_PAPER_COMMISSION_PER_LOT,
        )
        self._open_symbols: set[str] = set()
        self._ticket_to_symbol: dict[int, str] = {}
        self._tick_count = 0
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.executescript(_CREATE_TABLE)
                conn.commit()
        except Exception as exc:
            LOGGER.error("Failed to create paper_trades table: %s", exc)

    def is_enabled(self) -> bool:
        return self.enabled

    def execute_paper_trade(
        self,
        symbol: str,
        direction: str,
        sl_pips: float,
        tp_pips: float,
        tick: dict[str, Any],
        tick_count: int,
        score: float = 0,
        raw_score: float = 0,
        gate_states: dict[str, bool] | None = None,
        framework_scores: dict[str, float] | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        if symbol in self._open_symbols:
            LOGGER.debug("Paper trade skipped: %s already has open paper position", symbol)
            return None

        result = self._sim.execute_trade(
            symbol=symbol,
            direction=direction,
            lot_size=_PAPER_LOT_SIZE,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            tick=tick,
            tick_count=tick_count,
            score=score,
            gate_states=gate_states or {},
            framework_scores=framework_scores or {},
        )

        if result is None:
            return None

        ticket = result["ticket"]
        self._open_symbols.add(symbol)
        self._ticket_to_symbol[ticket] = symbol

        spread_at_entry = 0
        bid = float(tick.get("bid", 0))
        ask = float(tick.get("ask", 0))
        if bid > 0 and ask > 0:
            pip = self._sim._pip_size(symbol)
            spread_at_entry = (ask - bid) / pip if pip > 0 else 0

        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO paper_trades
                    (ticket, symbol, direction, lot_size, entry_price, sl_price, tp_price,
                     score, raw_score, gate_states_json, framework_scores_json,
                     slippage_pips, spread_at_entry, entry_tick)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticket, symbol, direction, _PAPER_LOT_SIZE,
                        result["price"], result["sl"], result["tp"],
                        score, raw_score,
                        json.dumps(gate_states) if gate_states else None,
                        json.dumps(framework_scores) if framework_scores else None,
                        result["slippage_pips"], spread_at_entry, tick_count,
                    ),
                )
                conn.commit()
        except Exception as exc:
            LOGGER.error("Failed to insert paper trade: %s", exc)

        LOGGER.info(
            "Paper trade: %s %s ticket=%d fill=%.5f sl=%.5f tp=%.5f slippage=%.1fpips",
            direction, symbol, ticket, result["price"], result["sl"], result["tp"], result["slippage_pips"],
        )

        return result

    def check_sl_tp(self, tick: dict[str, Any], tick_count: int) -> list[dict[str, Any]]:
        closed = self._sim.check_sl_tp(tick, tick_count)
        results = []

        for trade in closed:
            symbol = self._ticket_to_symbol.pop(trade.ticket, None)
            if symbol:
                self._open_symbols.discard(symbol)

            try:
                with sqlite3.connect(self._db_path) as conn:
                    conn.execute(
                        """
                        UPDATE paper_trades
                        SET exit_price = ?, pnl = ?, pnl_pips = ?, exit_reason = ?,
                            exit_tick = ?, is_open = 0, closed_at = datetime('now')
                        WHERE ticket = ?
                        """,
                        (trade.exit_price, trade.pnl, trade.pnl_pips, trade.exit_reason,
                         trade.exit_tick, trade.ticket),
                    )
                    conn.commit()
            except Exception as exc:
                LOGGER.error("Failed to update paper trade close: %s", exc)

            results.append({
                "ticket": trade.ticket,
                "symbol": trade.symbol,
                "direction": trade.direction,
                "pnl": trade.pnl,
                "pnl_pips": trade.pnl_pips,
                "exit_reason": trade.exit_reason,
            })

            LOGGER.info(
                "Paper trade closed: %s %s ticket=%d pnl=%.2f (%.1f pips) reason=%s",
                trade.direction, trade.symbol, trade.ticket, trade.pnl, trade.pnl_pips, trade.exit_reason,
            )

        return results

    def get_stats(self, hours: int = 24) -> dict[str, Any]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
                        COALESCE(SUM(pnl), 0) AS total_pnl,
                        COALESCE(AVG(pnl_pips), 0) AS avg_pnl_pips,
                        COALESCE(SUM(CASE WHEN is_open = 1 THEN 1 ELSE 0 END), 0) AS open_count
                    FROM paper_trades
                    WHERE timestamp >= datetime('now', ?)
                    """,
                    (f"-{hours} hours",),
                ).fetchone()

                total = row[0] if row else 0
                wins = row[1] if row else 0
                wr = (wins / total * 100) if total > 0 else 0

                return {
                    "total_trades": total,
                    "wins": wins,
                    "win_rate": round(wr, 1),
                    "total_pnl": round(row[2], 2) if row else 0,
                    "avg_pnl_pips": round(row[3], 2) if row else 0,
                    "open_positions": row[4] if row else 0,
                }
        except Exception as exc:
            LOGGER.error("Failed to get paper trading stats: %s", exc)
            return {"total_trades": 0}

    def get_status(self) -> dict[str, Any]:
        stats_24h = self.get_stats(24)
        return {
            "enabled": self.enabled,
            "open_symbols": list(self._open_symbols),
            "balance": round(self._sim.account_balance, 2),
            "stats_24h": stats_24h,
        }
