#!/usr/bin/env python3
"""
OVERSEER Binary Signal Engine v1.0
Standalone. Reads existing overseer_trades.db. Returns UP/DOWN signals with probabilities.
Never writes, never locks, never modifies main.py.
"""

import json
import logging
import math
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "database", "overseer_trades.db")

LOGGER = logging.getLogger("overseer.binary_signals")

_SYMBOLS = ["6EM6", "6BM6", "6JM6", "6AM6", "6CM6", "GC"]

_PIP_MAP = {
    "6EM6": 0.0001, "6BM6": 0.0001, "6AM6": 0.0001, "6CM6": 0.0001,
    "6JM6": 0.01, "GC": 0.1,
}

_REGIME_ALLOW = {
    "6EM6": {"BUY": [2, 3, 4, 5, 6, 7], "SELL": [2, 3, 4, 5, 6, 7]},
    "6BM6": {"BUY": [2, 3, 4, 5, 6, 7], "SELL": [2, 3, 4, 5, 6, 7]},
    "6JM6": {"BUY": [1, 2, 3, 4, 5, 6, 7], "SELL": [1, 2, 3, 4, 5, 6, 7]},
    "6AM6": {"BUY": [2, 3, 4, 5, 6, 7], "SELL": [2, 3, 4, 5, 6, 7]},
    "6CM6": {"BUY": [2, 3, 4, 5, 6, 7], "SELL": [2, 3, 4, 5, 6, 7]},
    "GC": {"BUY": [3, 4, 5, 6], "SELL": [3, 4, 5, 6]},
}

_MIN_WR = 0.70
_MIN_NONFLAT = 30
_wr_cache: Dict[str, Any] = {}
_wr_cache_ts: float = 0.0
_WR_CACHE_TTL = 300.0

_BUY_PRIO = {"6BM6": 1, "6EM6": 2, "GC": 3, "6AM6": 4, "6CM6": 5, "6JM6": 6}
_REGIME_PRIO = {5: 1, 6: 2, 3: 3, 7: 4, 4: 5, 2: 6, 1: 7, 8: 8, 9: 9}

_COOLDOWN_SEC = 30
_MAX_ACTIVE = 6
_last_signal_time: Dict[str, float] = {}
_last_telegram_time: float = 0.0


def get_regime() -> tuple:
    now = datetime.now(timezone.utc)
    h = now.hour
    m = now.minute
    wd = now.weekday()
    if 0 <= h < 2:
        return 1, 0.85, "Asian Range", False
    if 2 <= h < 3:
        return 2, 1.15, "Asian Breakout", True
    if 3 <= h < 5:
        return 3, 1.20, "London Open", True
    if 5 <= h < 8:
        return 4, 1.05, "London Morning", True
    if 8 <= h < 13:
        return 5, 1.25, "LN-NY Overlap", True
    if 13 <= h < 15:
        return 6, 1.20, "NY Open", True
    if h == 15 or (h == 15 and m < 30):
        return 7, 0.95, "NY Afternoon", True
    if 15 <= h < 17:
        return 7, 0.95, "NY Afternoon", True
    if 17 <= h < 21:
        return 8, 0.80, "Post-London", False
    return 9, 0.75, "NY Close", False


def _is_blocked_today() -> tuple:
    now = datetime.now(timezone.utc)
    if now.weekday() == 4 and now.hour >= 17:
        return True, "FRIDAY_EVENING"
    return False, ""


def _compute_spread_bps(bid: float, ask: float, symbol: str) -> float:
    if bid <= 0:
        return 99.0
    return (ask - bid) / bid * 10000.0


