"""Backfill DXY into signal_log from tick_log prices.

Computes synthetic DXY at each signal's timestamp using the nearest
tick prices for EURUSD, USDJPY, GBPUSD, USDCAD, USDCHF from tick_log.
"""
import math
import sqlite3
import sys
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
LOGGER = logging.getLogger("backfill_dxy")

DB_PATH = "/home/jogi999/Music/dfg/urlr/database/overseer_trades.db"

_DXY_CONSTANT = 50.14348112
_WEIGHTS = {
    "EURUSD": -0.576 / 0.958,
    "USDJPY": 0.136 / 0.958,
    "GBPUSD": -0.119 / 0.958,
    "USDCAD": 0.091 / 0.958,
    "USDCHF": 0.036 / 0.958,
}
_MIN_REQUIRED = {"EURUSD", "USDJPY", "GBPUSD"}

_SPOT_MAP = {
    "6EM6": "EURUSD",
    "6BM6": "GBPUSD",
    "6JM6": "USDJPY",
    "6CM6": "USDCAD",
    "6SM6": "USDCHF",
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "USDCAD": "USDCAD",
    "USDCHF": "USDCHF",
}

_INVERTED_FUTURES = {"6JM6", "6CM6"}

_SPOT_INVERTED = {"USDJPY", "USDCAD"}


def _compute_dxy(prices):
    if not _MIN_REQUIRED.issubset(prices):
        return None
    try:
        log_sum = 0.0
        for pair, weight in _WEIGHTS.items():
            p = prices.get(pair)
            if p is None or p <= 0:
                if pair in _MIN_REQUIRED:
                    return None
                continue
            log_sum += weight * math.log(p)
        return round(_DXY_CONSTANT * math.exp(log_sum), 4)
    except (ValueError, OverflowError):
        return None


def _infer_session(ts_str):
    try:
        hour = int(ts_str[11:13])
        if 0 <= hour < 7:
            return "asian"
        elif 7 <= hour < 8:
            return "asian_london_overlap"
        elif 8 <= hour < 13:
            return "london"
        elif 13 <= hour < 16:
            return "london_ny_overlap"
        elif 16 <= hour < 21:
            return "ny"
        else:
            return "asian"
    except (ValueError, IndexError):
        return ""


def _ts_to_epoch_ms(ts_str):
    from datetime import datetime, timezone
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (ValueError, OSError):
        return 0


def main():
    from datetime import datetime, timezone

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")

    signals = conn.execute(
        "SELECT id, symbol, tick_bid, tick_ask, timestamp "
        "FROM signal_log WHERE dxy = 0 OR dxy IS NULL "
        "ORDER BY timestamp ASC"
    ).fetchall()
    LOGGER.info("Signals with dxy=0: %d", len(signals))

    if not signals:
        LOGGER.info("Nothing to backfill")
        conn.close()
        return

    min_ts_ms = _ts_to_epoch_ms(signals[0][4])
    max_ts_ms = _ts_to_epoch_ms(signals[-1][4])
    LOGGER.info("Time range: %s -> %s (epoch ms: %d -> %d)", signals[0][4], signals[-1][4], min_ts_ms, max_ts_ms)

    ticks = conn.execute(
        "SELECT symbol, bid, ask, timestamp FROM tick_log "
        "WHERE timestamp >= ? AND timestamp <= ? "
        "ORDER BY timestamp ASC",
        (min_ts_ms, max_ts_ms),
    ).fetchall()
    LOGGER.info("Loaded %d ticks for DXY reconstruction", len(ticks))

    pair_prices = {}
    tick_idx = 0
    updated = 0
    dxy_success = 0
    session_fixed = 0
    spread_fixed = 0

    for sig_id, sig_sym, tick_bid, tick_ask, sig_ts in signals:
        sig_ts_ms = _ts_to_epoch_ms(sig_ts)

        while tick_idx < len(ticks) and ticks[tick_idx][3] <= sig_ts_ms:
            sym, bid, ask, _ = ticks[tick_idx]
            tick_idx += 1
            spot = _SPOT_MAP.get(sym)
            if spot is None:
                continue
            mid = (bid + ask) / 2.0 if bid and ask else bid or ask
            if not mid or mid <= 0:
                continue
            if sym in _INVERTED_FUTURES and mid > 0 and mid < 1:
                mid = 1.0 / mid
            pair_prices[spot] = mid

        dxy = _compute_dxy(pair_prices)
        if dxy and dxy > 0:
            dxy_success += 1
        else:
            dxy = 0.0

        set_parts = ["dxy = ?"]
        set_vals = [dxy]

        cur_session = conn.execute(
            "SELECT session FROM signal_log WHERE id = ?", (sig_id,)
        ).fetchone()[0]
        if not cur_session:
            session = _infer_session(sig_ts)
            set_parts.append("session = ?")
            set_vals.append(session)
            session_fixed += 1

        cur_spread = conn.execute(
            "SELECT spread_bps FROM signal_log WHERE id = ?", (sig_id,)
        ).fetchone()[0]
        if not cur_spread or cur_spread == 0:
            if tick_bid and tick_ask and tick_bid > 0:
                spread = round(abs(tick_ask - tick_bid) / tick_bid * 10000, 2)
                set_parts.append("spread_bps = ?")
                set_vals.append(spread)
                spread_fixed += 1

        set_vals.append(sig_id)
        conn.execute(
            "UPDATE signal_log SET {} WHERE id = ?".format(", ".join(set_parts)),
            set_vals,
        )
        updated += 1

        if updated % 2000 == 0:
            conn.commit()
            LOGGER.info(
                "Progress: %d/%d DXY=%.4f dxy_ok=%d pairs=%s",
                updated, len(signals), dxy,
                dxy_success,
                {k: round(v, 5) for k, v in pair_prices.items()},
            )

    conn.commit()
    LOGGER.info(
        "Done: %d updated, %d DXY populated, %d session fixed, %d spread fixed",
        updated, dxy_success, session_fixed, spread_fixed,
    )

    verify = conn.execute(
        "SELECT COUNT(*) FROM signal_log WHERE dxy > 0"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM signal_log").fetchone()[0]
    LOGGER.info("DXY coverage: %d/%d (%.1f%%)", verify, total, 100 * verify / max(1, total))

    conn.close()


if __name__ == "__main__":
    main()
