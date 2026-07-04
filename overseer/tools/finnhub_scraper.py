"""Finnhub News & Sentiment Scraper for OVERSEER v12.5.

Fetches forex-relevant market news with sentiment scoring from Finnhub.
Free tier: 60 calls/min.

Provides:
  - Market news with sentiment (bearish/neutral/bullish)
  - Economic calendar (supplements ForexFactory scraper)

Requires FINNHUB_API_KEY env var (free at https://finnhub.io/).

Run standalone::

    python tools/finnhub_scraper.py
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.scraper_utils import fetch_with_retry, ScraperHealth, is_data_stale

try:
    import requests
except ImportError as _exc:
    raise SystemExit("Missing dependency. Run: pip install requests") from _exc

LOGGER = logging.getLogger("overseer.finnhub_scraper")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = _PROJECT_ROOT / "database" / "overseer_trades.db"
_FINNHUB_JSON = _PROJECT_ROOT / "config" / "finnhub_latest.json"

_FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
_FINNHUB_BASE = "https://finnhub.io/api/v1"

health = ScraperHealth("finnhub")


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS finnhub_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            headline TEXT,
            source TEXT,
            url TEXT,
            sentiment REAL,
            timestamp TEXT,
            scraped_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS finnhub_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT,
            country TEXT,
            date TEXT,
            impact TEXT,
            actual REAL,
            estimate REAL,
            prev REAL,
            scraped_at TEXT NOT NULL
        )
    """)
    conn.commit()


_BULLISH_WORDS = frozenset([
    "surge", "rally", "jump", "gain", "rise", "soar", "bullish", "boost",
    "climb", "advance", "upbeat", "strong", "optimis", "hawkish", "tighten",
])
_BEARISH_WORDS = frozenset([
    "slump", "drop", "fall", "plunge", "bearish", "dive", "sink", "tumble",
    "decline", "weak", "pessimis", "dovish", "easing", "cut", "slash",
])


def _score_headline(text: str) -> float:
    lower = text.lower()
    bull = sum(1 for w in _BULLISH_WORDS if w in lower)
    bear = sum(1 for w in _BEARISH_WORDS if w in lower)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total


def _fetch_market_news() -> list[dict[str, Any]]:
    all_articles: list[dict[str, Any]] = []
    for category in ("forex", "general"):
        url = f"{_FINNHUB_BASE}/news"
        params = {"category": category, "token": _FINNHUB_API_KEY}
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                LOGGER.warning("Finnhub %s news returned %d", category, resp.status_code)
                continue
            articles = resp.json()
            if not isinstance(articles, list):
                continue
            for a in articles[:20]:
                sentiment = 0.0
                if isinstance(a.get("sentiment"), dict):
                    bearish = a["sentiment"].get("bearish", 0)
                    bullish = a["sentiment"].get("bullish", 0)
                    total = bearish + bullish
                    if total > 0:
                        sentiment = (bullish - bearish) / total
                else:
                    sentiment = _score_headline(a.get("headline", ""))
                ts = ""
                if a.get("datetime"):
                    try:
                        ts = datetime.fromtimestamp(a["datetime"], tz=timezone.utc).isoformat()
                    except (ValueError, OSError):
                        pass
                all_articles.append({
                    "category": a.get("category", category),
                    "headline": a.get("headline", ""),
                    "source": a.get("source", ""),
                    "url": a.get("url", ""),
                    "sentiment": sentiment,
                    "timestamp": ts,
                })
        except Exception as exc:
            LOGGER.warning("Finnhub %s news fetch failed: %s", category, exc)
    return all_articles


