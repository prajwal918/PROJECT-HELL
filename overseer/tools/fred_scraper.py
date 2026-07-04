"""FRED (Federal Reserve Economic Data) Scraper for OVERSEER v12.5.

Fetches key US macro data from the FRED API:
  - US Treasury yields (2Y, 10Y, 30Y)
  - Yield curve spread (2s10s)
  - Federal Funds Rate
  - CPI (Consumer Price Index)
  - Non-Farm Payrolls
  - GDP

Data is cached in SQLite and used by ml/fundamental_bias.py for
rate-differential bias adjustments.

Requires FRED_API_KEY env var (free at https://fred.stlouisfed.org/docs/api/fred/).

Run standalone::

    python tools/fred_scraper.py
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.scraper_utils import fetch_with_retry, ScraperHealth, is_data_stale

try:
    from fredapi import Fred
except ImportError:
    Fred = None

LOGGER = logging.getLogger("overseer.fred_scraper")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = _PROJECT_ROOT / "database" / "overseer_trades.db"
_FRED_JSON = _PROJECT_ROOT / "config" / "fred_latest.json"

_FRED_API_KEY = os.getenv("FRED_API_KEY", "")
_FRED_INTER_REQUEST_DELAY = float(os.getenv("FRED_INTER_REQUEST_DELAY", "0.5"))

_SERIES = {
    "DGS2": {"label": "us_2y_yield", "desc": "2-Year Treasury"},
    "DGS10": {"label": "us_10y_yield", "desc": "10-Year Treasury"},
    "DGS30": {"label": "us_30y_yield", "desc": "30-Year Treasury"},
    "T10Y2Y": {"label": "us_2s10s_spread", "desc": "10Y-2Y Spread"},
    "FEDFUNDS": {"label": "fed_funds_rate", "desc": "Fed Funds Rate"},
    "CPIAUCSL": {"label": "us_cpi_yoy", "desc": "CPI (YoY)"},
    "PAYEMS": {"label": "us_nfp", "desc": "Non-Farm Payrolls"},
    "GDP": {"label": "us_gdp_yoy", "desc": "GDP"},
    "IR3TIB01GBM156N": {"label": "boe_rate", "desc": "BoE Policy Rate"},
    "IR3TIB01JPM156N": {"label": "boj_rate", "desc": "BoJ Policy Rate"},
    "IR3TIB01AUM156N": {"label": "rba_rate", "desc": "RBA Cash Rate"},
    "IR3TIB01CAM156N": {"label": "boc_rate", "desc": "BoC Policy Rate"},
    "IR3TIB01NZM156N": {"label": "rbnz_rate", "desc": "RBNZ Official Rate"},
    "IR3TIB01CHM156N": {"label": "snb_rate", "desc": "SNB Policy Rate"},
}

health = ScraperHealth("fred")

_fred_client: Fred | None = None


def _get_client() -> Fred:
    global _fred_client
    if Fred is None:
        raise ImportError("fredapi not installed. Run: pip install fredapi")
    if _fred_client is None:
        if not _FRED_API_KEY:
            raise ValueError("FRED_API_KEY env var not set.")
        _fred_client = Fred(api_key=_FRED_API_KEY)
    return _fred_client


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fred_data (
            series_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            value REAL,
            date TEXT,
            unit TEXT,
            scraped_at TEXT NOT NULL
        )
    """)
    conn.commit()


def fetch_series(series_id: str) -> dict[str, Any] | None:
    fred = _get_client()
    try:
        series_info = fred.get_series_info(series_id)
        data = fred.get_series(series_id)
        if data is None or data.empty:
            return None
        latest_date = str(data.index[-1].date())
        latest_value = float(data.iloc[-1])
        return {
            "series_id": series_id,
            "label": _SERIES.get(series_id, {}).get("label", series_id),
            "value": latest_value,
            "date": latest_date,
            "unit": series_info.get("units", ""),
        }
    except Exception as exc:
        LOGGER.warning("FRED fetch %s failed: %s", series_id, exc)
        return None


def scrape_fred(force: bool = False) -> dict[str, Any]:
    if not _FRED_API_KEY or Fred is None:
        LOGGER.warning("FRED_API_KEY not set or fredapi not installed — skipping FRED scrape")
        return {}

    conn = sqlite3.connect(str(_DB_PATH))
    try:
        _ensure_table(conn)

        if not force:
            cur = conn.execute("SELECT MAX(scraped_at) FROM fred_data")
            row = cur.fetchone()
            if row and row[0] and not is_data_stale(row[0], max_age_hours=6.0):
                LOGGER.info("FRED data fresh (<6h) — skipping")
                cur2 = conn.execute("SELECT series_id, label, value, date FROM fred_data")
                cached = {}
                for r in cur2.fetchall():
                    cached[r[1]] = {"value": r[2], "date": r[3], "series_id": r[0]}
                return cached

        results: dict[str, Any] = {}
        now_iso = datetime.now(tz=timezone.utc).isoformat()

        for series_id, meta in _SERIES.items():
            record = fetch_with_retry(
                lambda sid=series_id: fetch_series(sid),
                label=f"fred_{series_id}",
            )
            if record and isinstance(record, dict):
                results[meta["label"]] = record
                conn.execute(
                    """INSERT OR REPLACE INTO fred_data
                    (series_id, label, value, date, unit, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (record["series_id"], record["label"], record["value"],
                     record["date"], record.get("unit", ""), now_iso),
                )
                conn.commit()
            if _FRED_INTER_REQUEST_DELAY > 0:
                time.sleep(_FRED_INTER_REQUEST_DELAY)
    finally:
        conn.close()

    if results:
        _FRED_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(_FRED_JSON, "w") as f:
            json.dump(results, f, indent=2)
        health.record_success(count=len(results))
        LOGGER.info("FRED scrape OK — %d series updated", len(results))
    else:
        health.record_failure()

    return results


def get_fred_data() -> dict[str, Any]:
    if not _FRED_API_KEY:
        return {}
    if _FRED_JSON.exists():
        try:
            with open(_FRED_JSON) as f:
                return json.load(f)
        except Exception:
            pass
    return scrape_fred(force=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = scrape_fred(force=True)
    for key, val in data.items():
        print(f"  {key}: {val.get('value', 'N/A')} ({val.get('date', '?')})")
