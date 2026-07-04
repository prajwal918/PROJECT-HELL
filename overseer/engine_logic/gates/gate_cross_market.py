from __future__ import annotations

import logging
import os
from collections import deque
from typing import Any

import numpy as np

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_cross_market")

MAX_CROSS_SPREAD_PIPS = float(os.getenv("MAX_CROSS_SPREAD_PIPS", "1.5"))
MAX_LEAD_LAG_PIPS = float(os.getenv("MAX_LEAD_LAG_PIPS", "3.0"))
CORRELATION_WINDOW = int(os.getenv("XMKT_CORR_WINDOW", "50"))
MIN_CORRELATION = float(os.getenv("XMKT_MIN_CORRELATION", "0.70"))
ARB_MIN_LAG_PIPS = float(os.getenv("XMKT_ARB_MIN_LAG_PIPS", "2.0"))
ARB_MAX_LAG_PIPS = float(os.getenv("XMKT_ARB_MAX_LAG_PIPS", "10.0"))


class GateCrossMarketSync(BaseGate):
    gate_name = "gate_XMKT"
    priority = 5

    def evaluate(self, tick: dict[str, Any]) -> bool:
        spot_spread = float(tick.get("spot_spread_pips", 0.0))
        max_spread = float(tick.get("cross_spread_max_pips", MAX_CROSS_SPREAD_PIPS))
        if spot_spread > max_spread:
            LOGGER.debug("Cross-market BLOCKED: spot spread %.1f > max %.1f", spot_spread, max_spread)
            return False
        return True


class GateLeadLag(BaseGate):
    gate_name = "gate_LEADLAG"
    priority = 6

    def evaluate(self, tick: dict[str, Any]) -> bool:
        lag_pips = float(tick.get("lead_lag_pips", 0.0))
        max_lag = float(tick.get("lead_lag_max_pips", MAX_LEAD_LAG_PIPS))
        if abs(lag_pips) > max_lag:
            LOGGER.debug("Lead-lag BLOCKED: lag %.2f pips exceeds max %.2f", lag_pips, max_lag)
            return False
        return True

    def calculate_lead_lag(self, rithmic_price: float, spot_price: float, pip_size: float = 0.0001) -> float:
        if pip_size <= 0:
            return 0.0
        return (rithmic_price - spot_price) / pip_size


class GateRollingCorrelation(BaseGate):
    gate_name = "gate_XCORR"
    priority = 5

    def __init__(self) -> None:
        self._cme_mids: deque[float] = deque(maxlen=CORRELATION_WINDOW)
        self._spot_mids: deque[float] = deque(maxlen=CORRELATION_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        cme_mid = float(tick.get("rithmic_price", 0.0))
        spot_mid = float(tick.get("deriv_price", 0.0))
        if cme_mid <= 0 or spot_mid <= 0:
            return True
        self._cme_mids.append(cme_mid)
        self._spot_mids.append(spot_mid)
        if len(self._cme_mids) < 20:
            return True
        cme_arr = np.array(self._cme_mids)
        spot_arr = np.array(self._spot_mids)
        if np.std(cme_arr) == 0 or np.std(spot_arr) == 0:
            return True
        corr = float(np.corrcoef(cme_arr, spot_arr)[0, 1])
        return abs(corr) >= MIN_CORRELATION


class GateArbitrage(BaseGate):
    gate_name = "gate_ARB"
    priority = 4

    def __init__(self) -> None:
        self._last_arb_time: float = 0.0

    def evaluate(self, tick: dict[str, Any]) -> bool:
        lag_pips = float(tick.get("lead_lag_pips", 0.0))
        abs_lag = abs(lag_pips)
        min_arb = float(tick.get("arb_min_lag_pips", ARB_MIN_LAG_PIPS))
        max_arb = float(tick.get("arb_max_lag_pips", ARB_MAX_LAG_PIPS))
        if abs_lag < min_arb:
            return True
        if abs_lag > max_arb:
            LOGGER.debug("Arbitrage gate BLOCKED: lag %.2f pips exceeds max %.2f - markets disconnected", lag_pips, max_arb)
            return False
        now = time.monotonic() if hasattr(self, '_last_arb_time') else 0.0
        import time as _time
        now = _time.monotonic()
        if now - self._last_arb_time < 1.0:
            return True
        self._last_arb_time = now
        LOGGER.debug("Arbitrage opportunity: lag=%.2f pips", lag_pips)
        return True
