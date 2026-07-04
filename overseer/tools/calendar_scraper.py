"""Economic Calendar Scraper for OVERSEER v12.

Scrapes upcoming economic events from public sources and provides them
in the format expected by ``gate_news.py`` (``GateNews``).

Data sources (tried in order):
1. Investing.com economic calendar (HTML scrape)
2. ForexFactory free JSON API mirror
3. Graceful empty-list fallback

Run standalone::

    python tools/calendar_scraper.py
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

from tools.scraper_utils import fetch_with_retry, ScraperHealth, is_data_stale

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as _exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependencies. Run:  pip install requests beautifulsoup4"
    ) from _exc

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

LOGGER = logging.getLogger("overseer.calendar_scraper")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_DIR = _PROJECT_ROOT / "config"
_CALENDAR_JSON = _CONFIG_DIR / "economic_calendar.json"
_DB_PATH = _PROJECT_ROOT / "database" / "overseer_trades.db"

_REFRESH_INTERVAL_SEC = int(os.getenv("CALENDAR_REFRESH_SECONDS", str(4 * 3600)))

# URLs
_INVESTING_URL = "https://www.investing.com/economic-calendar/"
_FF_API_URL_THIS_WEEK = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
}

# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

_TABLE_SCHEMA = """\
CREATE TABLE IF NOT EXISTS economic_calendar (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    currency      TEXT,
    impact        TEXT,
    forecast      TEXT,
    previous      TEXT,
    actual        TEXT,
    datetime_utc  TEXT,
    timestamp_ms  INTEGER,
    scraped_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_TABLE_SCHEMA)


def _save_to_db(events: list[dict[str, Any]]) -> None:
    """Persist calendar events to SQLite."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure_table(conn)
            for ev in events:
                conn.execute(
                    """
                    INSERT INTO economic_calendar
                        (name, currency, impact, forecast, previous, actual,
                         datetime_utc, timestamp_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev.get("name", ""),
                        ev.get("currency", ""),
                        ev.get("impact", ""),
                        ev.get("forecast", ""),
                        ev.get("previous", ""),
                        ev.get("actual", ""),
                        ev.get("datetime", ""),
                        ev.get("timestamp_ms", 0),
                    ),
                )
            conn.commit()
        LOGGER.info("Saved %d events to SQLite.", len(events))
    except Exception as exc:
        LOGGER.warning("Failed to save events to DB: %s", exc)


# ---------------------------------------------------------------------------
# Scraping helpers
# ---------------------------------------------------------------------------

_IMPACT_MAP = {
    "Holiday": "low",
    "Low": "low",
    "Medium": "medium",
    "High": "high",
    "low": "low",
    "medium": "medium",
    "high": "high",
}


def _parse_impact_class(css_classes: list[str]) -> str:
    """Derive impact from Investing.com CSS classes like 'bull3' / 'bull2'."""
    for cls in css_classes:
        cls_lower = cls.lower()
        if "bull3" in cls_lower or "high" in cls_lower:
            return "high"
        if "bull2" in cls_lower or "medium" in cls_lower or "moder" in cls_lower:
            return "medium"
        if "bull1" in cls_lower or "low" in cls_lower:
            return "low"
    return "low"


def _scrape_investing() -> list[dict[str, Any]]:
    """Attempt to scrape Investing.com economic calendar."""
    LOGGER.info("Attempting Investing.com scrape …")
    try:
        resp = requests.get(_INVESTING_URL, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        LOGGER.warning("Investing.com request failed: %s", exc)
        return []

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        events: list[dict[str, Any]] = []
        # Investing.com uses a table with id 'economicCalendarData'
        table = soup.find("table", {"id": "economicCalendarData"})
        if not table:
            # Try alternative selectors
            table = soup.find("table", class_=lambda c: c and "calendar" in c.lower()) if soup else None
        if not table:
            LOGGER.warning("Could not find calendar table on Investing.com")
            return []

        current_date = ""
        rows = table.find_all("tr")  # type: ignore[union-attr]
        for row in rows:
            # Date header rows
            date_cell = row.find("td", class_=lambda c: c and "theDay" in str(c))
            if date_cell:
                current_date = date_cell.get_text(strip=True)
                continue

            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            try:
                time_text = cells[0].get_text(strip=True)
                currency = cells[1].get_text(strip=True)

                # Impact from sentiment icon classes
                impact_cell = cells[2] if len(cells) > 2 else None
                impact_str = "low"
                if impact_cell:
                    icon = impact_cell.find("i") or impact_cell.find("span")
                    if icon:
                        impact_str = _parse_impact_class(icon.get("class", []))

                event_name = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                actual = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                forecast = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                previous = cells[6].get_text(strip=True) if len(cells) > 6 else ""

                # Build UTC datetime
                dt_str = f"{current_date} {time_text}".strip()
                try:
                    dt = datetime.strptime(dt_str, "%b %d, %Y %H:%M")
                    dt = dt.replace(tzinfo=ZoneInfo("US/Eastern"))
                    dt = dt.astimezone(timezone.utc)
                    ts_ms = int(dt.timestamp() * 1000)
                except ValueError:
                    ts_ms = 0
                    dt_str = ""

                events.append({
                    "name": event_name,
                    "impact": impact_str,
                    "timestamp_ms": ts_ms,
                    "datetime": dt.isoformat() if ts_ms else dt_str,
                    "currency": currency.upper(),
                    "forecast": forecast,
                    "previous": previous,
                    "actual": actual,
                })
            except Exception as row_exc:
                LOGGER.debug("Skipping row parse error: %s", row_exc)
                continue

        LOGGER.info("Investing.com: parsed %d events", len(events))
        return events

    except Exception as exc:
        LOGGER.warning("Investing.com parse error: %s", exc)
        return []


def _scrape_ff_api() -> list[dict[str, Any]]:
    LOGGER.info("Attempting ForexFactory API mirror ...")
    events: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for url in (_FF_API_URL_THIS_WEEK,):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            if resp.status_code == 429:
                LOGGER.warning("ForexFactory API rate-limited (%s) — skipping", url)
                continue
            resp.raise_for_status()
            raw: list[dict[str, Any]] = resp.json()
        except Exception as exc:
            LOGGER.warning("ForexFactory API request failed (%s): %s", url, exc)
            continue

        for item in raw:
            try:
                title = str(item.get("title", ""))
                country = str(item.get("country", "")).upper()
                impact_raw = str(item.get("impact", "Low"))
                impact = _IMPACT_MAP.get(impact_raw, "low")
                forecast = str(item.get("forecast", ""))
                previous = str(item.get("previous", ""))
                actual = str(item.get("actual", ""))

                date_str = str(item.get("date", ""))
                ts_ms = 0
                iso_str = date_str
                if date_str:
                    try:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        ts_ms = int(dt.timestamp() * 1000)
                        iso_str = dt.isoformat()
                    except ValueError:
                        pass

                key = f"{country}|{title}|{ts_ms}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                events.append({
                    "name": title,
                    "impact": impact,
                    "timestamp_ms": ts_ms,
                    "datetime": iso_str,
                    "currency": country,
                    "forecast": forecast,
                    "previous": previous,
                    "actual": actual,
                })
            except Exception as item_exc:
                LOGGER.debug("Skipping FF item parse error: %s", item_exc)
                continue

    LOGGER.info("ForexFactory API: parsed %d events", len(events))
    return events


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_LAST_REFRESH_TIME: float = 0.0
_calendar_health = ScraperHealth("calendar")


