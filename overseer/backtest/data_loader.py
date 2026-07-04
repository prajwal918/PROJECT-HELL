"""Backtest data loader for OVERSEER v12.

Supports multiple forex data formats:
- Dukascopy tick CSV: timestamp(ms),askPrice,bidPrice  (header row)
- HistData.com M1 CSV: YYYYMMDD HHMMSS;O;H;L;C;V  (semicolon, no header)
- Generic tick CSV: any format with column mapping via header auto-detection

Also supports CME futures data (Rithmic recorded CSV):
- timestamp, symbol, bid, ask, bid_size, ask_size, delta, dom_json
"""

from __future__ import annotations

import csv
import gzip
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("overseer.backtest.data_loader")

DATA_DIR = Path(__file__).resolve().parent / "data"
SPOT_DIR = DATA_DIR / "spot"
FUTURES_DIR = DATA_DIR / "futures"


def _detect_format(first_line: str, delimiter: str) -> str:
    """Auto-detect CSV format from first line of file."""
    fields = first_line.split(delimiter)
    stripped = [f.strip().lower().replace('"', '') for f in fields]

    if stripped[0] == "timestamp" and any("ask" in s for s in stripped):
        return "dukascopy_tick"

    if any(s in stripped for s in ("open", "high", "low", "close")):
        return "histdata_m1_header"

    if len(stripped) == 6 and delimiter == ";":
        try:
            datetime.strptime(fields[0].strip(), "%Y%m%d %H%M%S")
            return "histdata_m1"
        except ValueError:
            pass

    if "bid" in stripped and "ask" in stripped:
        return "generic_tick"

    if len(stripped) >= 2:
        try:
            float(stripped[0])
            return "dukascopy_tick_noheader"
        except ValueError:
            pass

    return "unknown"


