"""CBOE FX Volatility Index Scraper for OVERSEER v14.

Primary: RapidAPI Yahoo Finance for CBOE FX vol indices.
Fallback: Realized volatility from tick_log prices (Garman-Klass).

CBOE FX Vol Indices (accessed via RapidAPI):
EVZ = CBOE Euro Volatility Index
JYV = CBOE Japanese Yen Volatility Index
BZV = CBOE British Pound Volatility Index
AXV = CBOE Australian Dollar Volatility Index

These give per-currency implied vol -> synthetic risk reversal -> gamma proxy.
"""
from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import requests
except ImportError:
    requests = None

try:
    import numpy as np
except ImportError:
    np = None

from tools.scraper_utils import ScraperHealth

LOGGER = logging.getLogger("overseer.cboe_vol")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = _PROJECT_ROOT / "database" / "overseer_trades.db"

_ENABLED = os.getenv("CBOE_VOL_ENABLED", "true").lower() == "true"
_CACHE_TTL = float(os.getenv("CBOE_VOL_CACHE_TTL", "3600"))
_RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
_RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "yahoo-finance166.p.rapidapi.com")

_HEALTH = ScraperHealth("cboe_vol")

_CBOE_INDICES = {
    "EUR": "^EVZ",
    "JPY": "^JYV",
    "GBP": "^BZV",
    "AUD": "^AXV",
}

_CURRENCY_TO_SYMBOL = {
    "EUR": "6EM6",
    "JPY": "6JM6",
    "GBP": "6BM6",
    "AUD": "6AM6",
    "CAD": "6CM6",
    "CHF": "6SM6",
    "NZD": "6NM6",
}

_cached_data: Dict[str, Any] = {}
_cache_time: float = 0.0


