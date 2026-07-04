#!/usr/bin/env python3
"""
OANDA REST API Executor for OVERSEER.

Works on Linux. No MT5 needed.
Supports practice (demo) and live accounts.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOGGER = logging.getLogger("overseer.oanda")

OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_PRACTICE = os.getenv("OANDA_PRACTICE", "true").lower() in ("true", "1", "yes")

_BASE_URL = "https://api-fxpractice.oanda.com" if OANDA_PRACTICE else "https://api-fxtrade.oanda.com"
_STREAM_URL = "https://stream-fxpractice.oanda.com" if OANDA_PRACTICE else "https://stream-fxtrade.oanda.com"

_INSTRUMENT_MAP = {
    "6EM6": "EUR_USD",
    "6BM6": "GBP_USD",
    "6JM6": "USD_JPY",
    "6AM6": "AUD_USD",
    "6CM6": "USD_CAD",
    "6NM6": "NZD_USD",
    "6SM6": "USD_CHF",
    "GC": "XAU_USD",
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
    "AUDUSD": "AUD_USD",
    "USDCAD": "USD_CAD",
    "NZDUSD": "NZD_USD",
    "USDCHF": "USD_CHF",
    "XAUUSD": "XAU_USD",
}

_PIP_MAP = {
    "EUR_USD": 0.0001, "GBP_USD": 0.0001, "AUD_USD": 0.0001,
    "USD_CAD": 0.0001, "NZD_USD": 0.0001, "USD_CHF": 0.0001,
    "USD_JPY": 0.01, "XAU_USD": 0.01,
}

_connected = False
_account_info: Dict[str, Any] = {}


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {OANDA_API_KEY}",
        "Content-Type": "application/json",
        "Accept-Datetime-Format": "UNIX",
    }


def _request(method: str, path: str, body: Optional[dict] = None) -> Optional[dict]:
    if not OANDA_API_KEY:
        return None
    url = f"{_BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=_headers(), method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        LOGGER.error("OANDA %s %s HTTP %d: %s", method, path, e.code, err_body[:200])
        return None
    except URLError as e:
        LOGGER.error("OANDA %s %s URL error: %s", method, path, e.reason)
        return None
    except Exception as e:
        LOGGER.error("OANDA %s %s error: %s", method, path, e)
        return None


def map_symbol(overseer_symbol: str) -> Optional[str]:
    s = overseer_symbol.upper().replace("/", "_").replace("-", "_")
    if s in _INSTRUMENT_MAP:
        return _INSTRUMENT_MAP[s]
    for oanda_inst in _INSTRUMENT_MAP.values():
        if s == oanda_inst:
            return oanda_inst
    return None


def pip_size(instrument: str) -> float:
    return _PIP_MAP.get(instrument, 0.0001)


def connect() -> bool:
    global _connected, _account_info
    if not OANDA_API_KEY or not OANDA_ACCOUNT_ID:
        LOGGER.warning("OANDA_API_KEY or OANDA_ACCOUNT_ID not set")
        _connected = False
        return False
    resp = _request("GET", f"/v3/accounts/{OANDA_ACCOUNT_ID}/summary")
    if not resp:
        _connected = False
        return False
    acct = resp.get("account", {})
    _account_info = {
        "balance": float(acct.get("balance", 0)),
        "currency": acct.get("currency", "USD"),
        "open_trade_count": int(acct.get("openTradeCount", 0)),
        "margin_used": float(acct.get("marginUsed", 0)),
        "margin_available": float(acct.get("marginAvailable", 0)),
        "unrealized_pnl": float(acct.get("unrealizedPnL", 0)),
        "nav": float(acct.get("NAV", 0)),
    }
    _connected = True
    mode = "PRACTICE" if OANDA_PRACTICE else "LIVE"
    LOGGER.info(
        "OANDA %s connected: balance=%s %s open_trades=%d margin_avail=%s",
        mode,
        _account_info["balance"],
        _account_info["currency"],
        _account_info["open_trade_count"],
        _account_info["margin_available"],
    )
    return True


def get_account_balance() -> float:
    if not _connected:
        return 0.0
    resp = _request("GET", f"/v3/accounts/{OANDA_ACCOUNT_ID}/summary")
    if not resp:
        return _account_info.get("balance", 0.0)
    acct = resp.get("account", {})
    return float(acct.get("balance", 0))


def get_open_positions() -> Optional[List[dict]]:
    if not _connected:
        return None
    resp = _request("GET", f"/v3/accounts/{OANDA_ACCOUNT_ID}/openTrades")
    if resp is None:
        return None
    trades = resp.get("trades", [])
    result = []
    for t in trades:
        inst = t.get("instrument", "")
        units = int(float(t.get("currentUnits", "0")))
        direction = "BUY" if units > 0 else "SELL"
        result.append({
            "ticket": int(t.get("id", 0)),
            "symbol": inst,
            "direction": direction,
            "volume": abs(units),
            "open_price": float(t.get("price", 0)),
            "unrealized_pnl": float(t.get("unrealizedPnL", 0)),
            "sl": float(t.get("stopLossOrder", {}).get("price", 0)) if t.get("stopLossOrder") else 0,
            "tp": float(t.get("takeProfitOrder", {}).get("price", 0)) if t.get("takeProfitOrder") else 0,
        })
    return result


def get_pricing(instrument: str) -> Optional[dict]:
    resp = _request("GET", f"/v3/accounts/{OANDA_ACCOUNT_ID}/pricing?instruments={instrument}")
    if not resp:
        return None
    prices = resp.get("prices", [])
    if not prices:
        return None
    p = prices[0]
    bids = p.get("bids", [])
    asks = p.get("asks", [])
    if not bids or not asks:
        return None
    return {
        "bid": float(bids[0].get("price", 0)),
        "ask": float(asks[0].get("price", 0)),
        "spread": float(asks[0].get("price", 0)) - float(bids[0].get("price", 0)),
        "time": p.get("time", ""),
    }


def execute_trade(
    symbol: str,
    direction: str,
    lot_size: float = 0.01,
    sl_pips: float = 5.0,
    tp_pips: float = 12.5,
    tick: Optional[dict] = None,
) -> Optional[dict]:
    if not _connected:
        LOGGER.warning("OANDA not connected — cannot execute trade")
        return None

    instrument = map_symbol(symbol)
    if not instrument:
        LOGGER.error("Cannot map symbol %s to OANDA instrument", symbol)
        return None

    units = int(lot_size * 100000)
    if direction == "SELL":
        units = -units

    pricing = get_pricing(instrument)
    if not pricing:
        LOGGER.error("Cannot get OANDA pricing for %s", instrument)
        return None

    pip_val = pip_size(instrument)
    entry_price = pricing["ask"] if direction == "BUY" else pricing["bid"]

    if direction == "BUY":
        sl_price = round(entry_price - sl_pips * pip_val, 5)
        tp_price = round(entry_price + tp_pips * pip_val, 5)
    else:
        sl_price = round(entry_price + sl_pips * pip_val, 5)
        tp_price = round(entry_price - tp_pips * pip_val, 5)

    if "JPY" in instrument:
        sl_price = round(sl_price, 3)
        tp_price = round(tp_price, 3)
    elif "XAU" in instrument:
        sl_price = round(sl_price, 2)
        tp_price = round(tp_price, 2)

    order = {
        "order": {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(units),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {"price": str(sl_price), "timeInForce": "GTC"},
            "takeProfitOnFill": {"price": str(tp_price), "timeInForce": "GTC"},
        }
    }

    resp = _request("POST", f"/v3/accounts/{OANDA_ACCOUNT_ID}/orders", body=order)

    if not resp:
        LOGGER.error("OANDA order failed: no response")
        return None

    order_resp = resp.get("orderFillTransaction") or resp.get("orderCancelTransaction") or resp
    if resp.get("orderRejectTransaction") or resp.get("orderCancelTransaction"):
        reason = order_resp.get("reason", "unknown")
        LOGGER.warning("OANDA order rejected: %s", reason)
        return {"status": "rejected", "reason": reason}

    fill_price = float(order_resp.get("price", entry_price))
    trade_id = order_resp.get("tradeOpened", {}).get("tradeID") or order_resp.get("id", "0")
    fill_time = order_resp.get("time", "")

    LOGGER.info(
        "OANDA EXECUTED: %s %s %s | units=%d fill=%.5f sl=%.5f tp=%.5f trade_id=%s",
        direction, instrument, symbol, units, fill_price, sl_price, tp_price, trade_id,
    )

    return {
        "status": "filled",
        "ticket": int(trade_id) if trade_id else 0,
        "symbol": instrument,
        "direction": direction,
        "volume": lot_size,
        "fill_price": fill_price,
        "sl": sl_price,
        "tp": tp_price,
        "time": fill_time,
    }


def close_trade(trade_id: int) -> bool:
    if not _connected:
        return False
    resp = _request("PUT", f"/v3/accounts/{OANDA_ACCOUNT_ID}/trades/{trade_id}/close", body={})
    if not resp:
        return False
    LOGGER.info("OANDA closed trade %s", trade_id)
    return True


def modify_sl(trade_id: int, new_sl: float) -> bool:
    if not _connected:
        return False
    body = {"stopLoss": {"price": str(round(new_sl, 5)), "timeInForce": "GTC"}}
    resp = _request("PUT", f"/v3/accounts/{OANDA_ACCOUNT_ID}/trades/{trade_id}/orders", body=body)
    if not resp:
        return False
    LOGGER.info("OANDA modified SL trade %s to %.5f", trade_id, new_sl)
    return True


def shutdown() -> None:
    global _connected
    _connected = False
    LOGGER.info("OANDA executor shutdown")


def is_connected() -> bool:
    return _connected
