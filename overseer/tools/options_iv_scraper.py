"""Options IV / Risk-Reversal Data Scraper for OVERSEER v12.

Fetches implied-volatility and 25-delta risk-reversal data for major
forex pairs.  Risk reversals are the key institutional directional-skew
indicator (Framework 11):

    RR25 = IV(25Δ Call) − IV(25Δ Put)

  • RR25 > 0 → market pricing upside → bullish institutional skew
  • RR25 < 0 → market pricing downside → bearish institutional skew
  • Extreme |RR25| → contrarian signal

Data sources (tried in order):
  1. Custom API endpoint (set IV_API_URL in .env — e.g. QuikStrike,
     OptionMetrics, or broker-provided REST endpoint)
  2. CBOE FX Options HTML scrape (best-effort, fragile)
  3. Garman-Klass realised-vol estimation (IV only, **NO** fake RR)
  4. Graceful empty-data fallback

IMPORTANT: Risk-reversal data is ONLY populated from real options-market
sources (API or CBOE).  The Garman-Klass fallback provides realised-vol
only — it does NOT fabricate a risk-reversal number.  The skew_score
will be 0 (neutral) when no real options data is available.

Configuration (via ``.env``):
    IV_API_URL        – REST endpoint returning JSON array of IV data
    IV_API_KEY        – Bearer token / API key (optional)
    IV_REFRESH_SECONDS – Refresh interval (default 6 h)

Run standalone::

    python tools/options_iv_scraper.py
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
from typing import Any, Optional

try:
    import requests
except ImportError as _exc:
    raise SystemExit("Missing dependency. Run:  pip install requests") from _exc

from tools.scraper_utils import fetch_with_retry, ScraperHealth, is_data_stale

LOGGER = logging.getLogger("overseer.options_iv_scraper")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_DIR = _PROJECT_ROOT / "database"
_IV_JSON = _CONFIG_DIR / "options_iv_latest.json"
_DB_PATH = _CONFIG_DIR / "overseer_trades.db"

_REFRESH_INTERVAL_SEC = int(os.getenv("IV_REFRESH_SECONDS", str(6 * 3600)))

_IV_API_URL = os.getenv("IV_API_URL", "")
_IV_API_KEY = os.getenv("IV_API_KEY", "")
_IV_API_METHOD = os.getenv("IV_API_METHOD", "GET").upper()
_IV_API_BODY_JSON = os.getenv("IV_API_BODY_JSON", "")
_IV_API_HEADERS_JSON = os.getenv("IV_API_HEADERS_JSON", "")
_IV_API_DATA_PATH = os.getenv("IV_API_DATA_PATH", "")
_IV_ENABLE_CBOE = os.getenv("IV_ENABLE_CBOE", "false").lower() == "true"
_FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

_CBOE_FX_URL = "https://www.cboe.com/fx/options/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
}

_SYMBOL_MAP: dict[str, str] = {
    "EURUSD": "EUR",
    "GBPUSD": "GBP",
    "USDJPY": "JPY",
    "AUDUSD": "AUD",
    "USDCAD": "CAD",
    "NZDUSD": "NZD",
    "USDCHF": "CHF",
}

_REVERSE_SYMBOL_MAP: dict[str, str] = {v: k for k, v in _SYMBOL_MAP.items()}

_EXTREME_RR_THRESHOLD = float(os.getenv("IV_EXTREME_RR_THRESHOLD", "1.5"))
_MODERATE_RR_THRESHOLD = float(os.getenv("IV_MODERATE_RR_THRESHOLD", "0.75"))

_TABLE_SCHEMA = """\
CREATE TABLE IF NOT EXISTS options_iv (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol           TEXT    NOT NULL,
    currency         TEXT    NOT NULL,
    atm_iv           REAL,
    rr_25d           REAL,
    rr_10d           REAL,
    butterfly_25d    REAL,
    iv_percentile_52w REAL,
    skew_score       INTEGER,
    source           TEXT    NOT NULL DEFAULT 'unknown',
    scraped_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, scraped_at)
);
"""

_CREATE_INDEX_SQL = """\
CREATE INDEX IF NOT EXISTS idx_options_iv_symbol
    ON options_iv(symbol, scraped_at DESC);
