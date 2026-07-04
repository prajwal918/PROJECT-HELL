#!/usr/bin/env python3
"""
Gate Combo Pattern Memory — discover and exploit gate combinations
that have historically produced high win rates.

Not all gate combinations are equal. gate_A + gate_D might be
worth 0.02 bonus alone, but gate_A + gate_D + gate_Z15 could
be worth 0.10 bonus because that specific combo has 85% WR.

This module queries signal_log for gate combos with >75% WR
(min 10 samples) and stores them as bonus multipliers that
are applied to the adjusted score.

Combo keys are sorted, frozen sets of gate names to ensure
order-invariant matching (gate_A+gate_D == gate_D+gate_A).
"""

import json
import logging
import os
import sqlite3
from itertools import combinations
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

LOGGER = logging.getLogger("overseer.gate_combos")

GATE_COMBOS_ENABLED = os.getenv(
    "GATE_COMBOS_ENABLED", "true"
).lower() in ("true", "1", "yes")

COMBO_MIN_WR = float(os.getenv("GATE_COMBO_MIN_WR", "0.75"))
COMBO_MIN_SAMPLES = int(os.getenv("GATE_COMBO_MIN_SAMPLES", "10"))
COMBO_MAX_GATES = int(os.getenv("GATE_COMBO_MAX_GATES", "4"))
COMBO_BONUS_MAX = float(os.getenv("GATE_COMBO_BONUS_MAX", "0.10"))
COMBO_BONUS_PER_PP = float(os.getenv("GATE_COMBO_BONUS_PER_PP", "0.001"))

DB_PATH = os.getenv("DB_PATH", "database/overseer_trades.db")


class GateComboMemory:
    """Discovers and applies high-WR gate combo bonuses."""

    def __init__(self):
        self._combos: Dict[str, Dict[FrozenSet, Dict]] = {}
        # _combos[symbol_dir] = {frozenset_of_gates: {"wr": float, "count": int, "bonus": float}}
        self._loaded = False

    def _make_key(self, symbol: str, direction: str) -> str:
        return f"{symbol}_{direction}"

    def refresh_from_db(self, db_path: Optional[str] = None) -> int:
        """
        Query signal_log for high-WR gate combinations.

        Returns the number of combos discovered.
        """
        if not GATE_COMBOS_ENABLED:
            return 0

        _db = db_path or DB_PATH
        total_combos = 0

        try:
            conn = sqlite3.connect(_db, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            rows = conn.execute(
                """
                SELECT symbol, direction, gate_states_json, outcome_200ticks
                FROM signal_log
                WHERE gate_states_json IS NOT NULL
                AND outcome_200ticks IS NOT NULL
                AND outcome_200ticks != 'FLAT'
                """
            ).fetchall()
            conn.close()
        except Exception as e:
            LOGGER.warning("Gate combo DB query failed: %s", e)
            return 0

        # Group by symbol_direction
        groups: Dict[str, List[Dict]] = {}
        for symbol, direction, gates_json, outcome in rows:
            key = self._make_key(symbol, direction)
            if key not in groups:
                groups[key] = []
            try:
                gates = json.loads(gates_json) if gates_json else {}
            except (json.JSONDecodeError, TypeError):
                continue
            passed_gates = sorted(
                [g for g, v in gates.items() if v is True or v == 1]
            )
            groups[key].append({
                "passed": passed_gates,
                "win": outcome == "WIN",
            })

        # Find combos with >COMBO_MIN_WR WR
        self._combos.clear()
        for key, records in groups.items():
            self._combos[key] = {}
            total_records = len(records)
            if total_records < COMBO_MIN_SAMPLES:
                continue

            # Enumerate gate combos of size 2..COMBO_MAX_GATES
            # For efficiency, only consider top 20 most common gates
            gate_counts: Dict[str, int] = {}
            for rec in records:
                for g in rec["passed"]:
                    gate_counts[g] = gate_counts.get(g, 0) + 1

            top_gates = sorted(
                gate_counts.keys(),
                key=lambda g: gate_counts[g],
                reverse=True,
            )[:25]

            for size in range(2, COMBO_MAX_GATES + 1):
                for combo in combinations(top_gates, size):
                    combo_set = frozenset(combo)
                    wins = 0
                    total = 0
                    for rec in records:
                        if combo_set.issubset(frozenset(rec["passed"])):
                            total += 1
                            if rec["win"]:
                                wins += 1

                    if total < COMBO_MIN_SAMPLES:
                        continue

                    wr = wins / total
                    if wr >= COMBO_MIN_WR:
                        bonus = min(
                            COMBO_BONUS_MAX,
                            (wr - 0.50) * COMBO_BONUS_PER_PP * 100,
                        )
                        self._combos[key][combo_set] = {
                            "wr": round(wr, 4),
                            "count": total,
                            "bonus": round(bonus, 4),
                        }
                        total_combos += 1

        self._loaded = True
        LOGGER.info(
            "Gate combos loaded: %d combos across %d groups from %d records",
            total_combos,
            len(self._combos),
            len(rows),
        )
        return total_combos

    def check_combo(
        self,
        gate_states: Dict[str, bool],
        symbol: str,
        direction: str,
    ) -> float:
        """
        Check if current gate states match any known high-WR combo.

        Returns the maximum bonus from matching combos, or 0.0.
        """
        if not GATE_COMBOS_ENABLED:
            return 0.0

        key = self._make_key(symbol, direction)
        combo_map = self._combos.get(key, {})
        if not combo_map:
            return 0.0

        passed_set = frozenset(
            g for g, v in gate_states.items() if v is True or v == 1
        )

        best_bonus = 0.0
        for combo_set, info in combo_map.items():
            if combo_set.issubset(passed_set):
                bonus = info.get("bonus", 0.0)
                if bonus > best_bonus:
                    best_bonus = bonus

        return best_bonus

    def get_all_combos(
        self, symbol: str, direction: str
    ) -> Dict[FrozenSet, Dict]:
        """Return all stored combos for a symbol/direction."""
        key = self._make_key(symbol, direction)
        return self._combos.get(key, {})

    def get_status(self) -> Dict:
        """Status dict for dashboards."""
        total_combos = sum(len(v) for v in self._combos.values())
        return {
            "enabled": GATE_COMBOS_ENABLED,
            "loaded": self._loaded,
            "total_combos": total_combos,
            "groups": len(self._combos),
            "min_wr": COMBO_MIN_WR,
            "min_samples": COMBO_MIN_SAMPLES,
            "bonus_max": COMBO_BONUS_MAX,
        }

    def reset(self) -> None:
        """Clear all combo data."""
        self._combos.clear()
        self._loaded = False


gate_combo_memory = GateComboMemory()
