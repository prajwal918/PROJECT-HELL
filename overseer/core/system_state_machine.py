import os
import logging
from enum import Enum

log = logging.getLogger(__name__)

_ENABLED = os.getenv("SYSTEM_STATE_MACHINE_ENABLED", "true").lower() == "true"


class SystemState(Enum):
    CONFIDENT = "confident"
    CAUTIOUS = "cautious"
    DEFENSIVE = "defensive"
    HALTED = "halted"


class SystemStateMachine:
    def __init__(self):
        self._warnings = []
        self._state = SystemState.CONFIDENT
        self._confidence = 1.0

    def evaluate(self, drift_active=False, spread_zscore=0.0, consecutive_losses=0,
                 kyle_lambda_ratio=1.0, system_health=1.0, network_quality="EXCELLENT",
                 topology_drift=0.0, amihud_z=0.0, flash_crash=False,
                 drawdown_velocity=0.0, regime_uncertain=False):
        if not _ENABLED:
            return SystemState.CONFIDENT, 1.0
        self._warnings = []
        if drift_active:
            self._warnings.append("MODEL_DRIFT")
        if abs(spread_zscore) > 2.5:
            self._warnings.append("SPREAD_ANOMALY")
        if consecutive_losses >= 2:
            self._warnings.append("LOSS_STREAK")
        if kyle_lambda_ratio > 2.0:
            self._warnings.append("INFORMED_FLOW")
        if system_health < 0.90:
            self._warnings.append("SYSTEM_STRESS")
        if network_quality == "DEGRADED":
            self._warnings.append("NETWORK_ISSUE")
        if topology_drift > 0.5:
            self._warnings.append("REGIME_SHIFT")
        if amihud_z > 2.0:
            self._warnings.append("ILLIQUIDITY")
        if flash_crash:
            self._warnings.append("FLASH_CRASH")
        if drawdown_velocity < -50:
            self._warnings.append("DRAWDOWN_VELOCITY")
        if regime_uncertain:
            self._warnings.append("REGIME_UNCERTAIN")
        n = len(self._warnings)
        if n == 0:
            self._state = SystemState.CONFIDENT
            self._confidence = 1.00
        elif n <= 2:
            self._state = SystemState.CAUTIOUS
            self._confidence = 0.75
        elif n <= 4:
            self._state = SystemState.DEFENSIVE
            self._confidence = 0.50
        else:
            self._state = SystemState.HALTED
            self._confidence = 0.00
        return self._state, self._confidence

    def get_size_multiplier(self):
        return self._confidence

    @property
    def state(self):
        return self._state

    @property
    def warnings(self):
        return list(self._warnings)


system_state_machine = SystemStateMachine()
