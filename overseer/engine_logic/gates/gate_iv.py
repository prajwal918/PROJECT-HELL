"""Framework 11 — Options IV / Risk-Reversal Gate.

Reads the institutional directional skew from the options_iv table
and blocks trades that fight extreme institutional positioning.

Logic:
  • If 25-delta RR is extremely positive (calls expensive) and we're
    trying to SELL → BLOCK (institutions are pricing upside)
  • If 25-delta RR is extremely negative (puts expensive) and we're
    trying to BUY → BLOCK (institutions are pricing downside)
  • Otherwise → PASS

Additionally provides an IV-expansion filter:
  • If ATM IV is in the top 10 % of its 52-week range, suppress
    new positions (vol is too rich → wider stops needed).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_iv")

_DB_PATH = Path(__file__).resolve().parents[2] / "database" / "overseer_trades.db"

_IV_EXPANSION_BLOCK_PCT = float(os.getenv("IV_EXPANSION_BLOCK_PCT", "90"))
_EXTREME_RR_BLOCK = float(os.getenv("IV_EXTREME_RR_BLOCK", "1.5"))


class GateIVSkew(BaseGate):
    """Framework 11 gate — blocks trades fighting institutional IV skew."""

    gate_name = "gate_IVSKEW"
    priority = 6

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}
        self._last_load: float = 0.0

    def _refresh_cache(self) -> None:
        import time
        now = time.time()
        if now - self._last_load < 300.0:
            return
        try:
            with sqlite3.connect(_DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT symbol, atm_iv, rr_25d, iv_percentile_52w, skew_score
                    FROM options_iv
                    WHERE id IN (
                        SELECT MAX(id) FROM options_iv GROUP BY symbol
                    )
                    """
                ).fetchall()
            self._cache = {}
            for r in rows:
                self._cache[r["symbol"]] = dict(r)
        except Exception as exc:
            LOGGER.warning("IV cache refresh failed: %s", exc)
        self._last_load = now

    def evaluate(self, tick: dict[str, Any]) -> bool:
        self._refresh_cache()
        symbol = tick.get("symbol", "").upper()
        direction = tick.get("direction", "BUY").upper()

        iv_data = self._cache.get(symbol)
        if iv_data is None:
            return True

        rr_25d = iv_data.get("rr_25d", 0.0) or 0.0

        if rr_25d > _EXTREME_RR_BLOCK and direction == "SELL":
            LOGGER.debug(
                "IV SKEW BLOCKED: %s SELL while RR25=%.2f (extreme call skew)",
                symbol, rr_25d,
            )
            return False

        if rr_25d < -_EXTREME_RR_BLOCK and direction == "BUY":
            LOGGER.debug(
                "IV SKEW BLOCKED: %s BUY while RR25=%.2f (extreme put skew)",
                symbol, rr_25d,
            )
            return False

        return True


class GateIVExpansion(BaseGate):
    """Blocks new trades when ATM IV is in the extreme high percentile.

    High IV means options are expensive and the market is expecting a
    large move — not the time for directional spot trades with tight
    stops.
    """

    gate_name = "gate_IVEXP"
    priority = 7

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}
        self._last_load: float = 0.0

    def _refresh_cache(self) -> None:
        import time
        now = time.time()
        if now - self._last_load < 300.0:
            return
        try:
            with sqlite3.connect(_DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT symbol, atm_iv, iv_percentile_52w
                    FROM options_iv
                    WHERE id IN (
                        SELECT MAX(id) FROM options_iv GROUP BY symbol
                    )
                    """
                ).fetchall()
            self._cache = {}
            for r in rows:
                self._cache[r["symbol"]] = dict(r)
        except Exception as exc:
            LOGGER.warning("IV expansion cache refresh failed: %s", exc)
        self._last_load = now

    def evaluate(self, tick: dict[str, Any]) -> bool:
        self._refresh_cache()
        symbol = tick.get("symbol", "").upper()

        iv_data = self._cache.get(symbol)
        if iv_data is None:
            return True

        pct_52w = iv_data.get("iv_percentile_52w")
        if pct_52w is None:
            return True

        if float(pct_52w) > _IV_EXPANSION_BLOCK_PCT:
            LOGGER.debug(
                "IV EXPANSION BLOCKED: %s IV percentile=%.1f%% > %.1f%%",
                symbol, pct_52w, _IV_EXPANSION_BLOCK_PCT,
            )
            return False

        return True
