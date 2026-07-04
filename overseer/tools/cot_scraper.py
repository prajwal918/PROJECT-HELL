"""CFTC Commitments of Traders (COT) Data Scraper for OVERSEER v12.

Downloads weekly COT data for forex futures from the CFTC website,
extracts large-speculator (Non-Commercial) positioning, and calculates
contrarian sentiment scores.

Run standalone::

    python tools/cot_scraper.py
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError as _exc:  # pragma: no cover
    raise SystemExit("Missing dependency. Run:  pip install requests") from _exc

from tools.scraper_utils import fetch_with_retry, ScraperHealth, is_data_stale

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

LOGGER = logging.getLogger("overseer.cot_scraper")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_DIR = _PROJECT_ROOT / "config"
_COT_JSON = _CONFIG_DIR / "cot_latest.json"
_DB_PATH = _PROJECT_ROOT / "database" / "overseer_trades.db"

_REFRESH_INTERVAL_SEC = int(os.getenv("COT_REFRESH_SECONDS", str(12 * 3600)))

# CFTC data URLs (short-format futures-only report)
_CFTC_PRIMARY_URL = "https://www.cftc.gov/dea/newcot/deafut.txt"
_CFTC_FALLBACK_URL = "https://www.cftc.gov/dea/newcot/f_disagg.txt"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Mapping from our symbol codes to CFTC report search strings
_SYMBOL_SEARCH: dict[str, str] = {
    "6E": "EURO FX",
    "6B": "BRITISH POUND",
    "6J": "JAPANESE YEN",
    "6A": "AUSTRALIAN DOLLAR",
    "6C": "CANADIAN DOLLAR",
    "6N": "NEW ZEALAND DOLLAR",
    "GC": "GOLD",
}

# Reverse lookup for user convenience
_SPOT_TO_FUTURES: dict[str, str] = {
    "EURUSD": "6E",
    "GBPUSD": "6B",
    "USDJPY": "6J",
    "AUDUSD": "6A",
    "USDCAD": "6C",
    "NZDUSD": "6N",
    "XAUUSD": "GC",
}

# Percentile thresholds for extreme detection
_EXTREME_LONG_PCT = float(os.getenv("COT_EXTREME_LONG_PCT", "80"))
_EXTREME_SHORT_PCT = float(os.getenv("COT_EXTREME_SHORT_PCT", "20"))
_MODERATE_LONG_PCT = float(os.getenv("COT_MODERATE_LONG_PCT", "65"))
_MODERATE_SHORT_PCT = float(os.getenv("COT_MODERATE_SHORT_PCT", "35"))

# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

_TABLE_SCHEMA = """\
CREATE TABLE IF NOT EXISTS cot_positioning (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol           TEXT    NOT NULL,
    report_date      TEXT    NOT NULL,
    noncomm_long     INTEGER,
    noncomm_short    INTEGER,
    noncomm_net      INTEGER,
    open_interest    INTEGER,
    net_pct          REAL,
    percentile_52w   REAL,
    positioning_score INTEGER,
    scraped_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, report_date)
);
"""


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_TABLE_SCHEMA)


def _get_52w_range(conn: sqlite3.Connection, symbol: str) -> tuple[int, int]:
    """Return (min_net, max_net) for the last 52 records of *symbol*."""
    rows = conn.execute(
        """
        SELECT noncomm_net FROM cot_positioning
        WHERE symbol = ?
        ORDER BY report_date DESC
        LIMIT 52
        """,
        (symbol,),
    ).fetchall()
    if not rows:
        return (0, 0)
    nets = [r[0] for r in rows if r[0] is not None]
    if not nets:
        return (0, 0)
    return (min(nets), max(nets))


def _calc_percentile(current_net: int, min_net: int, max_net: int) -> float:
    """Percentile of current net within the 52-week min/max range (0-100)."""
    if max_net == min_net:
        return 50.0
    return ((current_net - min_net) / (max_net - min_net)) * 100.0


def _net_to_score(percentile: float) -> int:
    """Convert 52-week percentile to positioning score (-2 to +2).

    High percentile = large net long = bearish contrarian → negative score.
    Low percentile  = large net short = bullish contrarian → positive score.
    """
    if percentile >= _EXTREME_LONG_PCT:
        return -2  # extreme long → bearish contrarian
    if percentile >= _MODERATE_LONG_PCT:
        return -1  # moderately long
    if percentile <= _EXTREME_SHORT_PCT:
        return 2   # extreme short → bullish contrarian
    if percentile <= _MODERATE_SHORT_PCT:
        return 1   # moderately short
    return 0        # neutral


# ---------------------------------------------------------------------------
# Data download & parse
# ---------------------------------------------------------------------------

def _download_cot_data() -> str:
    """Download the raw COT text from CFTC. Returns raw CSV string."""
    for url in (_CFTC_PRIMARY_URL, _CFTC_FALLBACK_URL):
        try:
            LOGGER.info("Downloading COT data from %s …", url)
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            LOGGER.warning("COT download from %s failed: %s", url, exc)
    return ""


def _parse_cot_report(raw_text: str) -> list[dict[str, Any]]:
    """Parse the CFTC short-format futures report for target symbols.

    The deafut.txt file is comma-separated with these key columns
    (column indices may shift — we use header names):
      - Market_and_Exchange_Names
      - As_of_Date_In_Form_YYMMDD
      - NonComm_Positions_Long_All
      - NonComm_Positions_Short_All
      - Open_Interest_All
    """
    if not raw_text.strip():
        return []

    results: list[dict[str, Any]] = []

    try:
        reader = csv.DictReader(io.StringIO(raw_text))
        # Normalise header names (strip whitespace)
        if reader.fieldnames:
            reader.fieldnames = [f.strip() for f in reader.fieldnames]

        for row in reader:
            market_name = row.get("Market_and_Exchange_Names", "").strip().upper()

            for symbol, search_str in _SYMBOL_SEARCH.items():
                if search_str in market_name and "CHICAGO" in market_name:
                    try:
                        date_raw = row.get("As_of_Date_In_Form_YYMMDD", "").strip()
                        # Format YYMMDD → YYYY-MM-DD
                        if len(date_raw) == 6:
                            yr = int(date_raw[:2])
                            yr_full = 2000 + yr if yr < 80 else 1900 + yr
                            report_date = f"{yr_full}-{date_raw[2:4]}-{date_raw[4:6]}"
                        else:
                            report_date = date_raw

                        noncomm_long = int(row.get("NonComm_Positions_Long_All", "0").strip().replace(",", "") or 0)
                        noncomm_short = int(row.get("NonComm_Positions_Short_All", "0").strip().replace(",", "") or 0)
                        open_interest = int(row.get("Open_Interest_All", "0").strip().replace(",", "") or 0)
                        noncomm_net = noncomm_long - noncomm_short
                        net_pct = (noncomm_net / open_interest * 100.0) if open_interest > 0 else 0.0

                        results.append({
                            "symbol": symbol,
                            "report_date": report_date,
                            "noncomm_long": noncomm_long,
                            "noncomm_short": noncomm_short,
                            "noncomm_net": noncomm_net,
                            "open_interest": open_interest,
                            "net_pct": round(net_pct, 2),
                        })
                    except (ValueError, KeyError) as parse_exc:
                        LOGGER.debug("Parse error for %s row: %s", symbol, parse_exc)
                    break  # matched this row, move to next

    except Exception as exc:
        LOGGER.warning("COT CSV parse error: %s", exc)

    LOGGER.info("Parsed %d COT records", len(results))
    return results


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _save_cot_data(records: list[dict[str, Any]]) -> None:
    """Persist COT records to SQLite and JSON."""
    if not records:
        return

    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure_table(conn)

            for rec in records:
                # Calculate 52-week percentile
                min_net, max_net = _get_52w_range(conn, rec["symbol"])
                pct = _calc_percentile(rec["noncomm_net"], min_net, max_net)
                score = _net_to_score(pct)
                rec["percentile_52w"] = round(pct, 2)
                rec["positioning_score"] = score

                conn.execute(
                    """
                    INSERT OR REPLACE INTO cot_positioning
                        (symbol, report_date, noncomm_long, noncomm_short,
                         noncomm_net, open_interest, net_pct,
                         percentile_52w, positioning_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec["symbol"],
                        rec["report_date"],
                        rec["noncomm_long"],
                        rec["noncomm_short"],
                        rec["noncomm_net"],
                        rec["open_interest"],
                        rec["net_pct"],
                        rec["percentile_52w"],
                        rec["positioning_score"],
                    ),
                )
            conn.commit()
        LOGGER.info("Saved %d COT records to SQLite.", len(records))
    except Exception as exc:
        LOGGER.warning("Failed to save COT data to DB: %s", exc)

    # JSON output
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _COT_JSON.write_text(
            json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        LOGGER.info("Saved COT data to %s", _COT_JSON)
    except OSError as exc:
        LOGGER.warning("Failed to write COT JSON: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_last_refresh_time: float = 0.0
_cot_health = ScraperHealth("cot")


def get_cot_health() -> ScraperHealth:
    return _cot_health


def scrape_cot(force: bool = False) -> list[dict[str, Any]]:
    """Download & parse the latest COT report.

    Respects the auto-refresh interval (default 12 h) unless *force* is True.
    """
    global _last_refresh_time

    now = time.time()
    if not force and (now - _last_refresh_time) < _REFRESH_INTERVAL_SEC:
        if _COT_JSON.exists():
            try:
                return json.loads(_COT_JSON.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    raw = fetch_with_retry(_download_cot_data, label="cot_download")
    if not raw:
        _cot_health.record_failure()
        LOGGER.warning("COT data download failed — returning empty list.")
        return []

    records = _parse_cot_report(raw)
    if records:
        _save_cot_data(records)
        _cot_health.record_success(count=len(records))
    else:
        _cot_health.record_failure()
    _last_refresh_time = time.time()
    return records


def get_positioning_score(symbol: str) -> int:
    """Return the contrarian positioning score for *symbol* (-2 to +2).

    Accepts futures codes (``6E``) or spot codes (``EURUSD``).

    Returns:
        -2  extreme long  (bearish contrarian signal)
        -1  moderately long
         0  neutral
        +1  moderately short
        +2  extreme short (bullish contrarian signal)
    """
    # Normalise symbol
    sym = _SPOT_TO_FUTURES.get(symbol.upper(), symbol.upper())

    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure_table(conn)
            row = conn.execute(
                """
                SELECT positioning_score FROM cot_positioning
                WHERE symbol = ?
                ORDER BY report_date DESC
                LIMIT 1
                """,
                (sym,),
            ).fetchone()
        if row:
            return int(row[0])
    except Exception as exc:
        LOGGER.warning("get_positioning_score query failed: %s", exc)

    return 0  # neutral default


def get_all_scores() -> dict[str, dict[str, Any]]:
    """Return the latest positioning data for all tracked symbols."""
    result: dict[str, dict[str, Any]] = {}
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure_table(conn)
            for sym in _SYMBOL_SEARCH:
                row = conn.execute(
                    """
                    SELECT symbol, report_date, noncomm_net, net_pct,
                           percentile_52w, positioning_score
                    FROM cot_positioning
                    WHERE symbol = ?
                    ORDER BY report_date DESC
                    LIMIT 1
                    """,
                    (sym,),
                ).fetchone()
                if row:
                    result[sym] = {
                        "symbol": row[0],
                        "report_date": row[1],
                        "noncomm_net": row[2],
                        "net_pct": row[3],
                        "percentile_52w": row[4],
                        "positioning_score": row[5],
                    }
    except Exception as exc:
        LOGGER.warning("get_all_scores query failed: %s", exc)
    return result


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    print("=" * 60)
    print("OVERSEER — CFTC COT Data Scraper")
    print("=" * 60)

    records = scrape_cot(force=True)
    print(f"\nParsed COT records: {len(records)}")

    for rec in records:
        score = rec.get("positioning_score", 0)
        label = {-2: "EXTREME LONG ⬇", -1: "MOD LONG", 0: "NEUTRAL",
                 1: "MOD SHORT", 2: "EXTREME SHORT ⬆"}.get(score, "?")
        print(
            f"  {rec['symbol']:4s}  net={rec['noncomm_net']:+8d}  "
            f"pct={rec['net_pct']:+6.2f}%  52w={rec.get('percentile_52w', 0):.0f}%  "
            f"score={score:+d} ({label})"
        )

    print("\n--- Individual scores ---")
    for sym in _SYMBOL_SEARCH:
        print(f"  {sym}: {get_positioning_score(sym):+d}")

    print("\nDone.")