def _get_db() -> Optional[sqlite3.Connection]:
    try:
        conn = sqlite3.connect(DB_PATH, timeout=3)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def _latest_tick(conn: sqlite3.Connection, symbol: str) -> Optional[dict]:
    try:
        row = conn.execute(
            "SELECT bid, ask, delta, dom_json, timestamp FROM tick_log "
            "WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if not row:
            return None
        bid = row["bid"] or 0
        ask = row["ask"] or 0
        delta = row["delta"] or 0
        ts = row["timestamp"]
        dom = None
        if row["dom_json"]:
            try:
                dom = json.loads(row["dom_json"])
            except Exception:
                pass
        spread_bps = _compute_spread_bps(bid, ask, symbol)
        return {
            "bid": bid, "ask": ask, "mid": (bid + ask) / 2,
            "delta": delta, "spread_bps": spread_bps,
            "dom": dom, "timestamp": ts,
        }
    except Exception:
        return None


def _latest_candle(conn: sqlite3.Connection, symbol: str) -> Optional[dict]:
    try:
        row = conn.execute(
            "SELECT open, high, low, close, volume, tick_count, open_time "
            "FROM candle_history WHERE symbol=? AND timeframe='1m' "
            "ORDER BY id DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if not row:
            return None
        return {
            "open": row["open"], "high": row["high"], "low": row["low"],
            "close": row["close"], "volume": row["volume"] or 0,
            "tick_count": row["tick_count"] or 0, "open_time": row["open_time"],
        }
    except Exception:
        return None


def _avg_volume(conn: sqlite3.Connection, symbol: str, n: int = 20) -> float:
    try:
        row = conn.execute(
            f"SELECT AVG(volume) as avg_vol FROM ("
            f"SELECT volume FROM candle_history WHERE symbol=? AND timeframe='1m' "
            f"ORDER BY id DESC LIMIT {n})",
            (symbol,),
        ).fetchone()
        return row["avg_vol"] if row and row["avg_vol"] else 0
    except Exception:
        return 0.0


def _tick_freshness(timestamp) -> float:
    if timestamp is None:
        return 9999.0
    try:
        if isinstance(timestamp, (int, float)):
            tick_time = timestamp / 1000.0 if timestamp > 1e12 else timestamp
            return time.time() - tick_time
        ts_str = str(timestamp)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z:+00:00"):
            try:
                dt = datetime.strptime(ts_str[:26], fmt).replace(tzinfo=timezone.utc)
                return (datetime.now(timezone.utc) - dt).total_seconds()
            except ValueError:
                continue
        return 9999.0
    except Exception:
        return 9999.0


def _extract_dom_metrics(dom: Optional[dict]) -> dict:
    if not dom:
        return {"bid_size": 0, "ask_size": 0, "bid_depth": 0, "ask_depth": 0, "obi": 0}
    bids = dom.get("bids", [])
    asks = dom.get("asks", [])
    bid_total = sum(float(b.get("size", 0)) for b in bids[:5])
    ask_total = sum(float(a.get("size", 0)) for a in asks[:5])
    total = bid_total + ask_total
    obi = (bid_total - ask_total) / total if total > 0 else 0
    return {
        "bid_size": bid_total, "ask_size": ask_total,
        "bid_depth": len(bids), "ask_depth": len(asks), "obi": obi,
    }


def _get_live_perms() -> dict:
    global _wr_cache, _wr_cache_ts
    now = time.time()
    if _wr_cache and (now - _wr_cache_ts) < _WR_CACHE_TTL:
        return _wr_cache
    perms = {}
    for sym in _SYMBOLS:
        perms[sym] = {}
        for d in ["BUY", "SELL"]:
            perms[sym][d] = {"allowed": False, "wr": 0.0, "n": 0, "reason": ""}
    try:
        conn = _get_db()
        if not conn:
            _wr_cache = perms
            _wr_cache_ts = now
            return perms
        try:
            rows = conn.execute("""
                SELECT symbol, direction,
                       COUNT(*) as n,
                       SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as losses
                FROM signal_log
                WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
                  AND score >= 0.80
                GROUP BY symbol, direction
            """).fetchall()
            for row in rows:
                sym = row[0]
                d = row[1]
                n = row[2] or 0
                w = row[3] or 0
                l = row[4] or 0
                exflat = w + l
                wr = w / exflat if exflat > 0 else 0
                if sym in perms and d in perms.get(sym, {}):
                    perms[sym][d] = {"wr": wr, "n": exflat, "reason": ""}
                    if wr >= _MIN_WR and exflat >= _MIN_NONFLAT:
                        perms[sym][d]["allowed"] = True
                    elif exflat < _MIN_NONFLAT:
                        perms[sym][d]["reason"] = f"insufficient data (n={exflat}<{_MIN_NONFLAT})"
                    else:
                        perms[sym][d]["reason"] = f"WR {wr:.0%} < {_MIN_WR:.0%}"
        finally:
            conn.close()
    except Exception as e:
        LOGGER.error("live perms error: %s", e)
    _wr_cache = perms
    _wr_cache_ts = now
    return perms


def get_signal(symbol: str, direction: str) -> Optional[dict]:
    regime_id, mod, regime_name, tradeable = get_regime()
    if not tradeable:
        return None

    blocked, _ = _is_blocked_today()
    if blocked:
        return None

    live_perms = _get_live_perms()
    perm = live_perms.get(symbol, {}).get(direction, {})
    if not perm.get("allowed", False):
        return None

    regime_allowed = _REGIME_ALLOW.get(symbol, {}).get(direction, [])
    if regime_id not in regime_allowed:
        return None

    now = time.time()
    cooldown_key = f"{symbol}_{direction}"
    last_t = _last_signal_time.get(cooldown_key, 0)
    if now - last_t < _COOLDOWN_SEC:
        return None

    conn = _get_db()
    if not conn:
        return None
    try:
        tick = _latest_tick(conn, symbol)
        candle = _latest_candle(conn, symbol)
        avg_vol = _avg_volume(conn, symbol)

        if not tick or not candle:
            return None

        if _tick_freshness(tick["timestamp"]) > 30.0:
            return None

        score = 50

        d = tick.get("delta", 0) or 0
        if direction == "BUY" and d > 0:
            score += 15
        if direction == "SELL" and d < 0:
            score += 15

        sp = tick.get("spread_bps", 0) or 0
        if sp > 2.5:
            score -= 20
        elif sp < 1.5:
            score += 10

        o = candle["open"]
        c = candle["close"]
        h = candle["high"]
        l = candle["low"]
        body = c - o
        if direction == "BUY" and body > 0:
            score += 10
        if direction == "SELL" and body < 0:
            score += 10

        abs_body = abs(body)
        if abs_body > 0:
            uw = h - max(o, c)
            lw = min(o, c) - l
            if direction == "BUY" and lw > abs_body * 1.5:
                score += 12
            if direction == "SELL" and uw > abs_body * 1.5:
                score += 12

        vol = candle.get("volume", 0) or 0
        if avg_vol > 0 and vol > avg_vol * 1.5:
            score += 8

        dom_metrics = _extract_dom_metrics(tick.get("dom"))
        if direction == "BUY" and dom_metrics["obi"] > 0.3:
            score += 5
        if direction == "SELL" and dom_metrics["obi"] < -0.3:
            score += 5

        score = int(score * mod)
        score = max(0, min(100, score))

        if score < 70:
            return None

        _last_signal_time[cooldown_key] = now

        if score >= 85:
            label = "STRONG UP" if direction == "BUY" else "STRONG DOWN"
            arrow = "\u2191\u2191" if direction == "BUY" else "\u2193\u2193"
            cls = "strong"
        else:
            label = "UP" if direction == "BUY" else "DOWN"
            arrow = "\u2191" if direction == "BUY" else "\u2193"
            cls = "normal"

        utc_now = datetime.now(timezone.utc)
        return {
            "symbol": symbol,
            "dir": direction,
            "label": label,
            "arrow": arrow,
            "cls": cls,
            "prob": score,
            "regime": f"T{regime_id}",
            "regime_name": regime_name,
            "expiry": "1 MIN",
            "spread": round(sp, 2),
            "delta": round(d, 2),
            "obi": round(dom_metrics["obi"], 3),
            "time": utc_now.strftime("%H:%M:%S"),
            "timestamp": utc_now.isoformat(),
            "entry_mid": tick["mid"],
            "prio_sym": _BUY_PRIO.get(symbol, 99),
            "prio_regime": _REGIME_PRIO.get(regime_id, 99),
        }
    except Exception as e:
        LOGGER.error("binary signal error %s %s: %s", symbol, direction, e)
        return None
    finally:
        conn.close()


def get_all_binary_signals() -> List[dict]:
    out = []
    for sym in _SYMBOLS:
        for d in ["BUY", "SELL"]:
            s = get_signal(sym, d)
            if s:
                out.append(s)
    out.sort(key=lambda x: (-x["prob"], x["prio_regime"], x["prio_sym"]))
    return out[:_MAX_ACTIVE]


def get_binary_stats() -> dict:
    conn = _get_db()
    if not conn:
        return {"today_wr": 0, "today_signals": 0, "today_wins": 0, "today_losses": 0, "best_symbol": "-", "avg_prob": 0, "regime": "T?", "regime_name": "-"}
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        regime_id, mod, regime_name, tradeable = get_regime()
        live_perms = _get_live_perms()
        perms_summary = {}
        for sym, dirs in live_perms.items():
            for d, info in dirs.items():
                key = f"{sym}_{d}"
                perms_summary[key] = {
                    "allowed": info.get("allowed", False),
                    "wr": round(info.get("wr", 0), 3),
                    "n": info.get("n", 0),
                    "reason": info.get("reason", ""),
                }
        return {
            "regime": f"T{regime_id}",
            "regime_name": regime_name,
            "regime_tradeable": tradeable,
            "regime_modifier": mod,
            "today_wr": 0,
            "today_signals": 0,
            "today_wins": 0,
            "today_losses": 0,
            "best_symbol": "-",
            "avg_prob": 0,
            "utc_hour": datetime.now(timezone.utc).hour,
            "permissions": perms_summary,
        }
    except Exception:
        return {}
    finally:
        conn.close()


def should_telegram(signal: dict) -> bool:
    global _last_telegram_time
    if signal["cls"] != "strong":
        return False
    now = time.time()
    if now - _last_telegram_time < 60:
        return False
    _last_telegram_time = now
    return True
