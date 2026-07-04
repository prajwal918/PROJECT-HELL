"""COT Reports Scraper for OVERSEER v14.

Direct CFTC CSV download with SSL workaround.
Falls back to the cot_reports library if available.

Extracts Non-Commercial (large speculator) positioning for FX futures
and computes z-scores for crowding detection.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import sqlite3
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    requests = None

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import numpy as np
except ImportError:
    np = None

from tools.scraper_utils import ScraperHealth

LOGGER = logging.getLogger("overseer.cot_reports_lib")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = _PROJECT_ROOT / "database" / "overseer_trades.db"

_ENABLED = os.getenv("COT_REPORTS_LIB_ENABLED", "true").lower() == "true"
_CACHE_TTL = float(os.getenv("COT_REPORTS_CACHE_TTL", "43200"))

_HEALTH = ScraperHealth("cot_reports_lib")

_CME_FUTURES_MAP = {
    "6E": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    "6B": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE",
    "6J": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
    "6A": "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "6C": "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "6S": "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE",
    "6N": "NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "GC": "GOLD - COMMODITY EXCHANGE INC.",
    "CL": "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
}

_SYMBOL_MAP = {
    "6E": "6EM6", "6B": "6BM6", "6J": "6JM6", "6A": "6AM6",
    "6C": "6CM6", "6S": "6SM6", "6N": "6NM6", "GC": "GCM6", "CL": "CLN6",
}

_ZSCORE_WINDOW = 52

_CFTC_URL = "https://www.cftc.gov/dea/futures/deacmelf.htm"
_CFTC_HIST_URL = "https://www.cftc.gov/files/dea/history/deacot2026.zip"
_CFTC_HIST_URL_2025 = "https://www.cftc.gov/files/dea/history/deacot2025.zip"

_cached_data: Dict[str, Any] = {}
_cache_time: float = 0.0


def _get_conn():
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cot_reports_lib (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument TEXT,
            report_date TEXT,
            noncomm_long INTEGER,
            noncomm_short INTEGER,
            net_position INTEGER,
            zscore REAL,
            source TEXT DEFAULT 'cftc_direct',
            fetched_at TEXT,
            UNIQUE(instrument, report_date)
        )
    """)
    conn.commit()


def _compute_zscore(positions: List[int]) -> float:
    if len(positions) < 10:
        return 0.0
    window = positions[-_ZSCORE_WINDOW:]
    mean = sum(window) / len(window)
    std = (sum((x - mean) ** 2 for x in window) / len(window)) ** 0.5
    if std < 1e-10:
        return 0.0
    return round((window[-1] - mean) / std, 4)


