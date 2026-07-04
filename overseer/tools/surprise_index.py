"""Economic Surprise Index for OVERSEER v13.

Builds a rolling 3-month per-currency surprise index from economic
releases. Surprise = (actual - forecast) / historical_std.

Positive surprise index → currency appreciation bias.
Negative surprise index → currency depreciation bias.

Data sourced from calendar_scraper releases and manual updates.
"""

from __future__ import annotations

import logging
import math
import os
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

LOGGER = logging.getLogger("overseer.surprise_index")

_ENABLED = os.getenv("SURPRISE_INDEX_ENABLED", "true").lower() == "true"
_SURPRISE_WINDOW = int(os.getenv("SURPRISE_WINDOW_DAYS", "90"))
_DEFAULT_STD = float(os.getenv("SURPRISE_DEFAULT_STD", "0.5"))
_BIAS_SCALE = float(os.getenv("SURPRISE_BIAS_SCALE", "0.10"))

_CURRENCY_MAP = {
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

_COUNTRY_CURRENCY = {
    "US": "USD",
    "EU": "EUR",
    "DE": "EUR",
    "FR": "EUR",
    "GB": "GBP",
    "UK": "GBP",
    "JP": "JPY",
    "AU": "AUD",
    "CA": "CAD",
    "NZ": "NZD",
    "CH": "CHF",
}


class SurpriseIndex:
    """Rolling per-currency economic surprise index."""

    def __init__(self) -> None:
        self._releases: Dict[str, deque] = {}
        self._index_cache: Dict[str, float] = {}
        self._index_cache_time: float = 0.0
        self._CACHE_TTL = 300.0

    def _init_currency(self, currency: str) -> None:
        if currency not in self._releases:
            self._releases[currency] = deque(maxlen=500)

    def add_release(
        self,
        currency: str,
        actual: float,
        forecast: float,
        std: float = 0.0,
    ) -> None:
        if not _ENABLED:
            return
        self._init_currency(currency)

        if std <= 0:
            std = _DEFAULT_STD

        surprise = (actual - forecast) / std
        self._releases[currency].append((time.time(), surprise))
        self._index_cache.pop(currency, None)

        LOGGER.debug(
            "Surprise %s: actual=%.2f forecast=%.2f std=%.2f z=%.2f",
            currency, actual, forecast, std, surprise,
        )

    def add_release_country(
        self,
        country: str,
        actual: float,
        forecast: float,
        std: float = 0.0,
    ) -> None:
        currency = _COUNTRY_CURRENCY.get(country.upper())
        if currency is None:
            LOGGER.debug("Unknown country code: %s", country)
            return
        self.add_release(currency, actual, forecast, std)

    def _compute_index(self, currency: str) -> float:
        releases = self._releases.get(currency)
        if not releases:
            return 0.0

        now = time.time()
        cutoff = now - (_SURPRISE_WINDOW * 86400)

        recent = [s for ts, s in releases if ts >= cutoff]
        if not recent:
            return 0.0

        return sum(recent) / len(recent)

    def get_index(self, currency: str) -> float:
        if not _ENABLED:
            return 0.0

        now = time.time()
        cached = self._index_cache.get(currency)
        if cached is not None and (now - self._index_cache_time) < self._CACHE_TTL:
            return cached

        idx = self._compute_index(currency)
        self._index_cache[currency] = idx
        self._index_cache_time = now
        return idx

    def _get_symbol_currencies(self, symbol: str) -> Optional[Tuple[str, str]]:
        if symbol in _CURRENCY_MAP:
            return _CURRENCY_MAP[symbol]
        for key in _CURRENCY_MAP:
            if symbol.startswith(key[:2]):
                return _CURRENCY_MAP[key]
        return None

    def get_bias(self, symbol: str) -> float:
        if not _ENABLED:
            return 0.0

        currencies = self._get_symbol_currencies(symbol)
        if currencies is None:
            return 0.0

        base_currency, quote_currency = currencies
        base_idx = self.get_index(base_currency)
        quote_idx = self.get_index(quote_currency)

        relative = base_idx - quote_idx

        bias = max(-1.0, min(1.0, relative * _BIAS_SCALE))
        return bias

    def load_from_calendar_scraper(self) -> int:
        count = 0
        try:
            from tools.calendar_scraper import scrape_calendar
            events = scrape_calendar()
            if not isinstance(events, list):
                return 0
            for event in events:
                country = event.get("country", "")
                actual = event.get("actual")
                forecast = event.get("forecast")
                if actual is None or forecast is None:
                    continue
                try:
                    actual_f = float(str(actual).replace("%", "").replace("K", "").strip())
                    forecast_f = float(str(forecast).replace("%", "").replace("K", "").strip())
                except (ValueError, TypeError):
                    continue
                self.add_release_country(country, actual_f, forecast_f)
                count += 1
        except Exception as exc:
            LOGGER.warning("Calendar scraper load failed: %s", exc)

        if count > 0:
            LOGGER.info("Loaded %d releases into surprise index", count)
        return count


surprise_index = SurpriseIndex()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    surprise_index.add_release("USD", 0.4, 0.3, 0.15)
    surprise_index.add_release("EUR", -0.1, 0.2, 0.2)
    surprise_index.add_release("GBP", 0.5, 0.3, 0.25)
    for c in ("USD", "EUR", "GBP", "JPY", "AUD", "CAD"):
        idx = surprise_index.get_index(c)
        print(f"  {c}: surprise_index={idx:+.3f}")
    for sym in ("6EM6", "6BM6", "6JM6"):
        bias = surprise_index.get_bias(sym)
        print(f"  {sym}: bias={bias:+.4f}")