"""


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_TABLE_SCHEMA + _CREATE_INDEX_SQL)


def _rr_to_skew_score(rr_25d: float, percentile_52w: float | None = None) -> int:
    """Convert 25-delta risk reversal to a skew score (-2 to +2).

    Extreme skew is a contrarian signal:
      RR > +1.5  → score -2 (extreme bullish skew → contrarian bearish)
      RR > +0.75 → score -1
      RR < -1.5  → score +2 (extreme bearish skew → contrarian bullish)
      RR < -0.75 → score +1
      Otherwise  →  0
    """
    if rr_25d > _EXTREME_RR_THRESHOLD:
        return -2
    if rr_25d > _MODERATE_RR_THRESHOLD:
        return -1
    if rr_25d < -_EXTREME_RR_THRESHOLD:
        return 2
    if rr_25d < -_MODERATE_RR_THRESHOLD:
        return 1
    return 0


def _normalise_symbol(value: Any) -> str:
    symbol = str(value or "").upper().strip()
    symbol = symbol.replace("/", "").replace("-", "").replace("_", "")
    if symbol in _SYMBOL_MAP:
        return symbol
    if symbol in _REVERSE_SYMBOL_MAP:
        return _REVERSE_SYMBOL_MAP[symbol]
    return symbol


def _first_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lowered = {str(k).lower(): v for k, v in item.items()}
    for key in keys:
        if key in item:
            return item[key]
        value = lowered.get(key.lower())
        if value is not None:
            return value
    return None


def _as_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.replace("%", "").replace(",", "").strip()
        if not value:
            return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _data_at_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current


def _coerce_record_list(data: Any) -> list[dict[str, Any]]:
    """Return likely IV records from common REST response envelopes."""
    if _IV_API_DATA_PATH:
        data = _data_at_path(data, _IV_API_DATA_PATH)

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if not isinstance(data, dict):
        return []

    for key in ("data", "results", "items", "records", "rows", "values"):
        value = data.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = _coerce_record_list(value)
            if nested:
                return nested

    # Some APIs return {"EURUSD": {"atm_iv": ..., "rr_25d": ...}}.
    keyed_records: list[dict[str, Any]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            keyed_records.append({"symbol": key, **value})
    return keyed_records


def _parse_custom_record(item: dict[str, Any]) -> dict[str, Any] | None:
    symbol = _normalise_symbol(_first_value(item, (
        "symbol", "pair", "instrument", "ticker", "underlying", "currency_pair",
        "ccy_pair", "name",
    )))
    if symbol not in _SYMBOL_MAP:
        return None

    atm_iv = _as_optional_float(_first_value(item, (
        "atm_iv", "atmVol", "atm_vol", "atm", "iv", "implied_vol",
        "impliedVol", "implied_volatility", "volatility",
    )))
    rr_25d = _as_optional_float(_first_value(item, (
        "rr_25d", "rr25", "rr_25", "risk_reversal_25d", "riskReversal25D",
        "risk_reversal", "25d_rr", "delta25_rr",
    )))
    rr_10d = _as_optional_float(_first_value(item, (
        "rr_10d", "rr10", "rr_10", "risk_reversal_10d", "riskReversal10D",
        "10d_rr", "delta10_rr",
    )))
    butterfly_25d = _as_optional_float(_first_value(item, (
        "butterfly_25d", "bf_25d", "bf25", "fly_25d", "butterfly25D",
    )))
    percentile = _as_optional_float(_first_value(item, (
        "iv_percentile_52w", "iv_percentile", "percentile_52w",
        "ivRank", "iv_rank",
    )))

    if atm_iv is None and rr_25d is None and rr_10d is None and butterfly_25d is None:
        return None

    return {
        "symbol": symbol,
        "currency": _SYMBOL_MAP[symbol],
        "atm_iv": atm_iv,
        "rr_25d": rr_25d,
        "rr_10d": rr_10d,
        "butterfly_25d": butterfly_25d,
        "iv_percentile_52w": percentile,
        "source": "api",
    }


def _fetch_custom_api() -> list[dict[str, Any]]:
    """Fetch IV data from user-configured API endpoint.

    Expected JSON response: a list of dicts, or a common envelope such
    as {"data": [...]}, each with keys:
        symbol (str)       – e.g. "EURUSD"
        atm_iv (float)     – ATM implied volatility in percent
        rr_25d (float)     – 25-delta risk reversal in percent
        rr_10d (float|None) – 10-delta risk reversal (optional)
        butterfly_25d (float|None) – 25-delta butterfly (optional)
        iv_percentile_52w (float|None) – 52-week IV percentile (optional)

    Supports Bearer-token auth via IV_API_KEY. For POST APIs, set
    IV_API_METHOD=POST and IV_API_BODY_JSON to the request body.
    If records are nested, set IV_API_DATA_PATH, for example
    "data.records".
    """
    if not _IV_API_URL:
        return []

    LOGGER.info("Attempting custom IV API: %s", _IV_API_URL)
    try:
        headers = dict(_HEADERS)
        if _IV_API_KEY:
            headers["Authorization"] = f"Bearer {_IV_API_KEY}"
        if _IV_API_HEADERS_JSON:
            try:
                extra_headers = json.loads(_IV_API_HEADERS_JSON)
                if isinstance(extra_headers, dict):
                    headers.update({str(k): str(v) for k, v in extra_headers.items()})
            except json.JSONDecodeError as exc:
                LOGGER.warning("IV_API_HEADERS_JSON is invalid JSON: %s", exc)

        if _IV_API_METHOD == "POST":
            body: Any = None
            if _IV_API_BODY_JSON:
                try:
                    body = json.loads(_IV_API_BODY_JSON)
                except json.JSONDecodeError as exc:
                    LOGGER.warning("IV_API_BODY_JSON is invalid JSON: %s", exc)
                    return []
            resp = requests.post(_IV_API_URL, headers=headers, json=body, timeout=20)
        else:
            resp = requests.get(_IV_API_URL, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        LOGGER.warning("Custom IV API request failed: %s", exc)
        return []

    items = _coerce_record_list(data)
    if not items:
        LOGGER.warning("Custom IV API returned no parseable records: %s", type(data).__name__)
        return []

    results: list[dict[str, Any]] = []
    for item in items:
        parsed = _parse_custom_record(item)
        if parsed is not None:
            results.append(parsed)

    LOGGER.info("Custom API: parsed %d records", len(results))
    return results


def _fetch_cboe_data() -> list[dict[str, Any]]:
    """Attempt to fetch FX options data from CBOE."""
    LOGGER.info("Attempting CBOE FX options fetch ...")
    try:
        resp = requests.get(_CBOE_FX_URL, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        LOGGER.warning("CBOE FX options request failed: %s", exc)
        return []

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        LOGGER.warning("beautifulsoup4 not installed — CBOE scrape skipped")
        return []

    results: list[dict[str, Any]] = []
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue
                currency_name = cells[0].get_text(strip=True).upper()
                for currency, symbol in _REVERSE_SYMBOL_MAP.items():
                    if currency in currency_name:
                        try:
                            atm_iv = float(cells[1].get_text(strip=True).replace("%", ""))
                            rr_25d = float(cells[2].get_text(strip=True).replace("%", ""))
                            rr_10d_str = cells[3].get_text(strip=True).replace("%", "")
                            bf_25d_str = cells[4].get_text(strip=True).replace("%", "")
                            rr_10d = float(rr_10d_str) if rr_10d_str else None
                            bf_25d = float(bf_25d_str) if bf_25d_str else None
                            results.append({
                                "symbol": symbol,
                                "currency": currency,
                                "atm_iv": atm_iv,
                                "rr_25d": rr_25d,
                                "rr_10d": rr_10d,
                                "butterfly_25d": bf_25d,
                                "source": "cboe",
                            })
                        except (ValueError, IndexError):
                            continue
                        break
    except Exception as exc:
        LOGGER.warning("CBOE parse error: %s", exc)

    LOGGER.info("CBOE: parsed %d records", len(results))
    return results


def _fetch_finnhub_forex_vol() -> list[dict[str, Any]]:
    if not _FINNHUB_API_KEY:
        return []
    LOGGER.info("Attempting Finnhub forex volatility fetch ...")
    results: list[dict[str, Any]] = []
    for symbol, currency in _SYMBOL_MAP.items():
        try:
            url = f"https://finnhub.io/api/v1/forex/volatility?symbol={symbol}&token={_FINNHUB_API_KEY}"
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("atm_iv"):
                results.append({
                    "symbol": symbol,
                    "currency": currency,
                    "atm_iv": float(data["atm_iv"]),
                    "rr_25d": _as_optional_float(data.get("rr_25d")),
                    "rr_10d": _as_optional_float(data.get("rr_10d")),
                    "butterfly_25d": _as_optional_float(data.get("butterfly_25d")),
                    "source": "finnhub",
                })
        except Exception as exc:
            LOGGER.debug("Finnhub vol fetch failed for %s: %s", symbol, exc)
    LOGGER.info("Finnhub: parsed %d records", len(results))
    return results


def _candle_val(candle: Any, key: str) -> float:
    if isinstance(candle, dict):
        return float(candle.get(key, 0))
    return float(getattr(candle, key, 0))


def _estimate_realised_vol(symbol: str, candle_aggregator: Any = None) -> dict[str, Any] | None:
    if candle_aggregator is None:
        return None

    try:
        daily = candle_aggregator.snapshot(symbol).get("Daily", [])
        if len(daily) < 20:
            return None

        recent = daily[-20:]

        log_hl_sq_sum = 0.0
        log_co_sq_sum = 0.0
        for c in recent:
            h = _candle_val(c, "high")
            lo = _candle_val(c, "low")
            o = _candle_val(c, "open")
            cl = _candle_val(c, "close")
            if h <= 0 or lo <= 0 or o <= 0:
                continue
            log_hl = math.log(h / lo)
            log_co = math.log(cl / o)
            log_hl_sq_sum += log_hl ** 2
            log_co_sq_sum += log_co ** 2

        n = len(recent)
        if n == 0:
            return None

        garman_klass_var = (0.5 * log_hl_sq_sum - (2 * math.log(2) - 1) * log_co_sq_sum) / n
        if garman_klass_var <= 0:
            return None

        daily_vol = math.sqrt(garman_klass_var)
        annualised_rv = daily_vol * math.sqrt(252) * 100.0

        return {
            "symbol": symbol,
            "currency": _SYMBOL_MAP.get(symbol, symbol[:3]),
            "atm_iv": round(annualised_rv, 2),
            "rr_25d": None,
            "rr_10d": None,
            "butterfly_25d": None,
            "skew_score": 0,
            "source": "realised_vol",
        }
    except Exception as exc:
        LOGGER.warning("Realised-vol estimation failed for %s: %s", symbol, exc)
        return None


def _save_iv_data(records: list[dict[str, Any]]) -> None:
    """Persist IV records to SQLite and JSON."""
    if not records:
        return

    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure_table(conn)
            for rec in records:
                rr_25d = rec.get("rr_25d")
                pct_52w = rec.get("iv_percentile_52w")
                skew = rec.get("skew_score")
                if skew is None and rr_25d is not None:
                    skew = _rr_to_skew_score(float(rr_25d), pct_52w)
                elif skew is None:
                    skew = 0

                conn.execute(
                    """
                    INSERT OR REPLACE INTO options_iv
                        (symbol, currency, atm_iv, rr_25d, rr_10d,
                         butterfly_25d, iv_percentile_52w, skew_score, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec["symbol"],
                        rec.get("currency", ""),
                        rec.get("atm_iv"),
                        rr_25d,
                        rec.get("rr_10d"),
                        rec.get("butterfly_25d"),
                        pct_52w,
                        skew,
                        rec.get("source", "unknown"),
                    ),
                )
            conn.commit()
        LOGGER.info("Saved %d IV records to SQLite.", len(records))
    except Exception as exc:
        LOGGER.warning("Failed to save IV data to DB: %s", exc)

    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _IV_JSON.write_text(
            json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        LOGGER.info("Saved IV data to %s", _IV_JSON)
    except OSError as exc:
        LOGGER.warning("Failed to write IV JSON: %s", exc)


_last_refresh_time: float = 0.0
_has_real_options_data: bool = False
_iv_health = ScraperHealth("options_iv")


def get_iv_health() -> ScraperHealth:
    return _iv_health


def has_real_options_data() -> bool:
    """Return True if the last scrape produced real options-market data."""
    return _has_real_options_data


def scrape_options_iv(
    force: bool = False,
    candle_aggregator: Any = None,
) -> list[dict[str, Any]]:
    """Fetch the latest options IV / risk-reversal data.

    Tries sources in priority order:
      1. Custom API (IV_API_URL)
      2. CBOE scrape
      3. Garman-Klass realised-vol fallback (IV only, no RR)
    """
    global _last_refresh_time, _has_real_options_data

    now = time.time()
    if not force and (now - _last_refresh_time) < _REFRESH_INTERVAL_SEC:
        if _IV_JSON.exists():
            try:
                return json.loads(_IV_JSON.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    LOGGER.info("Starting options IV scrape (force=%s) ...", force)

    records: list[dict[str, Any]] = []
    _has_real_options_data = False

    records = fetch_with_retry(_fetch_custom_api, label="iv_api")
    if records:
        _has_real_options_data = True

    if not records and _IV_ENABLE_CBOE:
        records = fetch_with_retry(_fetch_cboe_data, label="iv_cboe")
        if records:
            _has_real_options_data = True

    if not records and _FINNHUB_API_KEY:
        records = fetch_with_retry(_fetch_finnhub_forex_vol, label="iv_finnhub")
        if records:
            _has_real_options_data = True

    if not records:
        LOGGER.warning(
            "No live options data available — using Garman-Klass realised-vol "
            "(ATM IV estimate only, NO risk-reversal data).  Set IV_API_URL "
            "in .env for real options-market data."
        )
        if candle_aggregator is not None:
            for symbol in _SYMBOL_MAP:
                est = _estimate_realised_vol(symbol, candle_aggregator)
                if est is not None:
                    records.append(est)

    if not records:
        _iv_health.record_failure()
        LOGGER.warning("All IV sources failed — returning empty list.")
        return []

    _iv_health.record_success(count=len(records))

    for rec in records:
        rr = rec.get("rr_25d")
        if rr is not None:
            rec["skew_score"] = rec.get("skew_score", _rr_to_skew_score(float(rr)))
        else:
            rec["skew_score"] = 0

    _save_iv_data(records)
    _last_refresh_time = time.time()
    return records


def get_skew_score(symbol: str) -> int:
    """Return the institutional skew score for *symbol* (-2 to +2).

    Returns 0 (neutral) when no real options data is available.
    """
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure_table(conn)
            row = conn.execute(
                """
                SELECT skew_score, source FROM options_iv
                WHERE symbol = ?
                ORDER BY scraped_at DESC
                LIMIT 1
                """,
                (symbol.upper(),),
            ).fetchone()
        if row is not None:
            source = row[1] or "unknown"
            if source == "realised_vol":
                return 0
            return int(row[0])
    except Exception as exc:
        LOGGER.warning("get_skew_score query failed: %s", exc)

    return 0


def get_rr_25d(symbol: str) -> float | None:
    """Return the latest 25-delta risk reversal for *symbol*.

    Returns None when only realised-vol data is available.
    """
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure_table(conn)
            row = conn.execute(
                """
                SELECT rr_25d, source FROM options_iv
                WHERE symbol = ?
                ORDER BY scraped_at DESC
                LIMIT 1
                """,
                (symbol.upper(),),
            ).fetchone()
        if row is not None:
            if row[1] == "realised_vol":
                return None
            return float(row[0]) if row[0] is not None else None
    except Exception as exc:
        LOGGER.warning("get_rr_25d query failed: %s", exc)
    return None


def get_atm_iv(symbol: str) -> float | None:
    """Return the latest ATM implied volatility for *symbol*."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure_table(conn)
            row = conn.execute(
                """
                SELECT atm_iv FROM options_iv
                WHERE symbol = ?
                ORDER BY scraped_at DESC
                LIMIT 1
                """,
                (symbol.upper(),),
            ).fetchone()
        if row is not None:
            return float(row[0])
    except Exception as exc:
        LOGGER.warning("get_atm_iv query failed: %s", exc)
    return None


def get_all_iv_data() -> dict[str, dict[str, Any]]:
    """Return the latest IV data for all tracked symbols."""
    result: dict[str, dict[str, Any]] = {}
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure_table(conn)
            for symbol in _SYMBOL_MAP:
                row = conn.execute(
                    """
                    SELECT symbol, currency, atm_iv, rr_25d, rr_10d,
                           butterfly_25d, iv_percentile_52w, skew_score,
                           source, scraped_at
                    FROM options_iv
                    WHERE symbol = ?
                    ORDER BY scraped_at DESC
                    LIMIT 1
                    """,
                    (symbol,),
                ).fetchone()
                if row:
                    result[symbol] = {
                        "symbol": row[0],
                        "currency": row[1],
                        "atm_iv": row[2],
                        "rr_25d": row[3],
                        "rr_10d": row[4],
                        "butterfly_25d": row[5],
                        "iv_percentile_52w": row[6],
                        "skew_score": row[7],
                        "source": row[8],
                        "scraped_at": row[9],
                    }
    except Exception as exc:
        LOGGER.warning("get_all_iv_data query failed: %s", exc)
    return result


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    print("=" * 60)
    print("OVERSEER — Options IV / Risk Reversal Scraper")
    print("=" * 60)

    records = scrape_options_iv(force=True)
    print(f"\nParsed IV records: {len(records)}")

    for rec in records:
        rr = rec.get("rr_25d")
        score = rec.get("skew_score", 0)
        label = {-2: "EXTREME CALL SKEW (bearish)", -1: "MOD CALL SKEW",
                 0: "NEUTRAL", 1: "MOD PUT SKEW",
                 2: "EXTREME PUT SKEW (bullish)"}.get(score, "?")
        source = rec.get("source", "unknown")
        rr_str = f"RR25={rr:+.2f}%" if rr is not None else "RR25=N/A"
        print(
            f"  {rec['symbol']:8s}  ATM_IV={rec.get('atm_iv', 0):6.2f}%  "
            f"{rr_str}  score={score:+d} ({label})  [{source}]"
        )

    print(f"\nHas real options data: {has_real_options_data()}")
    print("\nDone.")
