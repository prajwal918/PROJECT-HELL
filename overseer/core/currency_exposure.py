from __future__ import annotations

import logging
import os
from typing import Any

LOGGER = logging.getLogger("overseer.currency_exposure")

_MAX_CURRENCY_EXPOSURE = int(os.getenv("MAX_CURRENCY_EXPOSURE", "2"))
_MAX_AGGREGATE_USD_EXPOSURE = int(os.getenv("MAX_AGGREGATE_USD_EXPOSURE", "3"))
_MAX_CORRELATED_EXPOSURE = int(os.getenv("MAX_CORRELATED_EXPOSURE", "2"))

_CURRENCY_MAP: dict[str, tuple[str, str]] = {
    "6E": ("EUR", "USD"),
    "6B": ("GBP", "USD"),
    "6J": ("USD", "JPY"),
    "6A": ("AUD", "USD"),
    "6C": ("USD", "CAD"),
    "6N": ("NZD", "USD"),
    "6S": ("USD", "CHF"),
    "6M": ("MXN", "USD"),
    "6EM6": ("EUR", "USD"),
    "6BM6": ("GBP", "USD"),
    "6JM6": ("USD", "JPY"),
    "6AM6": ("AUD", "USD"),
    "6CM6": ("USD", "CAD"),
    "6NM6": ("NZD", "USD"),
    "6SM6": ("USD", "CHF"),
    "6MM6": ("MXN", "USD"),
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "USDJPY": ("USD", "JPY"),
    "AUDUSD": ("AUD", "USD"),
    "USDCAD": ("USD", "CAD"),
    "NZDUSD": ("NZD", "USD"),
    "USDCHF": ("USD", "CHF"),
}

_CORRELATED_GROUPS: list[tuple[str, ...]] = (
    ("EUR", "GBP", "CHF"),
    ("AUD", "NZD"),
    ("CAD",),
)

_BLOCKED_ROLLOVER_START_H = int(os.getenv("ROLLOVER_BLOCK_START_H", "20"))
_BLOCKED_ROLLOVER_START_M = int(os.getenv("ROLLOVER_BLOCK_START_M", "55"))
_BLOCKED_ROLLOVER_END_H = int(os.getenv("ROLLOVER_BLOCK_END_H", "21"))
_BLOCKED_ROLLOVER_END_M = int(os.getenv("ROLLOVER_BLOCK_END_M", "5"))
_SPREAD_EFFICIENCY_MAX_PCT = float(os.getenv("SPREAD_EFFICIENCY_MAX_PCT", "20.0"))


def _resolve_currencies(symbol: str) -> tuple[str, str] | None:
    if symbol in _CURRENCY_MAP:
        return _CURRENCY_MAP[symbol]
    for key, val in _CURRENCY_MAP.items():
        if symbol.startswith(key):
            return val
    return None


