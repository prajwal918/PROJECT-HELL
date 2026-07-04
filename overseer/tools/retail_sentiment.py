"""Retail Sentiment Fade for OVERSEER v13.

Scrapes OANDA open position ratios (position book) to measure retail
crowding. When retail is overwhelmingly long, SELL gets a bonus (fade
the crowd); when retail is overwhelmingly short, BUY gets a bonus.

Free endpoint:
  https://api-fxpractice.oanda.com/v3/instruments/{instrument}/positionBook

Requires OANDA_API_KEY from env.

Cache: 15 minutes TTL (retail positioning changes slowly).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

LOGGER = logging.getLogger("overseer.retail_sentiment")

_ENABLED = os.getenv("RETAIL_SENTIMENT_ENABLED", "true").lower() == "true"
_API_KEY = os.getenv("OANDA_API_KEY", "")
_BASE_URL = os.getenv(
    "OANDA_BASE_URL", "https://api-fxpractice.oanda.com"
)
_CACHE_TTL = float(os.getenv("RETAIL_SENTIMENT_CACHE_TTL", "900"))
_CROWD_THRESHOLD = float(os.getenv("RETAIL_CROWD_THRESHOLD", "0.80"))
_FADE_BONUS = float(os.getenv("RETAIL_FADE_BONUS", "0.06"))
_FADE_PENALTY = float(os.getenv("RETAIL_FADE_PENALTY", "0.04"))

_CME_TO_OANDA = {
    "6EM6": "EUR_USD",
    "6BM6": "GBP_USD",
    "6JM6": "USD_JPY",
    "6AM6": "AUD_USD",
    "6CM6": "USD_CAD",
    "6NM6": "NZD_USD",
    "6SM6": "USD_CHF",
}

try:
    import requests
except ImportError:
    requests = None


class RetailSentiment:
    """Fetch and cache OANDA retail position ratios for crowd-fade signals."""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_times: Dict[str, float] = {}
        self._consecutive_failures: int = 0

    def _resolve_instrument(self, symbol: str) -> Optional[str]:
        if symbol in _CME_TO_OANDA:
            return _CME_TO_OANDA[symbol]
        if "_" in symbol:
            return symbol
        return None

    def _fetch_position_book(self, instrument: str) -> Optional[Dict[str, Any]]:
        if requests is None or not _API_KEY:
            return None
        url = f"{_BASE_URL}/v3/instruments/{instrument}/positionBook"
        headers = {
            "Authorization": f"Bearer {_API_KEY}",
            "Accept": "application/json",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                LOGGER.warning(
                    "OANDA positionBook %s returned %d",
                    instrument,
                    resp.status_code,
                )
                return None
            data = resp.json()
            book = data.get("positionBook", {})
            return book
        except Exception as exc:
            LOGGER.warning("OANDA positionBook fetch %s failed: %s", instrument, exc)
            return None

    def _parse_long_pct(self, book: Dict[str, Any]) -> float:
        buckets = book.get("buckets", [])
        if not buckets:
            return 0.5
        long_vol = 0.0
        short_vol = 0.0
        for b in buckets:
            long_count = float(b.get("longCountPercent", 0))
            short_count = float(b.get("shortCountPercent", 0))
            long_vol += long_count
            short_vol += short_count
        total = long_vol + short_vol
        if total == 0:
            return 0.5
        return long_vol / total

    def get_sentiment(self, symbol: str) -> Dict[str, Any]:
        if not _ENABLED:
            return {"long_pct": 0.5, "short_pct": 0.5, "source": "disabled"}

        instrument = self._resolve_instrument(symbol)
        if instrument is None:
            return {"long_pct": 0.5, "short_pct": 0.5, "source": "unknown_symbol"}

        now = time.time()
        cached = self._cache.get(instrument)
        cached_time = self._cache_times.get(instrument, 0.0)
        if cached is not None and (now - cached_time) < _CACHE_TTL:
            return cached

        book = self._fetch_position_book(instrument)
        if book is None:
            if cached is not None:
                LOGGER.debug("Using stale cache for %s", instrument)
                return cached
            self._consecutive_failures += 1
            return {"long_pct": 0.5, "short_pct": 0.5, "source": "unavailable"}

        long_pct = self._parse_long_pct(book)
        short_pct = 1.0 - long_pct
        result = {
            "long_pct": long_pct,
            "short_pct": short_pct,
            "instrument": instrument,
            "source": "oanda_position_book",
            "timestamp": now,
        }
        self._cache[instrument] = result
        self._cache_times[instrument] = now
        self._consecutive_failures = 0

        LOGGER.info(
            "Retail sentiment %s: long=%.1f%% short=%.1f%%",
            instrument,
            long_pct * 100,
            short_pct * 100,
        )
        return result

    def get_fade_bonus(self, symbol: str, direction: str) -> float:
        if not _ENABLED:
            return 0.0

        sentiment = self.get_sentiment(symbol)
        long_pct = sentiment.get("long_pct", 0.5)
        short_pct = sentiment.get("short_pct", 0.5)

        if direction == "BUY":
            if short_pct >= _CROWD_THRESHOLD:
                return _FADE_BONUS
            if long_pct >= _CROWD_THRESHOLD:
                return -_FADE_PENALTY
        elif direction == "SELL":
            if long_pct >= _CROWD_THRESHOLD:
                return _FADE_BONUS
            if short_pct >= _CROWD_THRESHOLD:
                return -_FADE_PENALTY

        return 0.0


retail_sentiment = RetailSentiment()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for sym in ("6EM6", "6BM6", "6JM6"):
        s = retail_sentiment.get_sentiment(sym)
        print(f"  {sym}: long={s['long_pct']:.1%} short={s['short_pct']:.1%}")
        for d in ("BUY", "SELL"):
            b = retail_sentiment.get_fade_bonus(sym, d)
            print(f"    {d}: fade_bonus={b:+.4f}")
