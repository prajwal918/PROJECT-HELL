"""FXSSI Web Scraper for OVERSEER v14.

Scrapes live retail sentiment data from FXSSI.com tools page.
Extracts per-pair buy/sell ratios aggregated from 10+ brokers
(OANDA, Dukascopy, IG, FiboGroup, Instaforex, MyFxBook, FXBlue, etc.).

This gives real multi-broker retail positioning for gate_RETAIL_SENTIMENT.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import requests
except ImportError:
    requests = None

from tools.scraper_utils import ScraperHealth

LOGGER = logging.getLogger("overseer.fxssi_web")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = _PROJECT_ROOT / "database" / "overseer_trades.db"

_ENABLED = os.getenv("FXSSI_WEB_ENABLED", "true").lower() == "true"
_CACHE_TTL = float(os.getenv("FXSSI_WEB_CACHE_TTL", "900"))
_CROWD_THRESHOLD = float(os.getenv("FXSSI_CROWD_THRESHOLD", "0.65"))
_FADE_BONUS = float(os.getenv("FXSSI_FADE_BONUS", "0.06"))

_HEALTH = ScraperHealth("fxssi_web")

_PAIR_MAP = {
    "AUD/JPY": "AUDJPY",
    "AUD/USD": "AUDUSD",
    "EUR/AUD": "EURAUD",
    "EUR/GBP": "EURGBP",
    "EUR/JPY": "EURJPY",
    "EUR/USD": "EURUSD",
    "GBP/JPY": "GBPJPY",
    "GBP/USD": "GBPUSD",
    "NZD/USD": "NZDUSD",
    "USD/CAD": "USDCAD",
    "USD/CHF": "USDCHF",
    "USD/JPY": "USDJPY",
    "XAU/USD": "XAUUSD",
    "XAG/USD": "XAGUSD",
}

_CME_TO_FXSSI = {
    "6EM6": "EURUSD",
    "6BM6": "GBPUSD",
    "6JM6": "USDJPY",
    "6AM6": "AUDUSD",
    "6CM6": "USDCAD",
    "6NM6": "NZDUSD",
    "6SM6": "USDCHF",
    "GCM6": "XAUUSD",
}

_FXSSI_URL = "https://fxssi.com/tools/current-ratio"

_cached_ratios: Dict[str, float] = {}
_cache_time: float = 0.0


def _get_conn():
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fxssi_sentiment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT,
            buy_pct REAL,
            sell_pct REAL,
            signal TEXT,
            fetched_at TEXT,
            UNIQUE(pair, fetched_at)
        )
    """)
    conn.commit()


def _parse_sentiment_from_html(html: str) -> Dict[str, Dict[str, float]]:
    results: Dict[str, Dict[str, float]] = {}

    # Pattern 1: JSON data in page source
    json_match = re.search(r'"ratios"\s*:\s*(\[.*?\])', html, re.DOTALL)
    if json_match:
        try:
            ratios = json.loads(json_match.group(1))
            for item in ratios:
                pair = item.get("symbol", "").replace("/", "")
                buy_pct = float(item.get("buy", 0)) / 100.0
                sell_pct = float(item.get("sell", 0)) / 100.0
                if pair:
                    results[pair] = {"buy_pct": buy_pct, "sell_pct": sell_pct}
        except (json.JSONDecodeError, ValueError):
            pass

    if results:
        return results

    # Pattern 2: FXSSI current-ratio page HTML structure
    # <div class="line" data-avg="..."><div class="symbol">EURUSD</div>
    # <div class="ratio-bar-left" style="width: 68%;">68%</div>
    # <div class="ratio-bar-right" style="width: 32%;">32%</div>
    line_matches = re.findall(
        r'<div class="line"[^>]*data-avg="([^"]+)"[^>]*>.*?'
        r'<div class="symbol">(\w+)</div>.*?'
        r'ratio-bar-left.*?(\d{1,3})%.*?'
        r'ratio-bar-right.*?(\d{1,3})%',
        html, re.DOTALL
    )
    if line_matches:
        for avg_str, pair, buy_str, sell_str in line_matches:
            try:
                buy_pct = int(buy_str) / 100.0
                sell_pct = int(sell_str) / 100.0
                results[pair] = {"buy_pct": buy_pct, "sell_pct": sell_pct, "avg": float(avg_str)}
            except (ValueError, ZeroDivisionError):
                pass
        if results:
            return results

    # Pattern 3: Fallback — pair name followed by percentages
    for fxssi_pair, clean_pair in _PAIR_MAP.items():
        escaped = re.escape(fxssi_pair.replace("/", ""))
        pattern = rf'{escaped}\s*.*?(\d{{1,3}})%\s*.*?(\d{{1,3}})%'
        match = re.search(pattern, html[:500000])
        if match:
            buy_pct = int(match.group(1)) / 100.0
            sell_pct = int(match.group(2)) / 100.0
            results[clean_pair] = {"buy_pct": buy_pct, "sell_pct": sell_pct}

    return results


