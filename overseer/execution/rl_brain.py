"""Tabular RL Execution Brain — learns optimal micro-execution from experience.

State: [spread_bucket, delta_bucket, queue_depth_bucket, time_since_print_bucket]
Actions: [market_order, limit_at_bid+0.1, limit_at_bid+0.2, wait_1_tick, cancel_reenter]
Reward: +slippage_saved vs market baseline, -opportunity_cost, -adverse_selection_penalty

Uses Q-table (not neural network) — 0.01ms update time, perfect for 2 cores.
"""
from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.rl_brain")

RL_LR = float(os.getenv("RL_LR", "0.1"))
RL_GAMMA = float(os.getenv("RL_GAMMA", "0.95"))
RL_EPSILON = float(os.getenv("RL_EPSILON", "0.15"))
RL_EPSILON_DECAY = float(os.getenv("RL_EPSILON_DECAY", "0.999"))
RL_EPSILON_MIN = float(os.getenv("RL_EPSILON_MIN", "0.02"))
RL_SPREAD_BINS = int(os.getenv("RL_SPREAD_BINS", "5"))
RL_DELTA_BINS = int(os.getenv("RL_DELTA_BINS", "5"))
RL_DEPTH_BINS = int(os.getenv("RL_DEPTH_BINS", "5"))
RL_TIME_BINS = int(os.getenv("RL_TIME_BINS", "4"))
RL_N_ACTIONS = 5
RL_ACTIONS = ["market_buy", "limit_bid_plus_0.1", "limit_bid_plus_0.2", "wait_1_tick", "cancel_reenter"]


class TabularRLBrain:
    """Q-table execution brain. Learns from fill experience."""

    def __init__(self) -> None:
        self._q_table: dict[tuple, np.ndarray] = {}
        self.lr = RL_LR
        self.gamma = RL_GAMMA
        self.epsilon = RL_EPSILON
        self._update_count: int = 0
        self._experience: deque[dict[str, Any]] = deque(maxlen=50000)

    def _discretize(self, spread_bps: float, delta: float, queue_depth: float, time_since_print_ms: float) -> tuple:
        s_bin = min(RL_SPREAD_BINS - 1, max(0, int(spread_bps / 2)))
        d_bin = min(RL_DELTA_BINS - 1, max(0, int((delta + 100) / 40)))
        q_bin = min(RL_DEPTH_BINS - 1, max(0, int(queue_depth / 50)))
        t_bin = min(RL_TIME_BINS - 1, max(0, int(time_since_print_ms / 500)))
        return (s_bin, d_bin, q_bin, t_bin)

    def select_action(self, spread_bps: float, delta: float, queue_depth: float, time_since_print_ms: float) -> tuple[int, str]:
        state = self._discretize(spread_bps, delta, queue_depth, time_since_print_ms)
        if state not in self._q_table:
            self._q_table[state] = np.zeros(RL_N_ACTIONS)
        if np.random.random() < self.epsilon:
            action = np.random.randint(RL_N_ACTIONS)
        else:
            action = int(np.argmax(self._q_table[state]))
        self.epsilon = max(RL_EPSILON_MIN, self.epsilon * RL_EPSILON_DECAY)
        return action, RL_ACTIONS[action]

    def update(self, spread_bps: float, delta: float, queue_depth: float, time_since_print_ms: float, action: int, reward: float, next_spread: float, next_delta: float, next_depth: float, next_time: float, done: bool = False) -> None:
        state = self._discretize(spread_bps, delta, queue_depth, time_since_print_ms)
        next_state = self._discretize(next_spread, next_delta, next_depth, next_time)
        if state not in self._q_table:
            self._q_table[state] = np.zeros(RL_N_ACTIONS)
        if next_state not in self._q_table:
            self._q_table[next_state] = np.zeros(RL_N_ACTIONS)
        current_q = self._q_table[state][action]
        if done:
            target = reward
        else:
            target = reward + self.gamma * np.max(self._q_table[next_state])
        self._q_table[state][action] += self.lr * (target - current_q)
        self._update_count += 1
        self._experience.append({
            "state": state, "action": action, "reward": reward,
            "next_state": next_state, "done": done,
        })

    def compute_reward(self, slippage_pips: float, market_slippage_pips: float, filled: bool, price_ran_away_pips: float = 0.0, adverse_reversal_pips: float = 0.0) -> float:
        if not filled:
            return -price_ran_away_pips * 0.5
        slippage_saved = market_slippage_pips - slippage_pips
        reward = slippage_saved * 1.0
        if adverse_reversal_pips > 1.0:
            reward -= adverse_reversal_pips * 0.5
        return reward

    def get_best_action_for_state(self, spread_bps: float, delta: float, queue_depth: float, time_since_print_ms: float) -> dict[str, Any]:
        state = self._discretize(spread_bps, delta, queue_depth, time_since_print_ms)
        if state not in self._q_table:
            return {"action": "market_buy", "q_values": [0.0] * RL_N_ACTIONS, "confidence": 0.0, "explored": False}
        q = self._q_table[state]
        best = int(np.argmax(q))
        q_range = float(q.max() - q.min())
        confidence = min(1.0, q_range / 2.0) if q_range > 0 else 0.0
        return {
            "action": RL_ACTIONS[best],
            "action_idx": best,
            "q_values": [round(float(v), 4) for v in q],
            "confidence": round(confidence, 4),
            "explored": True,
        }

    def train_from_history(self) -> dict[str, Any]:
        if len(self._experience) < 100:
            return {"trained": False, "samples": len(self._experience)}
        losses = []
        for exp in list(self._experience)[-5000:]:
            state = exp["state"]
            action = exp["action"]
            reward = exp["reward"]
            next_state = exp["next_state"]
            done = exp["done"]
            if state not in self._q_table:
                self._q_table[state] = np.zeros(RL_N_ACTIONS)
            if next_state not in self._q_table:
                self._q_table[next_state] = np.zeros(RL_N_ACTIONS)
            current_q = self._q_table[state][action]
            target = reward if done else reward + self.gamma * np.max(self._q_table[next_state])
            loss = abs(target - current_q)
            self._q_table[state][action] += self.lr * (target - current_q)
            losses.append(loss)
        avg_loss = float(np.mean(losses)) if losses else 0.0
        return {"trained": True, "samples": len(self._experience), "avg_loss": round(avg_loss, 4)}

    def get_policy_summary(self) -> dict[str, Any]:
        action_counts = [0] * RL_N_ACTIONS
        for q in self._q_table.values():
            best = int(np.argmax(q))
            action_counts[best] += 1
        return {
            "states_explored": len(self._q_table),
            "updates": self._update_count,
            "epsilon": round(self.epsilon, 4),
            "best_action_distribution": {RL_ACTIONS[i]: action_counts[i] for i in range(RL_N_ACTIONS)},
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "states": len(self._q_table),
            "updates": self._update_count,
            "epsilon": round(self.epsilon, 4),
            "experience_buffer": len(self._experience),
        }
