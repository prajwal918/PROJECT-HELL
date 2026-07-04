"""Beat / Miss event analyzer — Framework 7 scoring.

Stores historical economic release data (CPI, NFP, GDP, etc.) and
analyses the directional lean for a given event + currency pair.

Data lives in the ``economic_history`` table inside the main OVERSEER
SQLite database.

Usage
-----
>>> from engine_logic.event_analyzer import EventAnalyzer
>>> ea = EventAnalyzer()
>>> ea.log_actual("CPI", "USD", forecast=3.1, actual=3.3)
>>> info = ea.analyze_historical_lean("CPI", "USD", n_periods=6)
>>> score = ea.score_event("CPI", "USD")   # → +1 (persistent beat)
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

LOGGER = logging.getLogger("overseer.event_analyzer")

# ── database path (same as setup_db.py) ──
_DB_PATH = Path(__file__).resolve().parents[1] / "database" / "overseer_trades.db"

# ── schema for the economic_history table ──
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS economic_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name     TEXT    NOT NULL,
    currency       TEXT    NOT NULL,
    forecast       REAL,
    actual         REAL,
    surprise_pct   REAL,
    pip_reaction   REAL,
    outcome        TEXT    CHECK (outcome IN ('BEAT', 'MISS', 'INLINE')),
    recorded_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_econ_hist_event_currency
    ON economic_history (event_name, currency, recorded_at DESC);
"""

# ── surprise tolerance: |actual − forecast| / |forecast| < threshold → INLINE ──
_INLINE_THRESHOLD_PCT = 0.5  # 0.5 %


def _classify(forecast: float, actual: float) -> tuple[str, float]:
    """Return (outcome, surprise_pct)."""
    if forecast == 0:
        surprise_pct = 0.0
        if actual > 0:
            return "BEAT", surprise_pct
        if actual < 0:
            return "MISS", surprise_pct
        return "INLINE", 0.0

    surprise_pct = ((actual - forecast) / abs(forecast)) * 100.0

    if abs(surprise_pct) <= _INLINE_THRESHOLD_PCT:
        return "INLINE", round(surprise_pct, 4)
    if actual > forecast:
        return "BEAT", round(surprise_pct, 4)
    return "MISS", round(surprise_pct, 4)


