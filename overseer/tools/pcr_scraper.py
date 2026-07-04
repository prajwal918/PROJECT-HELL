"""Put/Call Ratio Scraper for OVERSEER.

Fetches PCR (Put/Call Ratio) from:
- CBOE equity PCR
- FRED CBOE PCR series (PCRE)

Cache: 1 hour TTL.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from tools.scraper_utils import ScraperHealth

LOGGER = logging.getLogger("overseer.pcr_scraper")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = _PROJECT_ROOT / "database" / "overseer_trades.db"

_ENABLED = os.getenv("PCR_SCRAPER_ENABLED", "true").lower() == "true"
_CACHE_TTL = float(os.getenv("PCR_CACHE_TTL", "3600"))
_FEAR_THRESHOLD = float(os.getenv("PCR_FEAR_THRESHOLD", "1.2"))
_GREED_THRESHOLD = float(os.getenv("PCR_GREED_THRESHOLD", "0.7"))
_DIRECTION_BONUS = float(os.getenv("PCR_DIRECTION_BONUS", "0.05"))
_FRED_API_KEY = os.getenv("FRED_API_KEY", "")

health = ScraperHealth("pcr")

try:
    import requests
except ImportError:
    requests = None

try:
    from fredapi import Fred
except ImportError:
    Fred = None

_FRED_PCR_SERIES = "PCRE"

def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pcr_data (
            source TEXT PRIMARY KEY,
            pcr_value REAL,
            date TEXT,
            scraped_at TEXT NOT NULL
        )
    """)
    conn.commit()

def _fetch_cboe_pcr() -> Optional[Dict[str, Any]]:
    if requests is None:
        return None
    try:
        url = "https://cdn.cboe.com/api/us/options/market_statistics/daily/pcr/eq"
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, timeout=10, headers=headers)
        if resp.status_code != 200:
            return None
        data = resp.json()
        pcr = float(data.get("current", data.get("pcr", 0)))
        date_str = data.get("date", data.get("trade_date", ""))
        return {"source": "cboe", "pcr_value": pcr, "date": date_str}
    except Exception:
        return None

def _fetch_fred_pcr() -> Optional[Dict[str, Any]]:
    if Fred is None or not _FRED_API_KEY:
        return None
    try:
        fred = Fred(api_key=_FRED_API_KEY)
        series = fred.get_series(_FRED_PCR_SERIES)
        if series is None or series.empty:
            return None
        latest_date = str(series.index[-1].date())
        latest_value = float(series.iloc[-1])
        return {"source": "fred", "pcr_value": latest_value, "date": latest_date}
    except Exception:
        return None

class PCRScraper:
    def __init__(self) -> None:
        self._cached_pcr: Optional[float] = None
        self._cache_time: float = 0.0

    def get_pcr(self, symbol: str = "") -> float:
        if not _ENABLED:
            return 1.0
        now = time.time()
        if self._cached_pcr is not None and (now - self._cache_time) < _CACHE_TTL:
            return self._cached_pcr

        result = _fetch_cboe_pcr()
        if result is None:
            result = _fetch_fred_pcr()
        
        if result is None:
            health.record_failure()
            return self._cached_pcr if self._cached_pcr is not None else 1.0

        pcr = result["pcr_value"]
        self._cached_pcr = pcr
        self._cache_time = now
        health.record_success()
        return pcr

    def get_direction_bonus(self, symbol: str, direction: str) -> float:
        if not _ENABLED:
            return 0.0
        pcr = self.get_pcr(symbol)
        if pcr > _FEAR_THRESHOLD:
            return _DIRECTION_BONUS if direction == "SELL" else -_DIRECTION_BONUS * 0.5
        elif pcr < _GREED_THRESHOLD:
            return _DIRECTION_BONUS if direction == "BUY" else -_DIRECTION_BONUS * 0.5
        return 0.0

pcr_scraper = PCRScraper()
