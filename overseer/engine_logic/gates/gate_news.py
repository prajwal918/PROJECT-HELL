from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_news")

NEWS_CACHE_PATH = Path(__file__).resolve().parents[2] / "config" / "economic_calendar.json"
NEWS_BLOCK_MINUTES_BEFORE = int(os.getenv("NEWS_BLOCK_MINUTES_BEFORE", "30"))
NEWS_BLOCK_MINUTES_AFTER = int(os.getenv("NEWS_BLOCK_MINUTES_AFTER", "5"))
HIGH_IMPACT_EVENTS = {
    "Nonfarm Payrolls", "NFP", "Unemployment Rate",
    "FOMC", "Fed Interest Rate", "Federal Funds Rate",
    "CPI", "Consumer Price Index", "Core CPI",
    "GDP", "Gross Domestic Product",
    "Retail Sales", "ISM Manufacturing", "ISM Non-Manufacturing",
    "ECB Interest Rate", "BOE Interest Rate", "BOJ Interest Rate",
}

SESSION_LONDON_START = int(os.getenv("SESSION_LONDON_START", "7"))
SESSION_LONDON_END = int(os.getenv("SESSION_LONDON_END", "16"))
SESSION_NY_START = int(os.getenv("SESSION_NY_START", "12"))
SESSION_NY_END = int(os.getenv("SESSION_NY_END", "21"))
SESSION_ASIA_START = int(os.getenv("SESSION_ASIA_START", "0"))
SESSION_ASIA_END = int(os.getenv("SESSION_ASIA_END", "8"))

REGIME_WINDOW = int(os.getenv("REGIME_WINDOW", "50"))
REGIME_TRENDING_ATR_MULT = float(os.getenv("REGIME_TRENDING_ATR_MULT", "1.5"))


def _load_calendar() -> list[dict[str, Any]]:
    if not NEWS_CACHE_PATH.exists():
        return []
    try:
        return json.loads(NEWS_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        LOGGER.warning("Failed to load economic calendar: %s", exc)
        return []


def _get_session(utc_hour: int) -> str:
    in_london = SESSION_LONDON_START <= utc_hour < SESSION_LONDON_END
    in_ny = SESSION_NY_START <= utc_hour < SESSION_NY_END
    in_asia = SESSION_ASIA_START <= utc_hour < SESSION_ASIA_END
    if in_london and in_ny:
        return "london_ny_overlap"
    if in_london:
        return "london"
    if in_ny:
        return "ny"
    if in_asia:
        return "asia"
    return "off_hours"


class GateNews(BaseGate):
    gate_name = "gate_NEWS"
    priority = 0

    def __init__(self) -> None:
        self._calendar: list[dict[str, Any]] = []
        self._last_load: float = 0.0

    def _refresh_calendar(self) -> None:
        now = time.time()
        if now - self._last_load > 300.0:
            self._calendar = _load_calendar()
            self._last_load = now

    def evaluate(self, tick: dict[str, Any]) -> bool:
        self._refresh_calendar()
        if not self._calendar:
            return True
        now_ms = int(time.time() * 1000)
        for event in self._calendar:
            event_name = str(event.get("name", ""))
            event_time_ms = int(event.get("timestamp_ms", 0))
            if event_time_ms <= 0:
                continue
            is_high_impact = (
                event.get("impact", "").lower() == "high"
                or event_name in HIGH_IMPACT_EVENTS
            )
            if not is_high_impact:
                continue
            before_ms = NEWS_BLOCK_MINUTES_BEFORE * 60 * 1000
            after_ms = NEWS_BLOCK_MINUTES_AFTER * 60 * 1000
            if (event_time_ms - before_ms) <= now_ms <= (event_time_ms + after_ms):
                LOGGER.debug("News gate BLOCKED: %s at %s", event_name, event.get("datetime", ""))
                return False
        return True


class GateDXY(BaseGate):
    gate_name = "gate_DXY"
    priority = 8

    def evaluate(self, tick: dict[str, Any]) -> bool:
        dxy_trend = tick.get("dxy_trend", "neutral")
        direction = tick.get("direction", "BUY")
        if dxy_trend == "strong_up" and direction == "BUY":
            return False
        if dxy_trend == "strong_down" and direction == "SELL":
            return False
        return True


class GateVolume(BaseGate):
    gate_name = "gate_VOL"
    priority = 7

    def evaluate(self, tick: dict[str, Any]) -> bool:
        vol_ratio = float(tick.get("volume_ratio", 0.0))
        threshold = float(os.getenv("MIN_VOLUME_RATIO", "1.2"))
        return vol_ratio >= threshold


class GateSession(BaseGate):
    gate_name = "gate_SESSION"
    priority = 1

    def evaluate(self, tick: dict[str, Any]) -> bool:
        # We now allow all sessions and let the ML model/dynamic selector learn which are profitable
        return True


class GateMacroRegime(BaseGate):
    gate_name = "gate_REGIME"
    priority = 2

    def __init__(self) -> None:
        self._atr_buffer: deque[float] = deque(maxlen=REGIME_WINDOW)
        self._mid_buffer: deque[float] = deque(maxlen=REGIME_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        if bid <= 0 or ask <= 0:
            return False
        mid = (bid + ask) / 2.0
        spread = ask - bid
        self._mid_buffer.append(mid)
        self._atr_buffer.append(spread)
        if len(self._mid_buffer) < REGIME_WINDOW:
            return True
        mids = list(self._mid_buffer)
        price_range = max(mids) - min(mids)
        avg_atr = sum(self._atr_buffer) / len(self._atr_buffer) if self._atr_buffer else 0.0
        if avg_atr <= 0:
            return True
        range_to_atr = price_range / (avg_atr * REGIME_WINDOW)
        if range_to_atr > REGIME_TRENDING_ATR_MULT:
            regime = "trending"
        elif range_to_atr < 0.5:
            regime = "quiet"
        else:
            regime = "ranging"
        # We now allow all regimes and let the ML model/dynamic selector learn
        return True