def _fetch_cftc_text() -> Optional[str]:
    if requests is not None:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            }
            resp = requests.get(_CFTC_URL, headers=headers, timeout=20, verify=False)
            if resp.status_code == 200:
                return resp.text
            LOGGER.warning("CFTC returned status %d", resp.status_code)
        except Exception as exc:
            LOGGER.warning("CFTC requests fetch error: %s", exc)

    # Fallback: urllib with SSL skip
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(
            _CFTC_URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        LOGGER.warning("CFTC urllib fetch error: %s", exc)
    return None


def _fetch_cftc_rapidapi() -> Optional[str]:
    key = os.getenv("RAPIDAPI_KEY", "")
    host = os.getenv("RAPIDAPI_HOST", "")
    if not key or not host or requests is None:
        return None
    try:
        url = f"https://{host}/v8/finance/chart/^EVZ"
        resp = requests.get(url, headers={"X-RapidAPI-Key": key, "X-RapidAPI-Host": host}, timeout=15)
        if resp.status_code == 200:
            return _fetch_cftc_text()
    except Exception:
        pass
    return None


def _parse_cftc_text(text: str) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    # Strip HTML tags to get plain text
    import re as _re
    text = _re.sub(r'<[^>]+>', '\n', text)
    text = _re.sub(r'&nbsp;', ' ', text)
    text = _re.sub(r'&#\d+;', ' ', text)
    lines = text.split('\n')
    current_code = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Detect instrument header
        for code, cme_name in _CME_FUTURES_MAP.items():
            short_name = cme_name.split(" - ")[0]
            if short_name in stripped.upper() and "CHICAGO MERCANTILE" in stripped.upper():
                current_code = code
                break
            if short_name in stripped.upper() and "COMMODITY EXCHANGE" in stripped.upper():
                current_code = code
                break
            if short_name in stripped.upper() and "NEW YORK MERCANTILE" in stripped.upper():
                current_code = code
                break
        # Parse "All :" line for non-commercial positions
        # Format: "All : 842,424: 235,442 186,576 40,759 479,684 549,080 ..."
        if current_code and stripped.startswith("All"):
            try:
                # Replace colons with spaces, then extract all integers
                clean = stripped.replace(":", " ").replace(",", " ")
                nums = []
                for p in clean.split():
                    try:
                        nums.append(int(p))
                    except ValueError:
                        continue
                # nums = [All_tag_ignored, OpenInterest, NonCommLong, NonCommShort, Spreading, ...]
                # After replacing All with spaces and splitting, "All" is not an int
                # So nums[0]=OpenInterest, nums[1]=NonCommLong, nums[2]=NonCommShort
                if len(nums) >= 3:
                    noncomm_long = nums[1]
                    noncomm_short = nums[2]
                    net = noncomm_long - noncomm_short
                    sym = _SYMBOL_MAP.get(current_code, current_code)
                    result[current_code] = {
                        "symbol": sym,
                        "long": noncomm_long,
                        "short": noncomm_short,
                        "net": net,
                    }
                    LOGGER.info("COT parsed %s: L=%d S=%d net=%d", code, noncomm_long, noncomm_short, net)
            except Exception as exc:
                LOGGER.debug("COT parse line error: %s", exc)
            current_code = None
    return result


def _fetch_via_library() -> Optional[Any]:
    try:
        from cot_reports import cot_year
        for year in [2026, 2025]:
            try:
                df = cot_year(year=year, cot_report_type="legacy_fut", store_txt=False, verbose=False)
                if df is not None and not df.empty:
                    return df
            except Exception:
                continue
    except Exception:
        pass
    return None


def _parse_library_df(df) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for code, cme_name in _CME_FUTURES_MAP.items():
        try:
            if pd is not None:
                mask = df["Market_and_Exchange_Names"].str.upper().str.contains(
                    cme_name.upper(), na=False
                )
                sub = df[mask].sort_values("Report_Date_as_YYYY-MM-DD", ascending=False)
            else:
                continue

            if sub.empty:
                continue

            latest = sub.iloc[0]
            noncomm_long = int(latest.get("Noncommercial_Long", 0) or 0)
            noncomm_short = int(latest.get("Noncommercial_Short", 0) or 0)
            net = noncomm_long - noncomm_short

            history = []
            for _, row in sub.head(_ZSCORE_WINDOW).iterrows():
                nl = int(row.get("Noncommercial_Long", 0) or 0)
                ns = int(row.get("Noncommercial_Short", 0) or 0)
                history.append(nl - ns)

            zscore = _compute_zscore(history)
            sym = _SYMBOL_MAP.get(code, code)
            report_date = str(latest.get("Report_Date_as_YYYY-MM-DD", ""))

            result[code] = {
                "symbol": sym,
                "net": net,
                "long": noncomm_long,
                "short": noncomm_short,
                "zscore": zscore,
                "date": report_date,
                "source": "cot_library",
            }
        except Exception as exc:
            LOGGER.debug("COT library parse error for %s: %s", code, exc)
    return result


def scrape_cot_reports() -> Dict[str, Any]:
    if not _ENABLED:
        return {}

    global _cached_data, _cache_time
    if _cached_data and (time.time() - _cache_time) < _CACHE_TTL:
        return _cached_data

    result: Dict[str, Any] = {}

    # Method 1: Direct CFTC text fetch (most reliable)
    text = _fetch_cftc_text()
    if text:
        parsed = _parse_cftc_text(text)
        if parsed:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for code, entry in parsed.items():
                sym = entry["symbol"]
                # Compute z-score from DB history
                zscore = 0.0
                try:
                    conn2 = _get_conn()
                    _ensure_table(conn2)
                    hist = conn2.execute(
                        "SELECT net_position FROM cot_reports_lib "
                        "WHERE instrument=? ORDER BY report_date DESC LIMIT ?",
                        (sym, _ZSCORE_WINDOW),
                    ).fetchall()
                    positions = [r[0] for r in hist if r[0] is not None]
                    positions.append(entry["net"])
                    zscore = _compute_zscore(positions)
                    conn2.close()
                except Exception:
                    pass
                entry["zscore"] = zscore
                entry["date"] = today
                entry["source"] = "cftc_direct"
                result[code] = entry
            LOGGER.info("COT: fetched %d instruments via CFTC direct", len(result))

    # Method 2: Library fallback
    if not result:
        df = _fetch_via_library()
        if df is not None:
            result = _parse_library_df(df)
            if result:
                LOGGER.info("COT: fetched %d instruments via library", len(result))

    # Method 3: Try existing DB data
    if not result:
        try:
            conn = _get_conn()
            _ensure_table(conn)
            rows = conn.execute(
                "SELECT instrument, report_date, noncomm_long, noncomm_short, "
                "net_position, zscore FROM cot_reports_lib "
                "ORDER BY fetched_at DESC LIMIT 50"
            ).fetchall()
            conn.close()
            for r in rows:
                for code, sym in _SYMBOL_MAP.items():
                    if r[0] == sym:
                        result[code] = {
                            "symbol": sym, "net": r[4] or 0,
                            "long": r[2] or 0, "short": r[3] or 0,
                            "zscore": r[5] or 0.0, "date": r[1],
                            "source": "cached_db",
                        }
            if result:
                LOGGER.info("COT: loaded %d instruments from DB cache", len(result))
        except Exception:
            pass

    if not result:
        LOGGER.warning("COT: all methods failed")
        _HEALTH.record_failure()
        return _cached_data

    _HEALTH.record_success()

    conn = _get_conn()
    _ensure_table(conn)
    for code, entry in result.items():
        if entry.get("zscore", 0) == 0.0 and entry.get("net"):
            pass
        try:
            conn.execute(
                "INSERT OR REPLACE INTO cot_reports_lib "
                "(instrument, report_date, noncomm_long, noncomm_short, "
                "net_position, zscore, source, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                (entry.get("symbol", code), entry.get("date", ""),
                 entry.get("long", 0), entry.get("short", 0),
                 entry.get("net", 0), entry.get("zscore", 0),
                 entry.get("source", "unknown"),
                 datetime.now(timezone.utc).isoformat()),
            )
        except Exception:
            pass
    conn.commit()
    conn.close()

    _cached_data = result
    _cache_time = time.time()
    return result


def get_crowding_bonus(symbol: str) -> float:
    data = scrape_cot_reports()
    for code, entry in data.items():
        if entry.get("symbol") == symbol:
            zscore = entry.get("zscore", 0.0)
            if abs(zscore) > 2.0:
                return -0.05 if zscore > 0 else 0.03
    return 0.0


def get_net_position(symbol: str) -> int:
    data = scrape_cot_reports()
    for code, entry in data.items():
        if entry.get("symbol") == symbol:
            return entry.get("net", 0)
    return 0


def get_zscore(symbol: str) -> float:
    data = scrape_cot_reports()
    for code, entry in data.items():
        if entry.get("symbol") == symbol:
            return entry.get("zscore", 0.0)
    return 0.0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = scrape_cot_reports()
    for code, entry in sorted(result.items()):
        print(f"  {code}: net={entry.get('net',0):+d} z={entry.get('zscore',0):+.2f} "
              f"L={entry.get('long',0)} S={entry.get('short',0)} src={entry.get('source','?')}")
