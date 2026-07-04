#!/usr/bin/env python3
"""
Scale-In Engine — 3-tranche institutional entry.

Institutions never put the full position on at one price.
They scale in: partial on signal, add on confirmation, add on acceleration.

Tranche 1 (33%): Initial signal fires
Tranche 2 (34%): Price moves 1 pip in direction (first confirmation)
Tranche 3 (33%): gate_G fires or volume acceleration (momentum confirmation)

Average entry is better. Risk per trade is lower.
"""

import logging
import os
from typing import Dict, Optional, Tuple

LOGGER = logging.getLogger("overseer.scale_in")

SCALE_IN_ENABLED = os.getenv("SCALE_IN_ENABLED", "true").lower() in ("true", "1", "yes")
CONFIRMATION_PIPS = float(os.getenv("SCALE_IN_CONFIRMATION_PIPS", "1.0"))
MAX_WAIT_TICKS = int(os.getenv("SCALE_IN_MAX_WAIT_TICKS", "50"))


class ScaleInEngine:
    TRANCHES = [
        {"pct": 0.33, "trigger": "initial_signal"},
        {"pct": 0.34, "trigger": "first_confirmation"},
        {"pct": 0.33, "trigger": "momentum_acceleration"},
    ]

    def __init__(self):
        self._active: Dict[str, Dict] = {}

    def get_initial_lot(self, full_lot: float) -> float:
        """First tranche: 33% of full position."""
        return max(0.01, round(full_lot * self.TRANCHES[0]["pct"], 2))

    def start_scale_in(
        self,
        symbol: str,
        direction: str,
        full_lot: float,
        entry_price: float,
        pip_size: float,
        gate_states: dict = None,
    ) -> Dict:
        """Register the start of a scale-in sequence."""
        state = {
            "symbol": symbol,
            "direction": direction,
            "full_lot": full_lot,
            "entry_price": entry_price,
            "pip_size": pip_size,
            "tranches_filled": 1,
            "tranche_1_lot": self.get_initial_lot(full_lot),
            "tranche_2_lot": round(full_lot * self.TRANCHES[1]["pct"], 2),
            "tranche_3_lot": round(full_lot * self.TRANCHES[2]["pct"], 2),
            "best_price": entry_price,
            "ticks_since_entry": 0,
            "gate_g_fired": False,
            "completed": False,
        }

        if gate_states:
            state["gate_g_fired"] = gate_states.get("gate_G", False)

        self._active[symbol] = state
        LOGGER.info(
            "[SCALE_IN] %s %s tranche_1=%.2f (of %.2f) entry=%.5f",
            direction, symbol, state["tranche_1_lot"], full_lot, entry_price,
        )

        return {
            "action": "execute_initial",
            "lot": state["tranche_1_lot"],
            "remaining_lot": full_lot - state["tranche_1_lot"],
            "tranches_remaining": 2,
        }

    def should_add_tranche(
        self,
        symbol: str,
        current_price: float,
        gate_states: dict = None,
    ) -> Dict:
        """
        Check if we should add the next tranche.
        Returns action: 'add_tranche_2', 'add_tranche_3', 'hold', 'cancel'
        """
        if symbol not in self._active:
            return {"action": "no_active_scale_in"}

        state = self._active[symbol]
        if state["completed"]:
            return {"action": "completed"}

        state["ticks_since_entry"] += 1
        direction = state["direction"]
        pip_size = state["pip_size"]
        entry = state["entry_price"]

        if direction == "BUY":
            pips_moved = (current_price - entry) / pip_size
            state["best_price"] = max(state["best_price"], current_price)
        else:
            pips_moved = (entry - current_price) / pip_size
            state["best_price"] = min(state["best_price"], current_price)

        if state["ticks_since_entry"] > MAX_WAIT_TICKS:
            LOGGER.info(
                "[SCALE_IN] %s %s timed out after %d ticks — completing with %d tranches",
                direction, symbol, state["ticks_since_entry"], state["tranches_filled"],
            )
            state["completed"] = True
            return {"action": "timeout", "tranches_filled": state["tranches_filled"]}

        if gate_states and gate_states.get("gate_G", False):
            state["gate_g_fired"] = True

        if state["tranches_filled"] == 1:
            if pips_moved >= CONFIRMATION_PIPS:
                lot = state["tranche_2_lot"]
                state["tranches_filled"] = 2
                LOGGER.info(
                    "[SCALE_IN] %s %s tranche_2=%.2f confirmed at +%.1f pips",
                    direction, symbol, lot, pips_moved,
                )
                return {
                    "action": "add_tranche_2",
                    "lot": lot,
                    "remaining_lot": state["tranche_3_lot"],
                    "tranches_remaining": 1,
                }
            return {"action": "hold", "pips_moved": round(pips_moved, 1)}

        if state["tranches_filled"] == 2:
            if state["gate_g_fired"] or pips_moved >= CONFIRMATION_PIPS * 3:
                lot = state["tranche_3_lot"]
                state["tranches_filled"] = 3
                state["completed"] = True
                LOGGER.info(
                    "[SCALE_IN] %s %s tranche_3=%.2f momentum confirmed at +%.1f pips",
                    direction, symbol, lot, pips_moved,
                )
                return {
                    "action": "add_tranche_3",
                    "lot": lot,
                    "remaining_lot": 0,
                    "tranches_remaining": 0,
                }
            return {"action": "hold", "pips_moved": round(pips_moved, 1)}

        return {"action": "hold"}

    def cancel_scale_in(self, symbol: str) -> Optional[Dict]:
        """Cancel an incomplete scale-in (e.g., stop loss hit on tranche 1)."""
        if symbol not in self._active:
            return None
        state = self._active.pop(symbol)
        LOGGER.info(
            "[SCALE_IN] %s %s cancelled after %d tranches",
            state["direction"], symbol, state["tranches_filled"],
        )
        return {"action": "cancelled", "tranches_filled": state["tranches_filled"]}

    def complete_scale_in(self, symbol: str):
        """Mark a scale-in as fully complete."""
        if symbol in self._active:
            self._active[symbol]["completed"] = True

    def is_active(self, symbol: str) -> bool:
        return symbol in self._active and not self._active[symbol]["completed"]

    def get_state(self, symbol: str) -> Optional[Dict]:
        return self._active.get(symbol)