class CurrencyExposureTracker:
    def __init__(self) -> None:
        self._positions: dict[str, dict[str, Any]] = {}

    def register_position(self, symbol: str, direction: str, lot_size: float, entry_price: float) -> None:
        pair = _resolve_currencies(symbol)
        if pair is None:
            return
        self._positions[symbol] = {
            "direction": direction,
            "lot_size": lot_size,
            "entry_price": entry_price,
            "base": pair[0],
            "quote": pair[1],
        }

    def unregister_position(self, symbol: str) -> None:
        self._positions.pop(symbol, None)

    def get_net_exposure(self) -> dict[str, int]:
        exposure: dict[str, int] = {}
        for pos in self._positions.values():
            direction = pos["direction"]
            base = pos["base"]
            quote = pos["quote"]
            if direction == "BUY":
                exposure[base] = exposure.get(base, 0) + 1
                exposure[quote] = exposure.get(quote, 0) - 1
            else:
                exposure[base] = exposure.get(base, 0) - 1
                exposure[quote] = exposure.get(quote, 0) + 1
        return exposure

    def get_correlated_exposure(self) -> dict[str, int]:
        net = self.get_net_exposure()
        corr: dict[str, int] = {}
        for group in _CORRELATED_GROUPS:
            total = sum(abs(net.get(c, 0)) for c in group)
            for c in group:
                corr[c] = total
        return corr

    def check_new_position(self, symbol: str, direction: str) -> tuple[bool, str]:
        pair = _resolve_currencies(symbol)
        if pair is None:
            return True, ""

        base, quote = pair
        test_positions = dict(self._positions)
        test_positions[symbol] = {
            "direction": direction,
            "base": base,
            "quote": quote,
        }
        exposure: dict[str, int] = {}
        for pos in test_positions.values():
            d = pos["direction"]
            b = pos["base"]
            q = pos["quote"]
            if d == "BUY":
                exposure[b] = exposure.get(b, 0) + 1
                exposure[q] = exposure.get(q, 0) - 1
            else:
                exposure[b] = exposure.get(b, 0) - 1
                exposure[q] = exposure.get(q, 0) + 1

        for currency, exp in exposure.items():
            if abs(exp) > _MAX_CURRENCY_EXPOSURE:
                return False, f"FX-3: {currency} exposure={exp} > max={_MAX_CURRENCY_EXPOSURE}"

        usd_exp = abs(exposure.get("USD", 0))
        if usd_exp > _MAX_AGGREGATE_USD_EXPOSURE:
            return False, f"USD aggregate exposure={usd_exp} > max={_MAX_AGGREGATE_USD_EXPOSURE}"

        corr: dict[str, int] = {}
        for group in _CORRELATED_GROUPS:
            total = sum(abs(exposure.get(c, 0)) for c in group)
            for c in group:
                corr[c] = total
        for currency, total in corr.items():
            if total > _MAX_CORRELATED_EXPOSURE:
                return False, f"Correlated exposure: {currency} group total={total} > max={_MAX_CORRELATED_EXPOSURE}"

        return True, ""

    def get_status(self) -> dict[str, Any]:
        return {
            "open_positions": len(self._positions),
            "net_exposure": self.get_net_exposure(),
            "correlated_exposure": self.get_correlated_exposure(),
            "symbols": list(self._positions.keys()),
        }


def is_rollover_block() -> bool:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    h, m = now.hour, now.minute
    start_min = _BLOCKED_ROLLOVER_START_H * 60 + _BLOCKED_ROLLOVER_START_M
    end_min = _BLOCKED_ROLLOVER_END_H * 60 + _BLOCKED_ROLLOVER_END_M
    now_min = h * 60 + m
    if start_min <= end_min:
        return start_min <= now_min < end_min
    else:
        return now_min >= start_min or now_min < end_min


def check_spread_efficiency(spread_bps: float, sl_pips: float) -> tuple[bool, str]:
    if sl_pips <= 0:
        return True, ""
    spread_pips = spread_bps / 10.0
    pct = (spread_pips / sl_pips) * 100.0
    if pct > _SPREAD_EFFICIENCY_MAX_PCT:
        return False, f"Spread efficiency: spread={pct:.1f}% of SL > max={_SPREAD_EFFICIENCY_MAX_PCT}%"
    return True, ""


def check_max_notional(symbol: str, lot_size: float, account_balance: float) -> tuple[bool, str]:
    max_notional = float(os.getenv("MAX_NOTIONAL_PER_SYMBOL", "50000"))
    max_total = float(os.getenv("MAX_TOTAL_NOTIONAL", "100000"))
    notional = lot_size * 100000
    if notional > max_notional:
        return False, f"Notional ${notional:,.0f} > max ${max_notional:,.0f} per symbol"
    if notional > account_balance * 0.1:
        return False, f"Notional ${notional:,.0f} > 10% of balance ${account_balance:,.0f}"
    return True, ""


def check_margin_usage(account_balance: float) -> tuple[bool, str]:
    max_margin_pct = float(os.getenv("MAX_MARGIN_USAGE_PCT", "50.0"))
    try:
        import MetaTrader5 as mt5
        info = mt5.account_info()
        if info is not None:
            margin_used = float(info.margin)
            margin_pct = (margin_used / account_balance * 100) if account_balance > 0 else 0
            if margin_pct > max_margin_pct:
                return False, f"Margin usage {margin_pct:.1f}% > max {max_margin_pct}%"
    except Exception:
        pass
    return True, ""