def get_calendar_health() -> ScraperHealth:
    return _calendar_health


def scrape_calendar(force: bool = False) -> list[dict[str, Any]]:
    """Scrape economic calendar from available sources.

    Respects the auto-refresh interval (default 4 h) unless *force* is True.
    Returns a list of event dicts and persists to JSON + SQLite.
    """
    global _last_refresh_time

    now = time.time()
    if not force and (now - _last_refresh_time) < _REFRESH_INTERVAL_SEC:
        if _CALENDAR_JSON.exists():
            try:
                return json.loads(_CALENDAR_JSON.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    LOGGER.info("Starting calendar scrape (force=%s) ...", force)

    events = fetch_with_retry(_scrape_ff_api, label="calendar_ff")
    if not events:
        events = fetch_with_retry(_scrape_investing, label="calendar_investing")

    if not events:
        _calendar_health.record_failure()
        LOGGER.warning("All calendar sources failed.")
        if _CALENDAR_JSON.exists():
            try:
                cached = json.loads(_CALENDAR_JSON.read_text(encoding="utf-8"))
                if cached:
                    LOGGER.warning("Returning stale cached calendar data (%d events).", len(cached))
                    return cached
            except (json.JSONDecodeError, OSError):
                pass
        return []

    _calendar_health.record_success(count=len(events))

    # Persist results
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _CALENDAR_JSON.write_text(
            json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        LOGGER.info("Saved %d events to %s", len(events), _CALENDAR_JSON)
    except OSError as exc:
        LOGGER.warning("Failed to write calendar JSON: %s", exc)

    _save_to_db(events)
    _last_refresh_time = time.time()
    return events


def get_upcoming_events(hours_ahead: int = 24) -> list[dict[str, Any]]:
    """Return high-impact events within the next *hours_ahead* hours.

    Automatically triggers a refresh if stale.
    """
    events = scrape_calendar()
    if not events:
        return []

    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms + hours_ahead * 3600 * 1000

    upcoming: list[dict[str, Any]] = []
    for ev in events:
        ts = int(ev.get("timestamp_ms", 0))
        if ts <= 0:
            continue
        if not (now_ms <= ts <= cutoff_ms):
            continue
        if ev.get("impact", "").lower() == "high":
            upcoming.append(ev)

    upcoming.sort(key=lambda e: e.get("timestamp_ms", 0))
    LOGGER.info(
        "Upcoming high-impact events (next %dh): %d found", hours_ahead, len(upcoming)
    )
    return upcoming


def get_event_history(
    event_name: str,
    currency: str,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Query SQLite for past occurrences of an event (Framework 7 beat/miss).

    Returns the most recent *limit* rows matching *event_name* and *currency*,
    ordered newest-first.
    """
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure_table(conn)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT name, currency, impact, forecast, previous, actual,
                       datetime_utc, timestamp_ms, scraped_at
                FROM economic_calendar
                WHERE name LIKE ? AND currency = ?
                ORDER BY timestamp_ms DESC
                LIMIT ?
                """,
                (f"%{event_name}%", currency.upper(), limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        LOGGER.warning("get_event_history query failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    print("=" * 60)
    print("OVERSEER — Economic Calendar Scraper")
    print("=" * 60)

    all_events = scrape_calendar(force=True)
    print(f"\nTotal events scraped: {len(all_events)}")

    upcoming = get_upcoming_events(hours_ahead=24)
    print(f"High-impact in next 24h: {len(upcoming)}")
    for ev in upcoming[:5]:
        print(f"  [{ev['impact'].upper():6s}] {ev['datetime']}  {ev['currency']}  {ev['name']}")

    history = get_event_history("CPI", "USD", limit=5)
    print(f"\nCPI (USD) history: {len(history)} records")
    for h in history:
        print(f"  {h.get('datetime_utc', '')}  F={h.get('forecast')}  P={h.get('previous')}  A={h.get('actual')}")

    print("\nDone.")
