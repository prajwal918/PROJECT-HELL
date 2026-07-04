#!/usr/bin/env python3
"""
LEGENDARY MODE — One trade per symbol per day maximum.

Only fires when ALL platinum gates align simultaneously.
When it fires: full conviction, larger size, extended target.

Philosophy: "It's not whether you're right or wrong,
it's how much you make when you're right." — Druckenmiller
"""

import logging
import os
from typing import Dict, List, Optional, Tuple

LOGGER = logging.getLogger("overseer.legendary")

PLATINUM_GATES = [
    "gate_Z15",
    "gate_A",
    "gate_D",
    "gate_stacked_imbalance",
    "gate_CVD",
    "gate_M",
]

SUPPORTING_GATES = [
    "gate_J",
    "gate_K",
    "gate_FUND",
    "gate_G",
    "gate_iceberg_monitor",
    "gate_FVG",
    "gate_ORDER_BLOCK",
    "gate_SFP",
    "gate_WYCKOFF",
]

LEGENDARY_SCORE_THRESHOLD = float(os.getenv("LEGENDARY_SCORE_THRESHOLD", "0.95"))
LEGENDARY_SUPPORTING_MIN = int(os.getenv("LEGENDARY_SUPPORTING_MIN", "2"))
LEGENDARY_MAX_PER_DAY = int(os.getenv("LEGENDARY_MAX_PER_DAY", "1"))
LEGENDARY_KELLY_FRACTION = float(os.getenv("LEGENDARY_KELLY_FRACTION", "0.75"))
LEGENDARY_TP_RR = float(os.getenv("LEGENDARY_TP_RR", "4.0"))
LEGENDARY_BE_RR = float(os.getenv("LEGENDARY_BE_RR", "1.5"))
LEGENDARY_TRAIL_START_RR = float(os.getenv("LEGENDARY_TRAIL_START_RR", "2.0"))
LEGENDARY_TRAIL_STEP_PIPS = float(os.getenv("LEGENDARY_TRAIL_STEP_PIPS", "5"))
LEGENDARY_KILLZONE_PEAK_ONLY = os.getenv("LEGENDARY_KILLZONE_PEAK_ONLY", "true").lower() in ("true", "1", "yes")


class LegendaryMode:
    def __init__(self):
        self._fired_today: Dict[str, set] = {}
        self._current_date: Optional[str] = None

    def is_legendary(
        self, gate_states: dict, score: float, symbol: str, tick: dict = None
    ) -> Tuple[bool, int, str]:
        """
        Returns (is_legendary, conviction_0_to_100, reason)
        """
        failed_platinum = []
        for gate in PLATINUM_GATES:
            if not gate_states.get(gate, False):
                failed_platinum.append(gate)

        if failed_platinum:
            return False, 0, f"platinum_gate_failed:{','.join(failed_platinum)}"

        if score < LEGENDARY_SCORE_THRESHOLD:
            return False, 0, f"score_below_legendary:{score:.4f}"

        supporting_count = sum(
            1 for g in SUPPORTING_GATES if gate_states.get(g, False)
        )

        if supporting_count < LEGENDARY_SUPPORTING_MIN:
            return (
                False,
                0,
                f"insufficient_supporting_gates:{supporting_count}/{LEGENDARY_SUPPORTING_MIN}",
            )

        if tick:
            wyckoff = tick.get("_wyckoff", {})
            if wyckoff.get("avoid", False):
                return False, 0, f"wyckoff_transition_phase"

            po3_phase = tick.get("_po3_phase", "")
            if po3_phase == "MANIPULATION":
                return False, 0, "po3_manipulation_in_progress"

            if po3_phase == "ACCUMULATION":
                return False, 0, "po3_accumulation_phase"

            kz_quality = tick.get("_killzone_quality", 1.0)
            if LEGENDARY_KILLZONE_PEAK_ONLY and kz_quality < 0.8:
                return False, 0, f"killzone_quality_low:{kz_quality:.2f}"

            roll_status = tick.get("_roll_status", "ACTIVE")
            if roll_status in ("ROLL_NOW",):
                return False, 0, f"futures_roll_period:{roll_status}"

            spread_z = tick.get("_spread_zscore", 0.0)
            if abs(spread_z) > 3.0:
                return False, 0, f"spread_anomaly_z{spread_z:.1f}"

        score_contrib = min(40, int((score - 0.95) / 0.05 * 40))
        platinum_contrib = 40
        supporting_contrib = min(20, int(supporting_count / len(SUPPORTING_GATES) * 20))
        conviction = score_contrib + platinum_contrib + supporting_contrib
        conviction = min(100, conviction)

        if tick:
            po3_bias = tick.get("_po3_bias", "UNKNOWN")
            direction = tick.get("direction", "BUY")
            if po3_bias == direction and tick.get("_po3_manipulation", False):
                conviction = min(100, conviction + 10)

            psych = tick.get("_psych_level", {})
            if psych.get("significance", 0) >= 0.75:
                conviction = min(100, conviction + 5)

        reason = (
            f"LEGENDARY: score={score:.4f} "
            f"platinum=ALL supporting={supporting_count}/{len(SUPPORTING_GATES)} "
            f"conviction={conviction}"
        )

        return True, conviction, reason

    def can_fire_today(self, symbol: str, current_date: str) -> bool:
        if self._current_date != current_date:
            self._fired_today = {}
            self._current_date = current_date

        fired = self._fired_today.get(symbol, set())
        return len(fired) < LEGENDARY_MAX_PER_DAY

    def mark_fired(self, symbol: str, direction: str, current_date: str):
        if self._current_date != current_date:
            self._fired_today = {}
            self._current_date = current_date

        if symbol not in self._fired_today:
            self._fired_today[symbol] = set()
        self._fired_today[symbol].add(direction)

    def compute_legendary_lots(
        self,
        win_rate: float,
        avg_win_pips: float,
        avg_loss_pips: float,
        account_balance: float,
    ) -> float:
        if avg_loss_pips <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0.01
        w = win_rate
        r = avg_win_pips / avg_loss_pips
        kelly = w - ((1 - w) / r)
        if kelly <= 0:
            return 0.01
        legendary_kelly = kelly * LEGENDARY_KELLY_FRACTION
        pip_value = 10.0
        risk_per_lot = avg_loss_pips * pip_value
        if risk_per_lot <= 0:
            return 0.01
        lots = (account_balance * legendary_kelly) / risk_per_lot
        return max(0.01, min(lots, 1.0))

    def compute_legendary_tp(self, sl_pips: float) -> float:
        return sl_pips * LEGENDARY_TP_RR

    def compute_legendary_be_pips(self, sl_pips: float) -> float:
        return sl_pips * LEGENDARY_BE_RR

    def compute_legendary_trail_start(self, sl_pips: float) -> float:
        return sl_pips * LEGENDARY_TRAIL_START_RR

    def get_near_legendary_info(
        self, gate_states: dict, score: float, symbol: str
    ) -> Optional[dict]:
        if score < 0.90:
            return None

        platinum_pass = sum(
            1 for g in PLATINUM_GATES if gate_states.get(g, False)
        )
        if platinum_pass < 4:
            return None

        failed = [
            g for g in PLATINUM_GATES if not gate_states.get(g, False)
        ]
        supporting_count = sum(
            1 for g in SUPPORTING_GATES if gate_states.get(g, False)
        )

        return {
            "score": score,
            "platinum_passed": platinum_pass,
            "platinum_failed": failed,
            "supporting_count": supporting_count,
            "near_legendary": platinum_pass >= 4 and score >= 0.90,
        }


legendary_mode = LegendaryMode()
