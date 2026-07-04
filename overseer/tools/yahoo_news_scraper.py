"""FX News Sentiment Scraper for OVERSEER v14.

Multi-source FX news sentiment:
1. Finnhub (free tier, 60 req/min) — headline keyword scoring
2. ForexFactory news page scraping — direct HTML parse
3. Fallback: DB cache of previous sentiment

Scores headlines for USD/EUR/GBP/JPY/CAD/AUD sentiment using
keyword matching with bullish/bearish word lists.
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
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    requests = None

from tools.scraper_utils import ScraperHealth

LOGGER = logging.getLogger("overseer.yahoo_news")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = _PROJECT_ROOT / "database" / "overseer_trades.db"

_ENABLED = os.getenv("YAHOO_NEWS_ENABLED", "true").lower() == "true"
_FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")
_CACHE_TTL = float(os.getenv("YAHOO_NEWS_CACHE_TTL", "3600"))

_HEALTH = ScraperHealth("yahoo_news")

_CURRENCY_KEYWORDS = {
    "USD": ["dollar", "fed ", "fomc", "treasury", "us economy", "us gdp",
            "us inflation", "us cpi", "us nfp", "nonfarm", "us rates",
            "us interest rate", "us tariff", "us trade"],
    "EUR": ["euro", "ecb", "european central bank", "eurozone", "eu gdp",
            "eu inflation", "bund", "euribor", "eu rates"],
    "GBP": ["pound", "sterling", "boe", "bank of england", "uk gdp",
            "uk inflation", "uk rates", "ftse"],
    "JPY": ["yen", "boj", "bank of japan", "japan gdp", "japan inflation",
            "japan rates", "nikkei"],
    "CAD": ["canadian dollar", "loonie", "boc", "bank of canada",
            "canada gdp", "canada rates", "oil price", "crude oil"],
    "AUD": ["australian dollar", "aussie", "rba", "reserve bank of australia",
            "australia gdp", "australia rates"],
    "CHF": ["swiss franc", "snb", "swiss national bank", "switzerland"],
    "NZD": ["kiwi", "rbnz", "reserve bank of new zealand", "new zealand"],
}

_BULLISH_WORDS = ["hawkish", "rate hike", "tightening", "strong ", "surge",
                  "rally", "bullish", "upgrade", "beat expectations", "higher than expected",
                  "growth", "recovery", "boom", "expansion"]

_BEARISH_WORDS = ["dovish", "rate cut", "easing", "weak ", "slump", "plunge",
                  "bearish", "downgrade", "miss expectations", "lower than expected",
                  "recession", "crisis", "contraction", "slowdown", "deficit"]

_cached_sentiment: Dict[str, float] = {}
_cache_time: float = 0.0


def _get_conn():
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS yahoo_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            currency TEXT NOT NULL,
            sentiment_score REAL DEFAULT 0,
            headline_count INTEGER DEFAULT 0,
            bullish_count INTEGER DEFAULT 0,
            bearish_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'finnhub',
            fetched_at TEXT NOT NULL,
            UNIQUE(currency, fetched_at)
        )
    """)
    conn.commit()


def _score_text(text: str) -> Dict[str, float]:
    text_lower = text.lower()
    scores: Dict[str, float] = {}

    for currency, keywords in _CURRENCY_KEYWORDS.items():
        hit = any(kw in text_lower for kw in keywords)
        if not hit:
            scores[currency] = 0.0
            continue

        bull = sum(1 for w in _BULLISH_WORDS if w in text_lower)
        bear = sum(1 for w in _BEARISH_WORDS if w in text_lower)
        net = (bull - bear) / max(bull + bear, 1)
        scores[currency] = round(net, 3)

    return scores


def _fetch_finnhub_headlines() -> List[Dict[str, str]]:
    if not _FINNHUB_KEY or requests is None:
        return []
    articles = []
    categories = ["forex", "general"]
    for cat in categories:
        try:
            url = f"https://finnhub.io/api/v1/news?category={cat}&token={_FINNHUB_KEY}"
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                continue
            items = resp.json()
            if not isinstance(items, list):
                continue
            for item in items[:50]:
                title = item.get("headline", "")
                summary = item.get("summary", "")
                ts = item.get("datetime", 0)
                pub_date = ""
                if ts:
                    try:
                        from datetime import datetime as _dt
                        pub_date = _dt.utcfromtimestamp(int(ts)).isoformat()
                    except Exception:
                        pass
                articles.append({
                    "title": title,
                    "summary": summary or "",
                    "source": item.get("source", "finnhub"),
                    "pub_date": pub_date,
                })
        except Exception as exc:
            LOGGER.debug("Finnhub %s error: %s", cat, exc)
    return articles


