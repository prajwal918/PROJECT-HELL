from __future__ import annotations

import logging
from typing import Any
from datetime import datetime, timezone

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_LONDON_FIX")

_FIX_START_HOUR = int(__import__("os").getenv("LONDON_FIX_START_HOUR", "15"))
_FIX_END_HOUR = int(__import__("os").getenv("LONDON_FIX_END_HOUR", "16"))
_FIX_WINDOW_MINUTES = int(__import__("os").getenv("LONDON_FIX_WINDOW_MINUTES", "25"))


class GateLondonFix(BaseGate):
    gate_name = "gate_LONDON_FIX"
    priority = 37

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")

        try:
            ts_str = tick.get("timestamp", "")
            if ts_str:
                if "T" in ts_str:
                    now_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                else:
                    now_utc = datetime.fromisoformat(ts_str + "+00:00")
            else:
                now_utc = datetime.now(timezone.utc)
        except Exception:
            now_utc = datetime.now(timezone.utc)

        hour = now_utc.hour
        minute = now_utc.minute

        in_fix_window = False
        if hour == _FIX_START_HOUR and minute < _FIX_WINDOW_MINUTES:
            in_fix_window = True
        elif hour == _FIX_END_HOUR and minute < 15:
            in_fix_window = True

        if not in_fix_window:
            return False

        cumulative_delta = float(tick.get("cumulative_delta", 0))
        l3_pred = 0.0
        l3_info = tick.get("_l3_features", {})
        if isinstance(l3_info, dict):
            l3_pred = float(l3_info.get("l3_prediction", 0))

        if direction == "BUY" and (cumulative_delta > 0 or l3_pred > 0.3):
            return True
        if direction == "SELL" and (cumulative_delta < 0 or l3_pred < -0.3):
            return True

        return False
