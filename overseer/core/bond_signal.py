"""Bond Market Leading FX Signal for OVERSEER v13.

Bond yields lead FX moves by 5-15 minutes. When US 2Y yield is
rising fast, USD strength is incoming. When Bund yield is rising
fast, EUR strength is incoming.

Tracks yield velocity: (current_yield - yield_10min_ago) / 10
in basis points per minute.

If bond signal matches trade direction → +0.07 bonus.

Uses FRED scraper data for US yields and ECB scraper for Bund yields.
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from typing import Dict, Optional

LOGGER = logging.getLogger("overseer.bond_signal")

_ENABLED = os.getenv("BOND_SIGNAL_ENABLED", "true").lower() == "true"
_BOND_BONUS = float(os.getenv("BOND_BONUS", "0.07"))
_VELOCITY_WINDOW = int(os.getenv("BOND_VELOCITY_WINDOW", "600"))
_VELOCITY_THRESHOLD = float(os.getenv("BOND_VELOCITY_THRESHOLD", "0.5"))
_MAX_HISTORY = int(os.getenv("BOND_MAX_HISTORY", "3600"))

_CURRENCY_BOND_MAP = {
    "USD": {"us_2y_yield": 1.0, "us_10y_yield": 0.5},
    "EUR": {"ecb_deposit_rate": 1.0},
    "GBP": {"boe_rate": 1.0},
    "JPY": {"boj_rate": 1.0},
    "AUD": {"rba_rate": 1.0},
    "CAD": {"boc_rate": 1.0},
    "NZD": {"rbnz_rate": 1.0},
    "CHF": {"snb_rate": 1.0},
}

_SYMBOL_CURRENCIES = {
    "6EM6": ("EUR", "USD"),
    "6BM6": ("GBP", "USD"),
    "6JM6": ("USD", "JPY"),
    "6AM6": ("AUD", "USD"),
    "6CM6": ("USD", "CAD"),
    "6NM6": ("NZD", "USD"),
    "6SM6": ("USD", "CHF"),
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "USDJPY": ("USD", "JPY"),
    "AUDUSD": ("AUD", "USD"),
    "USDCAD": ("USD", "CAD"),
    "NZDUSD": ("NZD", "USD"),
    "USDCHF": ("USD", "CHF"),
}


class BondSignal:
    """Track bond yield velocity and compute FX direction bonus."""

    def __init__(self) -> None:
        self._yield_history: Dict[str, deque] = {}
        self._yield_velocity: Dict[str, float] = {}
        self._last_fetch_time: float = 0.0
        self._FETCH_INTERVAL = 300.0

    def _init_series(self, series_name: str) -> None:
        if series_name not in self._yield_history:
            self._yield_history[series_name] = deque(maxlen=_MAX_HISTORY)

    def update_yield(self, series_name: str, yield_value: float) -> None:
        if not _ENABLED:
            return
        self._init_series(series_name)
        self._yield_history[series_name].append((time.time(), yield_value))
        self._compute_velocity(series_name)

    def _compute_velocity(self, series_name: str) -> float:
        history = self._yield_history.get(series_name)
        if history is None or len(history) < 2:
            return 0.0

        now = time.time()
        cutoff = now - _VELOCITY_WINDOW

        current_val = None
        past_val = None
        for ts, val in reversed(history):
            if current_val is None:
                current_val = val
            if ts <= cutoff:
                past_val = val
                break

        if current_val is None or past_val is None:
            return 0.0

        elapsed_min = _VELOCITY_WINDOW / 60.0
        if elapsed_min == 0:
            return 0.0
        velocity = (current_val - past_val) / elapsed_min
        self._yield_velocity[series_name] = velocity
        return velocity

    def _fetch_fred_yields(self) -> None:
        now = time.time()
        if (now - self._last_fetch_time) < self._FETCH_INTERVAL:
            return
        self._last_fetch_time = now

        try:
            from tools.fred_scraper import get_fred_data
            fred = get_fred_data()
            for series_key in ("us_2y_yield", "us_10y_yield", "us_30y_yield"):
                entry = fred.get(series_key, {})
                val = entry.get("value")
                if val is not None:
                    self.update_yield(series_key, float(val))
        except Exception as exc:
            LOGGER.debug("FRED yield fetch failed: %s", exc)

        try:
            from tools.ecb_scraper import get_ecb_data
            ecb = get_ecb_data()
            for series_key in ("ecb_ref_rate", "ecb_deposit_rate", "eur_3m_euribor"):
                entry = ecb.get(series_key, {})
                val = entry.get("value")
                if val is not None:
                    self.update_yield(series_key, float(val))
        except Exception as exc:
            LOGGER.debug("ECB yield fetch failed: %s", exc)

    def _get_currency_velocity(self, currency: str) -> float:
        series_weights = _CURRENCY_BOND_MAP.get(currency, {})
        if not series_weights:
            return 0.0

        total_velocity = 0.0
        total_weight = 0.0
        for series_name, weight in series_weights.items():
            vel = self._yield_velocity.get(series_name, 0.0)
            total_velocity += vel * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0
        return total_velocity / total_weight

    def _get_symbol_currencies(self, symbol: str) -> Optional[tuple]:
        if symbol in _SYMBOL_CURRENCIES:
            return _SYMBOL_CURRENCIES[symbol]
        for key in _SYMBOL_CURRENCIES:
            if symbol.startswith(key[:2]):
                return _SYMBOL_CURRENCIES[key]
        return None

    def get_bond_bonus(self, symbol: str, direction: str) -> float:
        if not _ENABLED:
            return 0.0

        self._fetch_fred_yields()

        currencies = self._get_symbol_currencies(symbol)
        if currencies is None:
            return 0.0

        base_currency, quote_currency = currencies
        base_vel = self._get_currency_velocity(base_currency)
        quote_vel = self._get_currency_velocity(quote_currency)

        relative_velocity = base_vel - quote_vel

        if abs(relative_velocity) < _VELOCITY_THRESHOLD:
            return 0.0

        if direction == "BUY":
            if relative_velocity > 0:
                return _BOND_BONUS
            elif relative_velocity < -_VELOCITY_THRESHOLD:
                return -_BOND_BONUS * 0.5
        elif direction == "SELL":
            if relative_velocity < 0:
                return _BOND_BONUS
            elif relative_velocity > _VELOCITY_THRESHOLD:
                return -_BOND_BONUS * 0.5

        return 0.0


bond_signal = BondSignal()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bond_signal._fetch_fred_yields()
    for sym in ("6EM6", "6BM6", "6JM6", "6AM6", "6CM6"):
        for d in ("BUY", "SELL"):
            b = bond_signal.get_bond_bonus(sym, d)
            print(f"  {sym} {d}: bond_bonus={b:+.4f}")