def scrape_fxssi_sentiment() -> Dict[str, float]:
    if not _ENABLED or requests is None:
        return {}

    global _cached_ratios, _cache_time
    if _cached_ratios and (time.time() - _cache_time) < _CACHE_TTL:
        return _cached_ratios

    try:
        resp = requests.get(
            _FXSSI_URL,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
            timeout=15,
        )
        if resp.status_code != 200:
            LOGGER.warning("FXSSI returned %d", resp.status_code)
            _HEALTH.record_failure()
            return _cached_ratios
        html = resp.text
        _HEALTH.record_success()
    except Exception as exc:
        LOGGER.warning("FXSSI fetch error: %s", exc)
        _HEALTH.record_failure()
        return _cached_ratios

    parsed = _parse_sentiment_from_html(html)
    if not parsed:
        LOGGER.warning("FXSSI: could not parse sentiment from page")
        return _cached_ratios

    conn = _get_conn()
    _ensure_table(conn)

    result: Dict[str, float] = {}
    now = datetime.now(timezone.utc).isoformat()

    for pair, data in parsed.items():
        buy_pct = data["buy_pct"]
        sell_pct = data["sell_pct"]

        signal = "BUY" if buy_pct > 0.6 else ("SELL" if sell_pct > 0.6 else "NEUTRAL")

        try:
            conn.execute(
                "INSERT OR IGNORE INTO fxssi_sentiment "
                "(pair, buy_pct, sell_pct, signal, fetched_at) VALUES (?,?,?,?,?)",
                (pair, buy_pct, sell_pct, signal, now),
            )
        except Exception:
            pass

        result[pair] = buy_pct

    conn.commit()
    conn.close()

    _cached_ratios = result
    _cache_time = time.time()
    LOGGER.info("FXSSI: %d pairs scraped", len(result))
    return result


def get_buy_pct(symbol: str) -> float:
    data = scrape_fxssi_sentiment()
    fxssi_pair = _CME_TO_FXSSI.get(symbol, "")
    if fxssi_pair:
        return data.get(fxssi_pair, 0.5)
    return 0.5


def is_crowded(symbol: str, direction: str) -> bool:
    buy_pct = get_buy_pct(symbol)
    if direction == "BUY" and buy_pct > _CROWD_THRESHOLD:
        return True
    if direction == "SELL" and (1.0 - buy_pct) > _CROWD_THRESHOLD:
        return True
    return False


def get_fade_bonus(symbol: str, direction: str) -> float:
    if is_crowded(symbol, direction):
        return _FADE_BONUS
    return 0.0


def get_sentiment_signal(symbol: str) -> str:
    buy_pct = get_buy_pct(symbol)
    if buy_pct > 0.6:
        return "SELL"
    if buy_pct < 0.4:
        return "BUY"
    return "NEUTRAL"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = scrape_fxssi_sentiment()
    for pair, buy in sorted(result.items()):
        sell = 1.0 - buy
        sig = "SELL" if buy > 0.6 else ("BUY" if buy < 0.4 else "NEUTRAL")
        print(f"  {pair}: BUY={buy:.0%} SELL={sell:.0%} signal={sig}")