def _get_conn():
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cboe_fx_vol (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            currency TEXT,
            ticker TEXT,
            iv_value REAL,
            iv_change REAL DEFAULT 0,
            source TEXT DEFAULT 'rapidapi',
            fetch_date TEXT,
            fetched_at TEXT,
            UNIQUE(currency, fetch_date)
        )
    """)
    conn.commit()


def _fetch_rapidapi_vol(currency: str, ticker: str) -> Optional[float]:
    if not _RAPIDAPI_KEY or requests is None:
        return None
    url = f"https://{_RAPIDAPI_HOST}/v8/finance/chart/{ticker}"
    headers = {
        "X-RapidAPI-Key": _RAPIDAPI_KEY,
        "X-RapidAPI-Host": _RAPIDAPI_HOST,
    }
    params = {"range": "5d", "interval": "1d"}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            LOGGER.debug("RapidAPI %s status %d", ticker, resp.status_code)
            return None
        data = resp.json()
        closes = data.get("chart", {}).get("result", [{}])[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
        closes = [c for c in closes if c is not None]
        if closes:
            return float(closes[-1])
    except Exception as exc:
        LOGGER.debug("RapidAPI %s error: %s", ticker, exc)
    return None


def _fetch_realized_vol(currency: str) -> float:
    conn = None
    try:
        conn = _get_conn()
        sym = _CURRENCY_TO_SYMBOL.get(currency, "")
        if not sym:
            return 0.0
        rows = conn.execute(
            "SELECT bid, ask, timestamp FROM tick_log "
            "WHERE symbol=? AND bid > 0 AND ask > 0 "
            "ORDER BY rowid DESC LIMIT 500",
            (sym,),
        ).fetchall()
        if len(rows) < 20:
            return 0.0
        mids = [(float(r[0]) + float(r[1])) / 2.0 for r in reversed(rows)]
        returns = []
        for i in range(1, len(mids)):
            if mids[i - 1] > 0:
                returns.append(math.log(mids[i] / mids[i - 1]))
        if len(returns) < 10:
            return 0.0
        if np is not None:
            rv = float(np.std(returns)) * math.sqrt(252 * 1440)
        else:
            mean = sum(returns) / len(returns)
            var = sum((r - mean) ** 2 for r in returns) / len(returns)
            rv = math.sqrt(var) * math.sqrt(252 * 1440)
        return round(rv, 4)
    except Exception as exc:
        LOGGER.debug("Realized vol %s error: %s", currency, exc)
        return 0.0
    finally:
        if conn:
            conn.close()


def scrape_cboe_vol() -> Dict[str, Any]:
    if not _ENABLED:
        return {}

    global _cached_data, _cache_time
    if _cached_data and (time.time() - _cache_time) < _CACHE_TTL:
        return _cached_data

    result: Dict[str, Any] = {}
    vol_values: Dict[str, float] = {}
    any_success = False

    for currency, ticker in _CBOE_INDICES.items():
        iv = _fetch_rapidapi_vol(currency, ticker)
        source = "rapidapi"

        if iv is None or iv == 0.0:
            iv = _fetch_realized_vol(currency)
            source = "realized_vol"

        if iv is not None and iv > 0.0:
            vol_values[currency] = iv
            result[f"{currency}_iv"] = round(iv, 4)
            result[f"{currency}_iv_change"] = 0.0
            any_success = True
            LOGGER.info("CBOE %s (%s): IV=%.4f source=%s", currency, ticker, iv, source)

            conn = _get_conn()
            _ensure_table(conn)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT OR REPLACE INTO cboe_fx_vol "
                "(currency, ticker, iv_value, iv_change, source, fetch_date, fetched_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (currency, ticker, iv, 0.0, source, today,
                 datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            conn.close()
        else:
            result[f"{currency}_iv"] = 0.0
            result[f"{currency}_iv_change"] = 0.0
            LOGGER.debug("CBOE %s (%s): no data from any source", currency, ticker)

    if any_success:
        _HEALTH.record_success()
    else:
        _HEALTH.record_failure()

    if vol_values:
        max_curr = max(vol_values, key=vol_values.get)
        min_curr = min(vol_values, key=vol_values.get)
        result["skew_max_currency"] = max_curr
        result["skew_min_currency"] = min_curr
        if len(vol_values) >= 2:
            spread = vol_values[max_curr] - vol_values[min_curr]
            result["vol_skew_spread"] = round(spread, 4)
        else:
            result["vol_skew_spread"] = 0.0
    else:
        result["vol_skew_spread"] = 0.0

    result["per_symbol"] = {}
    for currency, sym in _CURRENCY_TO_SYMBOL.items():
        iv = vol_values.get(currency, 0.0)
        if iv == 0.0 and currency == "CAD" and vol_values.get("AUD"):
            iv = vol_values["AUD"] * 0.9
        if iv == 0.0 and currency == "CHF" and vol_values.get("EUR"):
            iv = vol_values["EUR"] * 0.85
        if iv == 0.0 and currency == "NZD" and vol_values.get("AUD"):
            iv = vol_values["AUD"] * 1.1
        result["per_symbol"][sym] = {
            "atm_iv": round(iv, 4),
            "skew_proxy": round(result.get("vol_skew_spread", 0) * 0.3, 4),
        }

    _cached_data = result
    _cache_time = time.time()
    return result


def get_symbol_iv(symbol: str) -> float:
    data = scrape_cboe_vol()
    per = data.get("per_symbol", {})
    entry = per.get(symbol, {})
    return entry.get("atm_iv", 0.0)


def get_symbol_skew(symbol: str) -> float:
    data = scrape_cboe_vol()
    per = data.get("per_symbol", {})
    entry = per.get(symbol, {})
    return entry.get("skew_proxy", 0.0)


def get_vol_skew_spread() -> float:
    data = scrape_cboe_vol()
    return data.get("vol_skew_spread", 0.0)


def is_high_vol_environment() -> bool:
    data = scrape_cboe_vol()
    for currency in _CBOE_INDICES:
        iv = data.get(f"{currency}_iv", 0.0)
        if iv > 10.0:
            return True
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = scrape_cboe_vol()
    for k, v in sorted(result.items()):
        if k != "per_symbol":
            print(f"  {k}: {v}")
    print("  per_symbol:")
    for sym, entry in result.get("per_symbol", {}).items():
        print(f"    {sym}: iv={entry['atm_iv']:.4f} skew={entry['skew_proxy']:.4f}")