def _fetch_forexfactory_headlines() -> List[Dict[str, str]]:
    if requests is None:
        return []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        }
        resp = requests.get("https://www.forexfactory.com/news", headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        html = resp.text
        articles = []
        # Parse news titles from ForexFactory
        title_matches = re.findall(
            r'class="[^"]*news-title[^"]*"[^>]*>([^<]+)',
            html
        )
        if not title_matches:
            title_matches = re.findall(
                r'<a[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)',
                html
            )
        if not title_matches:
            # Fallback: find any headline-looking text
            title_matches = re.findall(
                r'<span[^>]*class="[^"]*subject[^"]*"[^>]*>([^<]+)',
                html
            )
        for t in title_matches[:30]:
            articles.append({
                "title": t.strip(),
                "summary": "",
                "source": "forexfactory",
                "pub_date": "",
            })
        return articles
    except Exception as exc:
        LOGGER.debug("ForexFactory news error: %s", exc)
        return []


def _fetch_db_cache() -> Dict[str, float]:
    try:
        conn = _get_conn()
        _ensure_table(conn)
        rows = conn.execute(
            "SELECT currency, sentiment_score, fetched_at FROM yahoo_news "
            "ORDER BY fetched_at DESC LIMIT 100"
        ).fetchall()
        conn.close()
        result: Dict[str, float] = {}
        seen = set()
        for r in rows:
            curr = r[0]
            if curr not in seen:
                result[f"{curr}_sentiment"] = r[1] or 0.0
                seen.add(curr)
        return result
    except Exception:
        return {}


def scrape_yahoo_news() -> Dict[str, float]:
    if not _ENABLED or requests is None:
        return {}

    global _cached_sentiment, _cache_time
    if _cached_sentiment and (time.time() - _cache_time) < _CACHE_TTL:
        return _cached_sentiment

    # Source 1: Finnhub
    articles = _fetch_finnhub_headlines()
    source_name = "finnhub"

    # Source 2: ForexFactory
    if len(articles) < 5:
        ff_articles = _fetch_forexfactory_headlines()
        articles.extend(ff_articles)
        source_name = "multi"

    if not articles:
        LOGGER.warning("No news articles from any source")
        _HEALTH.record_failure()
        cached = _fetch_db_cache()
        if cached:
            _cached_sentiment = cached
            return cached
        return _cached_sentiment

    _HEALTH.record_success()

    conn = _get_conn()
    _ensure_table(conn)

    agg: Dict[str, List[float]] = {c: [] for c in _CURRENCY_KEYWORDS}

    for art in articles:
        text = f"{art['title']} {art['summary']}"
        scores = _score_text(text)

        for currency, score in scores.items():
            if score != 0.0:
                agg[currency].append(score)

    now = datetime.now(timezone.utc).isoformat()
    result: Dict[str, float] = {}

    for currency, score_list in agg.items():
        if score_list:
            avg = round(sum(score_list) / len(score_list), 4)
        else:
            avg = 0.0
        result[f"{currency}_sentiment"] = avg

        try:
            conn.execute(
                "INSERT OR REPLACE INTO yahoo_news "
                "(currency, sentiment_score, headline_count, "
                "bullish_count, bearish_count, source, fetched_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (currency, avg, len(score_list),
                 sum(1 for s in score_list if s > 0),
                 sum(1 for s in score_list if s < 0),
                 source_name, now),
            )
        except Exception:
            pass

    conn.commit()
    conn.close()

    _cached_sentiment = result
    _cache_time = time.time()
    LOGGER.info("FX News: %d articles, sentiment keys=%d", len(articles), len(result))
    return result


def get_usd_sentiment() -> float:
    data = scrape_yahoo_news()
    return data.get("USD_sentiment", 0.0)


def get_currency_sentiment(currency: str) -> float:
    data = scrape_yahoo_news()
    return data.get(f"{currency}_sentiment", 0.0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = scrape_yahoo_news()
    for k, v in sorted(result.items()):
        print(f"  {k}: {v:+.4f}")
