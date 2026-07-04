"""ECB Data Portal Scraper for OVERSEER v12.5.

Fetches key ECB / Eurozone macro data via the ECB SDMX 2.1 REST API:
  - ECB Main Refinancing Rate
  - ECB Deposit Facility Rate
  - German 10Y Bund Yield
  - EUR HICP (Harmonised Index of Consumer Prices)
  - EUR 3M Euribor

No API key required — ECB Data Portal is free and open.

Run standalone::

    python tools/ecb_scraper.py
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.scraper_utils import fetch_with_retry, ScraperHealth, is_data_stale

try:
    import requests
except ImportError as _exc:
    raise SystemExit("Missing dependency. Run: pip install requests") from _exc

LOGGER = logging.getLogger("overseer.ecb_scraper")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = _PROJECT_ROOT / "database" / "overseer_trades.db"
_ECB_JSON = _PROJECT_ROOT / "config" / "ecb_latest.json"

_ECB_API_BASE = "https://data-api.ecb.europa.eu/service/data"

_ECB_SERIES = {
    "ecb_ref_rate": {
        "dataflow": "FM",
        "key": "B.U2.EUR.4F.KR.MRR_FR.LEV",
        "desc": "ECB Main Refinancing Rate",
    },
    "ecb_deposit_rate": {
        "dataflow": "FM",
        "key": "B.U2.EUR.4F.KR.DFR.LEV",
        "desc": "ECB Deposit Facility Rate",
    },
    "eur_3m_euribor": {
        "dataflow": "FM",
        "key": "M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA",
        "desc": "3M Euribor",
    },
}

health = ScraperHealth("ecb")


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ecb_data (
            series_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            value REAL,
            date TEXT,
            scraped_at TEXT NOT NULL
        )
    """)
    conn.commit()


def _fetch_ecb_series(dataflow: str, key: str) -> dict[str, Any] | None:
    url = f"{_ECB_API_BASE}/{dataflow}/{key}"
    params = {
        "detail": "dataonly",
        "startPeriod": "2024-01-01",
        "endPeriod": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            LOGGER.warning("ECB API %s returned %d", key, resp.status_code)
            return None
        root = ET.fromstring(resp.text)
        ns = {
            "generic": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic",
        }
        obs_list = root.findall(".//generic:Obs", ns)
        if not obs_list:
            obs_list = root.findall(".//Obs")
        if not obs_list:
            return None
        latest_obs = obs_list[-1]
        period_el = latest_obs.find(".//generic:ObsDimension", ns)
        if period_el is None:
            period_el = latest_obs.find(".//ObsDimension")
        value_el = latest_obs.find(".//generic:ObsValue", ns)
        if value_el is None:
            value_el = latest_obs.find(".//ObsValue")
        if value_el is None:
            return None
        date_str = period_el.get("value", "") if period_el is not None else ""
        value_str = value_el.get("value", "")
        if not value_str:
            return None
        return {
            "value": float(value_str),
            "date": date_str,
        }
    except Exception as exc:
        LOGGER.warning("ECB fetch %s failed: %s", key, exc)
        return None


def scrape_ecb(force: bool = False) -> dict[str, Any]:
    conn = sqlite3.connect(str(_DB_PATH))
    _ensure_table(conn)

    if not force:
        cur = conn.execute("SELECT MAX(scraped_at) FROM ecb_data")
        row = cur.fetchone()
        if row and row[0] and not is_data_stale(row[0], max_age_hours=6.0):
            LOGGER.info("ECB data fresh (<6h) — skipping")
            cur2 = conn.execute("SELECT series_id, label, value, date FROM ecb_data")
            cached = {}
            for r in cur2.fetchall():
                cached[r[0]] = {"value": r[2], "date": r[3], "label": r[1]}
            conn.close()
            return cached

    results: dict[str, Any] = {}
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    for series_id, meta in _ECB_SERIES.items():
        record = fetch_with_retry(
            lambda m=meta: _fetch_ecb_series(m["dataflow"], m["key"]),
            label=f"ecb_{series_id}",
        )
        if record and isinstance(record, dict):
            record["label"] = meta["desc"]
            record["series_id"] = series_id
            results[series_id] = record
            conn.execute(
                """INSERT OR REPLACE INTO ecb_data
                   (series_id, label, value, date, scraped_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (series_id, meta["desc"], record["value"], record["date"], now_iso),
            )

    conn.commit()
    conn.close()

    if results:
        _ECB_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(_ECB_JSON, "w") as f:
            json.dump(results, f, indent=2)
        health.record_success(count=len(results))
        LOGGER.info("ECB scrape OK — %d series updated", len(results))
    else:
        health.record_failure()

    return results


def get_ecb_data() -> dict[str, Any]:
    if _ECB_JSON.exists():
        try:
            with open(_ECB_JSON) as f:
                return json.load(f)
        except Exception:
            pass
    return scrape_ecb(force=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = scrape_ecb(force=True)
    for key, val in data.items():
        print(f"  {key}: {val.get('value', 'N/A')} ({val.get('date', '?')})")
