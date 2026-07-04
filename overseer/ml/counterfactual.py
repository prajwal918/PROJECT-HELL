from __future__ import annotations

import logging
import math
import os
import sqlite3
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger("overseer.counterfactual")

_ENABLED = os.getenv("COUNTERFACTUAL_ENABLED", "true").lower() == "true"
_DB_PATH = os.getenv("DB_PATH", "database/overseer_trades.db")
_LOOKAHEAD_TICKS = int(os.getenv("COUNTERFACTUAL_LOOKAHEAD_TICKS", "200"))
_MAX_TRADES = int(os.getenv("COUNTERFACTUAL_MAX_TRADES", "500"))
_ALPHA_SMOOTH = float(os.getenv("COUNTERFACTUAL_ALPHA_SMOOTH", "0.1"))


class CounterfactualAnalyzer:
    def __init__(self) -> None:
        self._trades: Dict[str, deque] = {}
        self._execution_alphas: Dict[str, float] = {}
        self._tick_prices: Dict[str, deque] = {}
        self._n_trades: Dict[str, int] = {}

    def record_trade(
        self,
        symbol: str,
        entry_price: float,
        entry_tick: int,
        exit_price: float,
        exit_tick: int,
        pnl: float,
    ) -> None:
        if not _ENABLED:
            return
        if symbol not in self._trades:
            self._trades[symbol] = deque(maxlen=_MAX_TRADES)
            self._n_trades[symbol] = 0
        trade = {
            "entry_price": entry_price,
            "entry_tick": entry_tick,
            "exit_price": exit_price,
            "exit_tick": exit_tick,
            "pnl": pnl,
        }
        self._trades[symbol].append(trade)
        self._n_trades[symbol] = self._n_trades[symbol] + 1
        cf_pnl = self.compute_counterfactual(symbol, entry_tick, min(exit_tick - entry_tick, _LOOKAHEAD_TICKS))
        if cf_pnl is not None:
            alpha = pnl - cf_pnl
            old = self._execution_alphas.get(symbol, 0.0)
            self._execution_alphas[symbol] = old + _ALPHA_SMOOTH * (alpha - old)

    def compute_counterfactual(self, symbol: str, entry_tick: int, n_ticks: int) -> Optional[float]:
        if not _ENABLED:
            return None
        try:
            conn = sqlite3.connect(_DB_PATH, timeout=10)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT bid, ask FROM tick_log
                WHERE symbol = ? AND rowid > ?
                ORDER BY rowid ASC LIMIT ?
                """,
                (symbol, entry_tick, n_ticks),
            ).fetchall()
            conn.close()
        except Exception as exc:
            LOGGER.warning("Counterfactual DB query failed: %s", exc)
            return None
        if not rows:
            return None
        mid_start = (float(rows[0]["bid"]) + float(rows[0]["ask"])) / 2.0
        mid_end = (float(rows[-1]["bid"]) + float(rows[-1]["ask"])) / 2.0
        cf_pnl = mid_end - mid_start
        return cf_pnl

    def get_execution_alpha(self, symbol: str) -> float:
        return self._execution_alphas.get(symbol, 0.0)

    def get_all_alphas(self) -> Dict[str, float]:
        return {k: round(v, 4) for k, v in self._execution_alphas.items()}

    def is_execution_destroying_edge(self, symbol: str) -> bool:
        alpha = self._execution_alphas.get(symbol, 0.0)
        return alpha < -0.5

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": _ENABLED,
            "execution_alphas": self.get_all_alphas(),
            "n_trades": dict(self._n_trades),
        }


counterfactual_analyzer = CounterfactualAnalyzer()