def _fetch_economic_calendar() -> list[dict[str, Any]]:
    url = f"{_FINNHUB_BASE}/calendar/economic"
    params = {"token": _FINNHUB_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            LOGGER.warning("Finnhub calendar returned %d", resp.status_code)
            return []
        data = resp.json()
        events = data.get("economicCalendar", [])
        if not isinstance(events, list):
            return []
        results = []
        for e in events[:30]:
            results.append({
                "event": e.get("event", ""),
                "country": e.get("country", ""),
                "date": e.get("date", ""),
                "impact": e.get("impact", ""),
                "actual": e.get("actual", None),
                "estimate": e.get("estimate", None),
                "prev": e.get("prev", None),
            })
        return results
    except Exception as exc:
        LOGGER.warning("Finnhub calendar fetch failed: %s", exc)
        return []


def scrape_finnhub(force: bool = False) -> dict[str, Any]:
    if not _FINNHUB_API_KEY:
        LOGGER.warning("FINNHUB_API_KEY not set — skipping Finnhub scrape")
        return {}

    conn = sqlite3.connect(str(_DB_PATH))
    _ensure_tables(conn)

    if not force:
        cur = conn.execute("SELECT MAX(scraped_at) FROM finnhub_news")
        row = cur.fetchone()
        if row and row[0] and not is_data_stale(row[0], max_age_hours=1.0):
            LOGGER.info("Finnhub data fresh (<1h) — skipping")
            conn.close()
            if _FINNHUB_JSON.exists():
                try:
                    with open(_FINNHUB_JSON) as f:
                        return json.load(f)
                except Exception:
                    pass
            return {}

    now_iso = datetime.now(tz=timezone.utc).isoformat()
    results: dict[str, Any] = {}

    news = fetch_with_retry(_fetch_market_news, label="finnhub_news")
    if news and isinstance(news, list):
        results["news"] = news
        conn.execute("DELETE FROM finnhub_news")
        for a in news:
            conn.execute(
                """INSERT INTO finnhub_news
                   (category, headline, source, url, sentiment, timestamp, scraped_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (a.get("category", ""), a.get("headline", ""), a.get("source", ""),
                 a.get("url", ""), a.get("sentiment", 0.0), a.get("timestamp", ""), now_iso),
            )
        avg_sentiment = sum(a.get("sentiment", 0.0) for a in news) / len(news) if news else 0.0
        results["avg_sentiment"] = avg_sentiment
        LOGGER.info("Finnhub: %d news articles, avg sentiment=%.3f", len(news), avg_sentiment)

    calendar = fetch_with_retry(_fetch_economic_calendar, label="finnhub_calendar")
    if calendar and isinstance(calendar, list):
        results["calendar"] = calendar
        conn.execute("DELETE FROM finnhub_calendar")
        for e in calendar:
            conn.execute(
                """INSERT INTO finnhub_calendar
                   (event, country, date, impact, actual, estimate, prev, scraped_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (e.get("event", ""), e.get("country", ""), e.get("date", ""),
                 e.get("impact", ""), e.get("actual"), e.get("estimate"),
                 e.get("prev"), now_iso),
            )
        LOGGER.info("Finnhub: %d calendar events", len(calendar))

    conn.commit()
    conn.close()

    if results:
        _FINNHUB_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(_FINNHUB_JSON, "w") as f:
            json.dump(results, f, indent=2, default=str)
        health.record_success(count=len(results))
    else:
        health.record_failure()

    return results


def get_finnhub_data() -> dict[str, Any]:
    if not _FINNHUB_API_KEY:
        return {}
    if _FINNHUB_JSON.exists():
        try:
            with open(_FINNHUB_JSON) as f:
                return json.load(f)
        except Exception:
            pass
    return scrape_finnhub(force=True)


def get_usd_sentiment() -> float:
    data = get_finnhub_data()
    if "avg_sentiment" in data:
        return data["avg_sentiment"]
    news = data.get("news", [])
    if not news:
        return 0.0
    usd_keywords = ("usd", "dollar", "fed ", "fomc", "treasury", "payroll", "cpi", "nfp", "rates", "interest")
    usd_articles = []
    for a in news:
        hl = a.get("headline", "").lower()
        if any(kw in hl for kw in usd_keywords):
            usd_articles.append(a)
    pool = usd_articles if usd_articles else news
    return sum(a.get("sentiment", 0.0) for a in pool) / len(pool)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = scrape_finnhub(force=True)
    print(f"News: {len(data.get('news', []))} articles")
    print(f"Avg sentiment: {data.get('avg_sentiment', 0.0):.3f}")
    print(f"Calendar: {len(data.get('calendar', []))} events")