class EventAnalyzer:
    """Analyse historical beat/miss lean for economic releases.

    Parameters
    ----------
    db_path : Path | str | None
        Override for the SQLite database file.  Defaults to the main
        OVERSEER database.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DB_PATH
        self._ensure_table()
        LOGGER.info("EventAnalyzer initialised — db=%s", self._db_path)

    # ── internal ──

    def _get_conn(self) -> sqlite3.Connection:
        """Return a new connection with WAL mode."""
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _ensure_table(self) -> None:
        """Create the economic_history table if it does not exist."""
        try:
            with self._get_conn() as conn:
                conn.executescript(_CREATE_TABLE_SQL + _CREATE_INDEX_SQL)
                conn.commit()
        except sqlite3.Error as exc:
            LOGGER.error("Failed to ensure economic_history table: %s", exc)

    # ── public API ──

    def log_actual(
        self,
        event_name: str,
        currency: str,
        forecast: float,
        actual: float,
        pip_reaction: Optional[float] = None,
    ) -> None:
        """Record a new economic release.

        Parameters
        ----------
        event_name : str
            E.g. ``"CPI"``, ``"NFP"``, ``"GDP"``.
        currency : str
            ISO currency code, e.g. ``"USD"``.
        forecast / actual : float
            The consensus forecast and actual released value.
        pip_reaction : float | None
            Optional observed pip reaction in the first candle.
        """
        outcome, surprise_pct = _classify(forecast, actual)
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO economic_history
                        (event_name, currency, forecast, actual, surprise_pct,
                         pip_reaction, outcome)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_name.upper(),
                        currency.upper(),
                        forecast,
                        actual,
                        surprise_pct,
                        pip_reaction,
                        outcome,
                    ),
                )
                conn.commit()
            LOGGER.info(
                "Logged release: %s %s forecast=%.4f actual=%.4f → %s (%.2f%%)",
                event_name, currency, forecast, actual, outcome, surprise_pct,
            )
        except sqlite3.Error as exc:
            LOGGER.error("Failed to log actual: %s", exc)

    def analyze_historical_lean(
        self,
        event_name: str,
        currency: str,
        n_periods: int = 6,
    ) -> dict[str, Any]:
        """Analyse the last *n_periods* releases for directional lean.

        Returns
        -------
        dict with keys:
            beat_count, miss_count, inline_count,
            lean (BEAT | MISS | NEUTRAL),
            average_surprise_pct,
            average_pip_reaction
        """
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT outcome, surprise_pct, pip_reaction
                    FROM economic_history
                    WHERE event_name = ? AND currency = ?
                    ORDER BY recorded_at DESC
                    LIMIT ?
                    """,
                    (event_name.upper(), currency.upper(), n_periods),
                ).fetchall()
        except sqlite3.Error as exc:
            LOGGER.error("Historical lean query failed: %s", exc)
            return self._empty_lean()

        if not rows:
            LOGGER.debug("No history for %s/%s", event_name, currency)
            return self._empty_lean()

        beats = sum(1 for r in rows if r[0] == "BEAT")
        misses = sum(1 for r in rows if r[0] == "MISS")
        inlines = sum(1 for r in rows if r[0] == "INLINE")

        surprises = [r[1] for r in rows if r[1] is not None]
        avg_surprise = sum(surprises) / len(surprises) if surprises else 0.0

        pips = [r[2] for r in rows if r[2] is not None]
        avg_pips = sum(pips) / len(pips) if pips else 0.0

        # Determine lean
        total = len(rows)
        if beats > total / 2:
            lean = "BEAT"
        elif misses > total / 2:
            lean = "MISS"
        else:
            lean = "NEUTRAL"

        result = {
            "beat_count": beats,
            "miss_count": misses,
            "inline_count": inlines,
            "lean": lean,
            "average_surprise_pct": round(avg_surprise, 4),
            "average_pip_reaction": round(avg_pips, 2),
            "periods_analysed": total,
        }
        LOGGER.info(
            "Historical lean: %s/%s → %s (B=%d M=%d I=%d avg_surprise=%.2f%%)",
            event_name, currency, lean, beats, misses, inlines, avg_surprise,
        )
        return result

    def score_event(
        self,
        event_name: str,
        currency: str,
        n_periods: int = 6,
    ) -> int:
        """Return a Framework 7 score: +1, 0, or -1.

        +1 → persistent beat lean (bullish for currency)
        -1 → persistent miss lean (bearish for currency)
         0 → no clear lean
        """
        lean_info = self.analyze_historical_lean(event_name, currency, n_periods)
        lean = lean_info.get("lean", "NEUTRAL")
        if lean == "BEAT":
            return 1
        if lean == "MISS":
            return -1
        return 0

    # ── helpers ──

    @staticmethod
    def _empty_lean() -> dict[str, Any]:
        return {
            "beat_count": 0,
            "miss_count": 0,
            "inline_count": 0,
            "lean": "NEUTRAL",
            "average_surprise_pct": 0.0,
            "average_pip_reaction": 0.0,
            "periods_analysed": 0,
        }

    def get_recent_releases(
        self,
        event_name: str,
        currency: str,
        n: int = 10,
    ) -> list[dict[str, Any]]:
        """Return the *n* most recent releases (for debugging / display)."""
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT event_name, currency, forecast, actual,
                           surprise_pct, pip_reaction, outcome, recorded_at
                    FROM economic_history
                    WHERE event_name = ? AND currency = ?
                    ORDER BY recorded_at DESC
                    LIMIT ?
                    """,
                    (event_name.upper(), currency.upper(), n),
                ).fetchall()
        except sqlite3.Error as exc:
            LOGGER.error("Recent releases query failed: %s", exc)
            return []

        return [
            {
                "event_name": r[0],
                "currency": r[1],
                "forecast": r[2],
                "actual": r[3],
                "surprise_pct": r[4],
                "pip_reaction": r[5],
                "outcome": r[6],
                "recorded_at": r[7],
            }
            for r in rows
        ]