def _parse_ts_to_ms(ts_str: str) -> int:
    """Parse various timestamp formats and return ms epoch integer."""
    ts_str = ts_str.strip()

    try:
        val = int(ts_str)
        if val > 1e12:
            return val
        if val > 1e9:
            return val * 1000
    except ValueError:
        pass

    formats = [
        "%Y%m%d %H%M%S%f",
        "%Y%m%d %H%M%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S.%f",
        "%Y.%m.%d %H:%M:%S",
        "%d.%m.%Y %H:%M:%S.%f",
        "%d.%m.%Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue

    return 0


def _syth_bid_ask_from_ohlc(
    price: float, spread_pips: float = 1.5, pip_size: float = 0.0001,
) -> tuple[float, float]:
    """Synthesize bid/ask from a price using mid + half spread."""
    half_spread = spread_pips * pip_size / 2.0
    return round(price - half_spread, 6), round(price + half_spread, 6)


def _infer_pip_size(symbol: str) -> float:
    sym = symbol.upper()
    if "JPY" in sym:
        return 0.01
    if sym.startswith("XAU") or sym == "GOLD":
        return 0.1
    return 0.0001


def load_spot_data(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    spread_pips: float | None = None,
    max_ticks: int | None = None,
) -> list[dict[str, Any]]:
    """Load spot forex data from CSV files in backtest/data/spot/.

    Parameters
    ----------
    symbol : str
        e.g. "EURUSD" — will match files like EURUSD_*.csv, eurusd-*.csv, DAT_ASCII_EURUSD_*.csv
    start_date, end_date : str | None
        Optional ISO date filters (inclusive).
    spread_pips : float | None
        Override spread for M1 bar → tick conversion. Auto-detected if None.
    max_ticks : int | None
        Cap on total ticks loaded (useful for quick tests with large files).

    Returns
    -------
    list[dict]
        Normalised tick dicts: {symbol, bid, ask, bid_size, ask_size, timestamp(ms epoch), ...}
    """
    ticks: list[dict[str, Any]] = []
    pip_size = _infer_pip_size(symbol)
    default_spread = spread_pips or 1.5

    if not SPOT_DIR.exists():
        LOGGER.error("Spot data directory not found: %s", SPOT_DIR)
        return ticks

    patterns = [
        f"{symbol.upper()}*",
        f"{symbol.lower()}*",
        f"DAT_ASCII_{symbol.upper()}*",
    ]
    files: list[Path] = []
    for pat in patterns:
        files.extend(sorted(SPOT_DIR.glob(pat)))
    files = sorted(set(files))

    if not files:
        LOGGER.warning("No data files found for %s in %s", symbol, SPOT_DIR)
        return ticks

    for filepath in files:
        LOGGER.info("Loading %s ...", filepath.name)
        file_ticks = _load_csv_file(filepath, symbol, pip_size, default_spread)
        ticks.extend(file_ticks)
        if max_ticks and len(ticks) >= max_ticks:
            ticks = ticks[:max_ticks]
            break

    ticks.sort(key=lambda t: t["timestamp"])

    if start_date:
        start_ms = _parse_ts_to_ms(start_date)
        ticks = [t for t in ticks if t["timestamp"] >= start_ms]
    if end_date:
        end_ms = _parse_ts_to_ms(end_date)
        ticks = [t for t in ticks if t["timestamp"] <= end_ms]

    LOGGER.info("Loaded %d ticks for %s", len(ticks), symbol)
    return ticks


def _detect_delimiter(first_line: str) -> str:
    """Detect delimiter from first line of file."""
    if ";" in first_line:
        return ";"
    if "\t" in first_line:
        return "\t"
    return ","


def _load_csv_file(
    filepath: Path, symbol: str, pip_size: float, default_spread: float,
) -> list[dict[str, Any]]:
    """Load a single CSV file, auto-detecting format and delimiter."""
    opener = gzip.open if filepath.suffix == ".gz" else open
    ticks: list[dict[str, Any]] = []

    with opener(filepath, "rt", encoding="utf-8", errors="replace") as f:
        first_line = f.readline()
        if not first_line:
            return ticks

        delimiter = _detect_delimiter(first_line)
        fmt = _detect_format(first_line, delimiter)

        if fmt == "dukascopy_tick":
            header = first_line.strip().split(delimiter)
            col_map = {c.strip().lower().replace('"', ''): i for i, c in enumerate(header)}
            reader = csv.reader(f, delimiter=delimiter)
            ticks = _parse_dukascopy(reader, col_map, symbol)

        elif fmt == "dukascopy_tick_noheader":
            reader = csv.reader(f, delimiter=delimiter)
            ticks = _parse_dukascopy_noheader(first_line, reader, symbol)

        elif fmt == "histdata_m1":
            ticks = _parse_histdata_m1_raw(first_line, f, symbol, pip_size, default_spread)

        elif fmt == "histdata_m1_header":
            header = first_line.strip().split(delimiter)
            col_map = {c.strip().lower().replace('"', ''): i for i, c in enumerate(header)}
            reader = csv.reader(f, delimiter=delimiter)
            ticks = _parse_histdata_m1(reader, col_map, symbol, pip_size, default_spread)

        elif fmt == "generic_tick":
            header = first_line.strip().split(delimiter)
            col_map = {c.strip().lower().replace('"', ''): i for i, c in enumerate(header)}
            reader = csv.reader(f, delimiter=delimiter)
            ticks = _parse_generic_tick(reader, col_map, symbol)

        else:
            LOGGER.error("Unknown CSV format in %s — first line: %s", filepath.name, first_line[:200])

    LOGGER.info("Loaded %d ticks from %s (format=%s)", len(ticks), filepath.name, fmt)
    return ticks


def _parse_dukascopy(
    reader: csv.reader, col_map: dict[str, int], symbol: str,
) -> list[dict[str, Any]]:
    """Parse Dukascopy tick CSV: timestamp(ms),askPrice,bidPrice"""
    ticks: list[dict[str, Any]] = []
    ts_idx = _find_col(col_map, ["timestamp", "time"])
    ask_idx = _find_col(col_map, ["askprice", "ask_price", "ask"])
    bid_idx = _find_col(col_map, ["bidprice", "bid_price", "bid"])
    bsize_idx = _find_col(col_map, ["bid_size", "bidsize", "bid volume", "bidvolume"])
    asize_idx = _find_col(col_map, ["ask_size", "asksize", "ask volume", "askvolume"])

    for row in reader:
        try:
            ts_raw = row[ts_idx].strip() if ts_idx < len(row) else ""
            ts_ms = _parse_ts_to_ms(ts_raw)
            bid = float(row[bid_idx]) if bid_idx < len(row) else 0.0
            ask = float(row[ask_idx]) if ask_idx < len(row) else 0.0
            if bid <= 0 or ask <= 0:
                continue
            bsize = float(row[bsize_idx]) if bsize_idx < len(row) and _has_col(col_map, "bid_size", "bidsize") else 0.0
            asize = float(row[asize_idx]) if asize_idx < len(row) and _has_col(col_map, "ask_size", "asksize") else 0.0
            ticks.append({
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "bid_size": bsize,
                "ask_size": asize,
                "timestamp": ts_ms,
                "delta": 0.0,
                "dom": {},
            })
        except (ValueError, IndexError):
            continue
    return ticks


def _parse_dukascopy_noheader(
    first_line: str, reader: csv.reader, symbol: str,
) -> list[dict[str, Any]]:
    """Parse Dukascopy-style tick CSV without header (ts_ms, ask, bid)."""
    ticks: list[dict[str, Any]] = []
    all_rows = [first_line.strip().split(",")] + list(reader)
    for row in all_rows:
        if len(row) < 3:
            continue
        try:
            ts_ms = _parse_ts_to_ms(row[0].strip())
            ask = float(row[1].strip())
            bid = float(row[2].strip())
            if bid <= 0 or ask <= 0:
                continue
            ticks.append({
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "bid_size": 0.0,
                "ask_size": 0.0,
                "timestamp": ts_ms,
                "delta": 0.0,
                "dom": {},
            })
        except (ValueError, IndexError):
            continue
    return ticks


def _parse_histdata_m1_raw(
    first_line: str, f, symbol: str, pip_size: float, spread_pips: float,
) -> list[dict[str, Any]]:
    """Parse HistData M1 format: YYYYMMDD HHMMSS;O;H;L;C;V (semicolon, no header)."""
    ticks: list[dict[str, Any]] = []

    def _parse_line(line: str) -> list[str]:
        return line.strip().split(";")

    all_lines = [first_line] + f.readlines()
    for line in all_lines:
        parts = _parse_line(line)
        if len(parts) < 6:
            continue
        try:
            ts_ms = _parse_ts_to_ms(parts[0].strip())
            o = float(parts[1].strip())
            h = float(parts[2].strip())
            l = float(parts[3].strip())
            c = float(parts[4].strip())
            vol = float(parts[5].strip())
            if o <= 0 or c <= 0:
                continue

            bar_points = [
                (0, o, 5),
                (15, h, 8),
                (30, l, 8),
                (45, c, 5),
            ]
            for offset_sec, price, size in bar_points:
                bid, ask = _syth_bid_ask_from_ohlc(price, spread_pips, pip_size)
                ticks.append({
                    "symbol": symbol,
                    "bid": bid,
                    "ask": ask,
                    "bid_size": float(size),
                    "ask_size": float(size),
                    "timestamp": ts_ms + offset_sec * 1000,
                    "delta": 0.0,
                    "dom": {},
                    "bar_open": o,
                    "bar_high": h,
                    "bar_low": l,
                    "bar_close": c,
                    "bar_volume": vol,
                })
        except (ValueError, IndexError):
            continue
    return ticks


def _parse_histdata_m1(
    reader: csv.reader, col_map: dict[str, int], symbol: str,
    pip_size: float, spread_pips: float,
) -> list[dict[str, Any]]:
    """Parse M1 OHLC bars with header into 4 synthetic ticks."""
    ticks: list[dict[str, Any]] = []
    ts_idx = _find_col(col_map, ["timestamp", "time", "date", "datetime"])
    open_idx = _find_col(col_map, ["open"])
    high_idx = _find_col(col_map, ["high"])
    low_idx = _find_col(col_map, ["low"])
    close_idx = _find_col(col_map, ["close"])
    vol_idx = _find_col(col_map, ["volume", "vol", "tick_volume"])

    for row in reader:
        try:
            ts_ms = _parse_ts_to_ms(row[ts_idx].strip()) if ts_idx < len(row) else 0
            o = float(row[open_idx]) if open_idx < len(row) else 0.0
            h = float(row[high_idx]) if high_idx < len(row) else 0.0
            l = float(row[low_idx]) if low_idx < len(row) else 0.0
            c = float(row[close_idx]) if close_idx < len(row) else 0.0
            vol = float(row[vol_idx]) if vol_idx is not None and vol_idx < len(row) else 0.0
            if o <= 0 or c <= 0:
                continue

            bar_points = [(0, o, 5), (15, h, 8), (30, l, 8), (45, c, 5)]
            for offset_sec, price, size in bar_points:
                bid, ask = _syth_bid_ask_from_ohlc(price, spread_pips, pip_size)
                ticks.append({
                    "symbol": symbol,
                    "bid": bid,
                    "ask": ask,
                    "bid_size": float(size),
                    "ask_size": float(size),
                    "timestamp": ts_ms + offset_sec * 1000,
                    "delta": 0.0,
                    "dom": {},
                    "bar_open": o,
                    "bar_high": h,
                    "bar_low": l,
                    "bar_close": c,
                    "bar_volume": vol,
                })
        except (ValueError, IndexError):
            continue
    return ticks


def _parse_generic_tick(
    reader: csv.reader, col_map: dict[str, int], symbol: str,
) -> list[dict[str, Any]]:  # noqa: C901
    ticks: list[dict[str, Any]] = []
    ts_idx = _find_col(col_map, ["timestamp", "time", "date", "datetime"])
    bid_idx = _find_col(col_map, ["bid", "bidprice", "bid_price"])
    ask_idx = _find_col(col_map, ["ask", "askprice", "ask_price"])
    delta_idx = _find_col(col_map, ["delta", "order_flow_delta"])
    has_delta = _has_col(col_map, "delta", "order_flow_delta")

    for row in reader:
        try:
            ts_ms = _parse_ts_to_ms(row[ts_idx].strip()) if ts_idx < len(row) else 0
            bid = float(row[bid_idx]) if bid_idx < len(row) else 0.0
            ask = float(row[ask_idx]) if ask_idx < len(row) else 0.0
            delta = 0.0
            if has_delta and delta_idx < len(row):
                try:
                    delta = float(row[delta_idx])
                except ValueError:
                    delta = 0.0
            if bid <= 0 or ask <= 0:
                continue
            ticks.append({
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "bid_size": 0.0,
                "ask_size": 0.0,
                "timestamp": ts_ms,
                "delta": delta,
                "dom": {},
            })
        except (ValueError, IndexError):
            continue
    return ticks


def _find_col(col_map: dict[str, int], candidates: list[str]) -> int:
    """Find first matching column index from candidates."""
    for c in candidates:
        if c in col_map:
            return col_map[c]
    return 0


def _has_col(col_map: dict[str, int], *candidates: str) -> bool:
    """Check if any candidate column exists."""
    return any(c in col_map for c in candidates)


def load_futures_data(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Load CME futures tick data from backtest/data/futures/."""
    ticks: list[dict[str, Any]] = []

    if not FUTURES_DIR.exists():
        LOGGER.warning("Futures data directory not found: %s", FUTURES_DIR)
        return ticks

    files = sorted(FUTURES_DIR.glob(f"{symbol.upper()}*.*"))
    if not files:
        files = sorted(FUTURES_DIR.glob(f"{symbol.lower()}*.*"))

    for filepath in files:
        file_ticks = _load_csv_file(filepath, symbol, _infer_pip_size(symbol), 1.5)
        ticks.extend(file_ticks)

    ticks.sort(key=lambda t: t["timestamp"])
    if start_date:
        start_ms = _parse_ts_to_ms(start_date)
        ticks = [t for t in ticks if t["timestamp"] >= start_ms]
    if end_date:
        end_ms = _parse_ts_to_ms(end_date)
        ticks = [t for t in ticks if t["timestamp"] <= end_ms]

    LOGGER.info("Loaded %d futures ticks for %s", len(ticks), symbol)
    return ticks


def generate_sample_data(
    symbol: str = "EURUSD",
    num_ticks: int = 5000,
    base_price: float = 1.0850,
    volatility: float = 0.0003,
    spread_pips: float = 1.2,
) -> list[dict[str, Any]]:
    """Generate synthetic tick data for testing the backtest framework.

    Useful when no real data is available yet — lets you verify the
    entire pipeline works end-to-end.
    """
    import random

    pip_size = _infer_pip_size(symbol)
    half_spread = spread_pips * pip_size / 2.0
    base_ts = int(datetime(2025, 1, 6, 8, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    ticks: list[dict[str, Any]] = []
    price = base_price

    for i in range(num_ticks):
        price += random.gauss(0, volatility)
        price = max(base_price * 0.95, min(base_price * 1.05, price))
        bid = round(price - half_spread, 6)
        ask = round(price + half_spread, 6)

        bid_size = random.uniform(1.0, 10.0)
        ask_size = random.uniform(1.0, 10.0)
        direction = "BUY" if ask_size > bid_size else "SELL"
        ts_ms = base_ts + i * 1000

        ticks.append({
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "timestamp": ts_ms,
            "delta": random.uniform(-50, 50),
            "dom": {},
            "direction": direction,
        })

    LOGGER.info("Generated %d synthetic ticks for %s", num_ticks, symbol)
    return ticks
