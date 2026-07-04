import os
import logging
import numpy as np
from collections import deque

log = logging.getLogger(__name__)

_ENABLED = os.getenv("SIGNAL_ENTROPY_ENABLED", "true").lower() == "true"
_WINDOW = int(os.getenv("SIGNAL_ENTROPY_WINDOW", "50"))
_HIGH_ENTROPY_THRESHOLD = float(os.getenv("SIGNAL_ENTROPY_HIGH", "0.70"))
_LOW_ENTROPY_THRESHOLD = float(os.getenv("SIGNAL_ENTROPY_LOW", "0.30"))
_HIGH_ENTROPY_MULT = float(os.getenv("SIGNAL_ENTROPY_HIGH_MULT", "0.80"))
_LOW_ENTROPY_MULT = float(os.getenv("SIGNAL_ENTROPY_LOW_MULT", "1.15"))


class SignalEntropy:
    def __init__(self):
        self._gate_fire_rates = {}

    def on_signal(self, gate_states):
        if not _ENABLED:
            return
        for gate, val in gate_states.items():
            if gate not in self._gate_fire_rates:
                self._gate_fire_rates[gate] = deque(maxlen=_WINDOW)
            self._gate_fire_rates[gate].append(1.0 if val else 0.0)

    def compute_entropy(self):
        if not _ENABLED:
            return 0.5, 1.0
        rates = []
        for gate, vals in self._gate_fire_rates.items():
            if len(vals) >= 5:
                rate = sum(vals) / len(vals)
                if 0 < rate < 1:
                    rates.append(rate)
        if not rates:
            return 0.5, 1.0
        rates = np.array(rates)
        rates = rates / rates.sum()
        ent = -np.sum(rates * np.log(rates + 1e-10))
        max_ent = np.log(len(rates))
        normalized = ent / max_ent if max_ent > 0 else 0.5
        if normalized > _HIGH_ENTROPY_THRESHOLD:
            mult = _HIGH_ENTROPY_MULT
        elif normalized < _LOW_ENTROPY_THRESHOLD:
            mult = _LOW_ENTROPY_MULT
        else:
            mult = 1.0
        return normalized, mult


signal_entropy = SignalEntropy()
