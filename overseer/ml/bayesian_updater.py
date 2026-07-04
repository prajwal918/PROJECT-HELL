"""Bayesian Score Updating for OVERSEER v13.

After a signal fires, observes the next 3 ticks to update the
prior (XGBoost score) with tick-level likelihood. The posterior
indicates whether the signal is strengthening or weakening:

- posterior > prior  → signal strengthening → enter (or full size)
- posterior < prior  → signal weakening → skip or reduce size
- posterior collapsed → abort

Uses a simple Beta-Binomial conjugate update:
  prior = Beta(alpha, beta) parameterized from XGBoost score
  Each tick provides a Bernoulli likelihood: favorable or unfavorable
  posterior = Beta(alpha + favorable, beta + unfavorable)
"""

from __future__ import annotations

import logging
import math
import os
from typing import Dict, Optional, Tuple

LOGGER = logging.getLogger("overseer.bayesian_updater")

_ENABLED = os.getenv("BAYESIAN_UPDATER_ENABLED", "true").lower() == "true"
_OBSERVATION_TICKS = int(os.getenv("BAYESIAN_OBSERVATION_TICKS", "3"))
_PRIOR_STRENGTH = float(os.getenv("BAYESIAN_PRIOR_STRENGTH", "10.0"))
_COLLAPSE_THRESHOLD = float(os.getenv("BAYESIAN_COLLAPSE_THRESHOLD", "0.10"))
_WEAKEN_THRESHOLD = float(os.getenv("BAYESIAN_WEAKEN_THRESHOLD", "0.0"))


class Observation:
    """Track Bayesian observation state for a single symbol."""

    __slots__ = ("alpha", "beta", "prior_score", "direction", "ticks_observed", "favorable")

    def __init__(self, prior_score: float, direction: str) -> None:
        self.prior_score = prior_score
        self.direction = direction
        self.alpha = prior_score * _PRIOR_STRENGTH
        self.beta = (1.0 - prior_score) * _PRIOR_STRENGTH
        self.ticks_observed = 0
        self.favorable = 0

    @property
    def posterior(self) -> float:
        total = self.alpha + self.beta
        if total <= 0:
            return self.prior_score
        return self.alpha / total


class BayesianUpdater:
    """Update XGBoost signal scores with tick-level Bayesian inference."""

    def __init__(self) -> None:
        self._observations: Dict[str, Observation] = {}
        self._completed: Dict[str, Tuple[float, str]] = {}

    def start_observation(self, symbol: str, prior_score: float, direction: str) -> None:
        if not _ENABLED:
            return
        obs = Observation(prior_score, direction)
        self._observations[symbol] = obs
        self._completed.pop(symbol, None)

        LOGGER.debug(
            "Bayesian %s: start obs prior=%.4f dir=%s alpha=%.1f beta=%.1f",
            symbol, prior_score, direction, obs.alpha, obs.beta,
        )

    def observe_tick(self, symbol: str, tick_direction: str, tick_volume: float = 1.0) -> None:
        if not _ENABLED:
            return

        obs = self._observations.get(symbol)
        if obs is None:
            return

        if obs.ticks_observed >= _OBSERVATION_TICKS:
            return

        obs.ticks_observed += 1

        is_favorable = False
        if obs.direction == "BUY" and tick_direction == "BUY":
            is_favorable = True
        elif obs.direction == "SELL" and tick_direction == "SELL":
            is_favorable = True

        volume_factor = min(tick_volume / 10.0, 3.0) if tick_volume > 0 else 1.0

        if is_favorable:
            obs.alpha += volume_factor
            obs.favorable += 1
        else:
            obs.beta += volume_factor

        if obs.ticks_observed >= _OBSERVATION_TICKS:
            posterior = obs.posterior
            delta = posterior - obs.prior_score

            if posterior < _COLLAPSE_THRESHOLD:
                action = "abort"
            elif delta < _WEAKEN_THRESHOLD - 0.02:
                action = "skip"
            elif delta < _WEAKEN_THRESHOLD:
                action = "reduce"
            elif delta > 0.02:
                action = "enter"
            elif delta > 0:
                action = "enter_small"
            else:
                action = "enter_small"

            self._completed[symbol] = (posterior, action)

            LOGGER.info(
                "Bayesian %s: prior=%.4f posterior=%.4f delta=%+.4f ticks=%d fav=%d action=%s",
                symbol, obs.prior_score, posterior, delta,
                obs.ticks_observed, obs.favorable, action,
            )
            self._observations.pop(symbol, None)

    def get_posterior(self, symbol: str) -> Tuple[float, str]:
        if not _ENABLED:
            return (0.0, "disabled")

        completed = self._completed.get(symbol)
        if completed is not None:
            return completed

        obs = self._observations.get(symbol)
        if obs is None:
            return (0.0, "no_observation")

        if obs.ticks_observed >= _OBSERVATION_TICKS:
            return (obs.posterior, "completed")

        return (obs.posterior, "observing")

    def is_observing(self, symbol: str) -> bool:
        return symbol in self._observations

    def clear(self, symbol: str) -> None:
        self._observations.pop(symbol, None)
        self._completed.pop(symbol, None)

    def get_all_states(self) -> Dict[str, Dict[str, object]]:
        result = {}
        for sym, obs in self._observations.items():
            result[sym] = {
                "prior": obs.prior_score,
                "posterior": obs.posterior,
                "direction": obs.direction,
                "ticks_observed": obs.ticks_observed,
                "favorable": obs.favorable,
                "status": "observing",
            }
        for sym, (posterior, action) in self._completed.items():
            result[sym] = {
                "posterior": posterior,
                "action": action,
                "status": "completed",
            }
        return result


bayesian_updater = BayesianUpdater()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bu = bayesian_updater
    bu.start_observation("6EM6", 0.92, "BUY")
    bu.observe_tick("6EM6", "BUY", 15.0)
    p, a = bu.get_posterior("6EM6")
    print(f"  After 1 tick: posterior={p:.4f} action={a}")
    bu.observe_tick("6EM6", "SELL", 8.0)
    p, a = bu.get_posterior("6EM6")
    print(f"  After 2 ticks: posterior={p:.4f} action={a}")
    bu.observe_tick("6EM6", "BUY", 12.0)
    p, a = bu.get_posterior("6EM6")
    print(f"  After 3 ticks: posterior={p:.4f} action={a}")

    bu.start_observation("6BM6", 0.88, "SELL")
    bu.observe_tick("6BM6", "BUY", 20.0)
    bu.observe_tick("6BM6", "BUY", 15.0)
    bu.observe_tick("6BM6", "BUY", 10.0)
    p, a = bu.get_posterior("6BM6")
    print(f"  6BM6 weakening: posterior={p:.4f} action={a}")
