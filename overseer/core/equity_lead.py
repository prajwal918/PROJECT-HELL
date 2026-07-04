"""Equity Futures as FX Lead for OVERSEER v13.

S&P futures (ES) movements lead FX by 3-8 minutes:
- ES drop → risk-off → 6J BUY, 6A SELL, 6N SELL
- ES rip up → risk-on → 6A BUY, 6N BUY, 6J SELL

Uses Finnhub S&P 500 data or free index APIs.

If equity signal matches pair+direction → +0.08 bonus.
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from typing import Dict, Optional

LOGGER = logging.getLogger("overseer.equity_lead")

_ENABLED = os.getenv("EQUITY_LEAD_ENABLED", "true").lower() == "true"
_EQUITY_BONUS = float(os.getenv("EQUITY_BONUS", "0.08"))
_LOOKBACK_TICKS = int(os.getenv("EQUITY_LOOKBACK_TICKS", "20"))
_THRESHOLD_PCT = float(os.getenv("EQUITY_THRESHOLD_PCT", "0.3"))
_MAX_HISTORY = int(os.getenv("EQUITY_MAX_HISTORY", "500"))
_FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

_RISK_OFF_PAIRS = {
    "6JM6": {"BUY": True, "SELL": False},
    "6AM6": {"BUY": False, "SELL": True},
    "6NM6": {"BUY": False, "SELL": True},
    "6SM6": {"BUY": False, "SELL": True},
    "6EM6": {"BUY": False, "SELL": True},
    "6BM6": {"BUY": False, "SELL": True},
}

_RISK_ON_PAIRS = {
    "6JM6": {"BUY": False, "SELL": True},
    "6AM6": {"BUY": True, "SELL": False},
    "6NM6": {"BUY": True, "SELL": False},
    "6SM6": {"BUY": True, "SELL": False},
    "6EM6": {"BUY": True, "SELL": False},
    "6BM6": {"BUY": True, "SELL": False},
}

try:
    import requests
except ImportError:
    requests = None


class EquityLead:
    """Track equity futures moves and compute FX direction bonus."""

    def __init__(self) -> None:
        self._spx_history: deque = deque(maxlen=_MAX_HISTORY)
        self._current_regime: str = "neutral"
        self._last_change_pct: float = 0.0
        self._last_fetch_time: float = 0.0
        self._FETCH_INTERVAL = 60.0

    def update_equity(self, spx_change_pct: float) -> None:
        if not _ENABLED:
            return
        self._spx_history.append((time.time(), spx_change_pct))
        self._last_change_pct = spx_change_pct
        self._update_regime()

    def _update_regime(self) -> None:
        if len(self._spx_history) < 2:
            self._current_regime = "neutral"
            return

        recent = list(self._spx_history)[-_LOOKBACK_TICKS:]
        if not recent:
            self._current_regime = "neutral"
            return

        avg_change = sum(change for _, change in recent) / len(recent)

        if avg_change < -_THRESHOLD_PCT:
            self._current_regime = "risk_off"
        elif avg_change > _THRESHOLD_PCT:
            self._current_regime = "risk_on"
        else:
            self._current_regime = "neutral"

    def _fetch_finnhub_equity(self) -> None:
        if requests is None or not _FINNHUB_API_KEY:
            return
        now = time.time()
        if (now - self._last_fetch_time) < self._FETCH_INTERVAL:
            return
        self._last_fetch_time = now

        try:
            url = "https://finnhub.io/api/v1/quote"
            params = {"symbol": "SPY", "token": _FINNHUB_API_KEY}
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                LOGGER.warning("Finnhub equity quote returned %d", resp.status_code)
                return
            data = resp.json()
            prev_close = float(data.get("pc", 0))
            current = float(data.get("c", 0))
            if prev_close > 0:
                change_pct = ((current - prev_close) / prev_close) * 100.0
                self.update_equity(change_pct)
                LOGGER.debug(
                    "Equity: SPY=%.2f prev=%.2f change=%.2f%%",
                    current, prev_close, change_pct,
                )
        except Exception as exc:
            LOGGER.warning("Finnhub equity fetch failed: %s", exc)

    def get_fx_bonus(self, symbol: str, direction: str) -> float:
        if not _ENABLED:
            return 0.0

        self._fetch_finnhub_equity()

        if self._current_regime == "risk_off":
            mapping = _RISK_OFF_PAIRS.get(symbol)
            if mapping and mapping.get(direction):
                return _EQUITY_BONUS
        elif self._current_regime == "risk_on":
            mapping = _RISK_ON_PAIRS.get(symbol)
            if mapping and mapping.get(direction):
                return _EQUITY_BONUS

        if self._current_regime == "risk_off":
            mapping = _RISK_OFF_PAIRS.get(symbol)
            if mapping and not mapping.get(direction):
                return -_EQUITY_BONUS * 0.5
        elif self._current_regime == "risk_on":
            mapping = _RISK_ON_PAIRS.get(symbol)
            if mapping and not mapping.get(direction):
                return -_EQUITY_BONUS * 0.5

        return 0.0

    @property
    def regime(self) -> str:
        return self._current_regime

    @property
    def last_change_pct(self) -> float:
        return self._last_change_pct


equity_lead = EquityLead()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    equity_lead._fetch_finnhub_equity()
    print(f"  Equity regime: {equity_lead.regime}")
    print(f"  SPY change: {equity_lead.last_change_pct:.2f}%")
    for sym in ("6JM6", "6AM6", "6NM6", "6EM6"):
        for d in ("BUY", "SELL"):
            b = equity_lead.get_fx_bonus(sym, d)
            print(f"  {sym} {d}: bonus={b:+.4f}")
