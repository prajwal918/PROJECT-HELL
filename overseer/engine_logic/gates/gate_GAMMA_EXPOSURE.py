from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_GAMMA_EXPOSURE")

_GAMMA_WALL_PIPS = float(__import__("os").getenv("GAMMA_WALL_PIPS", "15.0"))


class GateGammaExposure(BaseGate):
    gate_name = "gate_GAMMA_EXPOSURE"
    priority = 40

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")
        symbol = tick.get("symbol", "")
        mid = (float(tick.get("bid", 0)) + float(tick.get("ask", 0))) / 2.0
        if mid <= 0:
            return False
        pip_size = float(tick.get("pip_size", 0.0001))

        try:
            from tools.gamma_scraper import gamma_scraper
            exposure = gamma_scraper.get_gamma_exposure(symbol, mid)
        except Exception:
            return False

        if not exposure:
            return False

        gamma_net = float(exposure.get("net_gamma", 0))
        call_wall = float(exposure.get("call_wall", 0))
        put_wall = float(exposure.get("put_wall", 0))

        if call_wall > 0 and put_wall > 0:
            dist_to_call_wall = abs(call_wall - mid) / pip_size
            dist_to_put_wall = abs(put_wall - mid) / pip_size
        else:
            return False

        if direction == "BUY":
            if gamma_net > 0 and dist_to_put_wall < _GAMMA_WALL_PIPS:
                return True
            if put_wall > call_wall and dist_to_put_wall < _GAMMA_WALL_PIPS * 2:
                return True

        if direction == "SELL":
            if gamma_net < 0 and dist_to_call_wall < _GAMMA_WALL_PIPS:
                return True
            if call_wall > put_wall and dist_to_call_wall < _GAMMA_WALL_PIPS * 2:
                return True

        return False
