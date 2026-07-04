from __future__ import annotations

import logging
import math
import os
import random
from typing import Any, Dict, List, Optional, Tuple

LOGGER = logging.getLogger("overseer.rl_exit_agent")

_ENABLED = os.getenv("RL_EXIT_AGENT_ENABLED", "true").lower() == "true"
_LR = float(os.getenv("RL_EXIT_LR", "0.1"))
_GAMMA = float(os.getenv("RL_EXIT_GAMMA", "0.95"))
_EPSILON = float(os.getenv("RL_EXIT_EPSILON", "0.1"))
_HOLD_PENALTY = float(os.getenv("RL_EXIT_HOLD_PENALTY", "0.01"))
_SL_PENALTY = float(os.getenv("RL_EXIT_SL_PENALTY", "1.0"))
_PNL_BINS = int(os.getenv("RL_EXIT_PNL_BINS", "10"))
_TICKS_BINS = int(os.getenv("RL_EXIT_TICKS_BINS", "8"))
_DIST_BINS = int(os.getenv("RL_EXIT_DIST_BINS", "5"))

_ACTIONS = ("HOLD", "EXIT_NOW", "MOVE_SL_BE")


class RLExitAgent:
    def __init__(self) -> None:
        self._q: Dict[str, Dict[str, float]] = {}
        self._lr = _LR
        self._gamma = _GAMMA
        self._epsilon = _EPSILON
        self._n_updates = 0

    def _discretize(self, value: float, n_bins: int, lo: float, hi: float) -> int:
        if hi <= lo:
            return 0
        t = (value - lo) / (hi - lo)
        t = max(0.0, min(1.0, t))
        return min(int(t * n_bins), n_bins - 1)

    def _state_key(self, state_dict: Dict[str, Any]) -> str:
        pnl = float(state_dict.get("pnl", 0.0))
        ticks = int(state_dict.get("ticks_in_trade", 0))
        regime = str(state_dict.get("regime", "unknown"))[:4]
        velocity = float(state_dict.get("tape_velocity", 0.0))
        dist_tp = float(state_dict.get("dist_to_tp", 0.0))
        dist_sl = float(state_dict.get("dist_to_sl", 0.0))
        ofi = float(state_dict.get("ofi", 0.0))
        spread = float(state_dict.get("spread", 0.0))
        pnl_bin = self._discretize(pnl, _PNL_BINS, -50.0, 50.0)
        ticks_bin = self._discretize(float(ticks), _TICKS_BINS, 0.0, 500.0)
        vel_bin = self._discretize(velocity, 5, 0.0, 5.0)
        dtp_bin = self._discretize(dist_tp, _DIST_BINS, 0.0, 50.0)
        dsl_bin = self._discretize(dist_sl, _DIST_BINS, 0.0, 20.0)
        ofi_bin = self._discretize(ofi, 5, -1.0, 1.0)
        spread_bin = self._discretize(spread, 4, 0.0, 5.0)
        return "p{}t{}r{}v{}tp{}sl{}o{}s{}".format(
            pnl_bin, ticks_bin, regime, vel_bin, dtp_bin, dsl_bin, ofi_bin, spread_bin
        )

    def _ensure_state(self, state_key: str) -> None:
        if state_key not in self._q:
            self._q[state_key] = {a: 0.0 for a in _ACTIONS}

    def get_action(self, state_dict: Dict[str, Any]) -> str:
        if not _ENABLED:
            return "HOLD"
        state_key = self._state_key(state_dict)
        self._ensure_state(state_key)
        if random.random() < self._epsilon:
            return random.choice(list(_ACTIONS))
        q_vals = self._q[state_key]
        best_action = max(_ACTIONS, key=lambda a: q_vals[a])
        return best_action

    def update(
        self,
        state: Dict[str, Any],
        action: str,
        reward: float,
        next_state: Dict[str, Any],
    ) -> None:
        if not _ENABLED:
            return
        self._n_updates += 1
        state_key = self._state_key(state)
        next_key = self._state_key(next_state)
        self._ensure_state(state_key)
        self._ensure_state(next_key)
        best_next = max(self._q[next_key].values())
        old_q = self._q[state_key].get(action, 0.0)
        new_q = old_q + self._lr * (reward + self._gamma * best_next - old_q)
        self._q[state_key][action] = new_q

    def compute_reward(
        self,
        action: str,
        pnl: float,
        hit_sl: bool,
        ticks_in_trade: int,
    ) -> float:
        if action == "EXIT_NOW":
            return pnl
        if action == "MOVE_SL_BE":
            return 0.0
        if hit_sl:
            return -abs(pnl) - _SL_PENALTY
        return -_HOLD_PENALTY * ticks_in_trade

    def get_q_values(self, state_dict: Dict[str, Any]) -> Dict[str, float]:
        state_key = self._state_key(state_dict)
        self._ensure_state(state_key)
        return dict(self._q[state_key])

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": _ENABLED,
            "n_states": len(self._q),
            "n_updates": self._n_updates,
            "epsilon": self._epsilon,
            "actions": list(_ACTIONS),
        }


rl_exit_agent = RLExitAgent()
