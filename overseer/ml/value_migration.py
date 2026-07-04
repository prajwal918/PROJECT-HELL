"""Value Area Migration for OVERSEER v13.

Tracks POC (Point of Control), VAH (Value Area High), and VAL
(Value Area Low) across the last 5 sessions. When POC consistently
migrates higher, institutions are moving value up. When POC migrates
lower, institutions are moving value down.

If migration aligns with signal direction → +0.05 bonus.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from typing import Dict, List, Optional, Tuple

LOGGER = logging.getLogger("overseer.value_migration")

_ENABLED = os.getenv("VALUE_MIGRATION_ENABLED", "true").lower() == "true"
_BONUS = float(os.getenv("VALUE_MIGRATION_BONUS", "0.05"))
_MAX_SESSIONS = int(os.getenv("VALUE_MIGRATION_MAX_SESSIONS", "5"))
_MIGRATION_THRESHOLD = float(os.getenv("VALUE_MIGRATION_THRESHOLD", "0.3"))


class ValueMigration:
    """Track POC/VAH/VAL migration across sessions for institutional direction."""

    def __init__(self) -> None:
        self._sessions: Dict[str, deque] = {}
        self._migration_cache: Dict[str, str] = {}

    def _init_symbol(self, symbol: str) -> None:
        if symbol not in self._sessions:
            self._sessions[symbol] = deque(maxlen=_MAX_SESSIONS)

    def update_session(self, symbol: str, poc: float, vah: float, val: float) -> None:
        if not _ENABLED:
            return
        self._init_symbol(symbol)
        session_data = {
            "poc": poc,
            "vah": vah,
            "val": val,
            "range": vah - val if vah > val else 0.0001,
        }
        self._sessions[symbol].append(session_data)
        self._migration_cache.pop(symbol, None)

        LOGGER.debug(
            "ValueMigration %s: poc=%.5f vah=%.5f val=%.5f",
            symbol, poc, vah, val,
        )

    def get_migration_direction(self, symbol: str) -> str:
        if not _ENABLED:
            return "neutral"

        cached = self._migration_cache.get(symbol)
        if cached is not None:
            return cached

        sessions = self._sessions.get(symbol)
        if sessions is None or len(sessions) < 2:
            self._migration_cache[symbol] = "neutral"
            return "neutral"

        session_list = list(sessions)

        poc_values = [s["poc"] for s in session_list]
        val_values = [s["val"] for s in session_list]
        vah_values = [s["vah"] for s in session_list]

        avg_range = sum(s["range"] for s in session_list) / len(session_list)
        if avg_range <= 0:
            self._migration_cache[symbol] = "neutral"
            return "neutral"

        n = len(poc_values)
        poc_start = sum(poc_values[:max(1, n // 2)]) / max(1, n // 2)
        poc_end = sum(poc_values[max(1, n // 2):]) / max(1, n - n // 2)

        poc_migration = (poc_end - poc_start) / avg_range

        val_start = sum(val_values[:max(1, n // 2)]) / max(1, n // 2)
        val_end = sum(val_values[max(1, n // 2):]) / max(1, n - n // 2)
        val_migration = (val_end - val_start) / avg_range

        vah_start = sum(vah_values[:max(1, n // 2)]) / max(1, n // 2)
        vah_end = sum(vah_values[max(1, n // 2):]) / max(1, n - n // 2)
        vah_migration = (vah_end - vah_start) / avg_range

        combined = (poc_migration * 0.5 + val_migration * 0.25 + vah_migration * 0.25)

        if combined > _MIGRATION_THRESHOLD:
            direction = "up"
        elif combined < -_MIGRATION_THRESHOLD:
            direction = "down"
        else:
            direction = "neutral"

        self._migration_cache[symbol] = direction

        LOGGER.debug(
            "ValueMigration %s: poc_m=%.2f val_m=%.2f vah_m=%.2f combined=%.2f → %s",
            symbol, poc_migration, val_migration, vah_migration, combined, direction,
        )
        return direction

    def get_bonus(self, symbol: str, direction: str) -> float:
        if not _ENABLED:
            return 0.0

        migration_dir = self.get_migration_direction(symbol)

        if migration_dir == "neutral":
            return 0.0

        if direction == "BUY" and migration_dir == "up":
            return _BONUS
        elif direction == "SELL" and migration_dir == "down":
            return _BONUS
        elif direction == "BUY" and migration_dir == "down":
            return -_BONUS * 0.5
        elif direction == "SELL" and migration_dir == "up":
            return -_BONUS * 0.5

        return 0.0

    def get_sessions(self, symbol: str) -> List[Dict[str, float]]:
        sessions = self._sessions.get(symbol)
        if sessions is None:
            return []
        return list(sessions)


value_migration = ValueMigration()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    vm = value_migration
    vm.update_session("6EM6", 1.0850, 1.0870, 1.0830)
    vm.update_session("6EM6", 1.0855, 1.0875, 1.0835)
    vm.update_session("6EM6", 1.0862, 1.0882, 1.0842)
    vm.update_session("6EM6", 1.0870, 1.0890, 1.0850)
    vm.update_session("6EM6", 1.0878, 1.0898, 1.0858)
    d = vm.get_migration_direction("6EM6")
    print(f"  6EM6 migration: {d}")
    for trade_dir in ("BUY", "SELL"):
        b = vm.get_bonus("6EM6", trade_dir)
        print(f"  6EM6 {trade_dir}: bonus={b:+.4f}")
