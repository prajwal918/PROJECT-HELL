from __future__ import annotations

import logging
import os
import time
from typing import Any

LOGGER = logging.getLogger("overseer.dom_quality")

_STALE_BOOK_MAX_AGE_SECONDS = float(os.getenv("STALE_BOOK_MAX_AGE_SECONDS", "5.0"))
_DEPTH_COLLAPSE_MIN_LEVELS = int(os.getenv("DEPTH_COLLAPSE_MIN_LEVELS", "3"))
_SPREAD_SPIKE_MAX_SIGMAS = float(os.getenv("SPREAD_SPIKE_MAX_SIGMAS", "5.0"))
_VACUUM_MIN_DEPTH = int(os.getenv("VACUUM_MIN_DEPTH", "5"))
_RECOVERY_COOLDOWN_SECONDS = float(os.getenv("DOM_RECOVERY_COOLDOWN_SECONDS", "30.0"))
_CROSSED_BOOK_GRACE_TICKS = int(os.getenv("DOM_CROSSED_BOOK_GRACE_TICKS", "3"))
_AUTO_FIX_CROSSED_BOOK = os.getenv("DOM_AUTO_FIX_CROSSED_BOOK", "true").lower() == "true"


class DOMQualityChecker:
    def __init__(self) -> None:
        self._last_dom_time: dict[str, float] = {}
        self._last_bid: dict[str, float] = {}
        self._last_ask: dict[str, float] = {}
        self._last_depth_bid: dict[str, int] = {}
        self._last_depth_ask: dict[str, int] = {}
        self._spread_history: dict[str, list[float]] = {}
        self._halted_symbols: set[str] = set()
        self._halt_time: dict[str, float] = {}
        self._halt_reasons: dict[str, str] = {}
        self._feed_healthy: dict[str, bool] = {}
        self._max_spread_history = 100
        self._last_symbol: str | None = None
        self._consecutive_crossed: dict[str, int] = {}

    def check_tick(self, tick: dict[str, Any]) -> bool:
        symbol = str(tick.get("symbol", ""))
        if not symbol:
            return False
        quality = self.update(symbol, tick)
        tick.update(quality)
        return True

    def update(self, symbol: str, tick: dict[str, Any]) -> dict[str, Any]:
        now = time.monotonic()
        self._last_symbol = symbol
        bid = float(tick.get("bid", 0))
        ask = float(tick.get("ask", 0))
        auto_swapped = False
        if _AUTO_FIX_CROSSED_BOOK and bid > 0 and ask > 0 and bid > ask:
            bid, ask = ask, bid
            tick["bid"], tick["ask"] = bid, ask
            tick["bid_size"], tick["ask_size"] = tick.get("ask_size", 0), tick.get("bid_size", 0)
            auto_swapped = True
        dom = tick.get("dom", {})
        bid_depth = 0
        ask_depth = 0
        if isinstance(dom, dict):
            bid_levels = dom.get("bids", [])
            ask_levels = dom.get("asks", [])
            if isinstance(bid_levels, list):
                bid_depth = len(bid_levels)
            if isinstance(ask_levels, list):
                ask_depth = len(ask_levels)

        prev_bid = self._last_bid.get(symbol, 0)
        prev_ask = self._last_ask.get(symbol, 0)
        self._last_bid[symbol] = bid
        self._last_ask[symbol] = ask
        self._last_depth_bid[symbol] = bid_depth
        self._last_depth_ask[symbol] = ask_depth
        self._last_dom_time[symbol] = now

        mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0
        spread = (ask - bid) / mid * 10000 if mid > 0 else 0
        if symbol not in self._spread_history:
            self._spread_history[symbol] = []
        self._spread_history[symbol].append(spread)
        if len(self._spread_history[symbol]) > self._max_spread_history:
            self._spread_history[symbol] = self._spread_history[symbol][-self._max_spread_history:]

        issues: list[str] = []
        quality_score = 1.0

        if bid <= 0 or ask <= 0:
            issues.append("zero_bid_ask")
            quality_score = 0.0
        elif bid > ask:
            self._consecutive_crossed[symbol] = self._consecutive_crossed.get(symbol, 0) + 1
            if self._consecutive_crossed[symbol] >= _CROSSED_BOOK_GRACE_TICKS:
                issues.append("crossed_book")
                quality_score = 0.0
        elif bid == ask:
            if bid_depth > 0 or ask_depth > 0:
                issues.append("zero_spread")
                quality_score *= 0.7
            self._consecutive_crossed[symbol] = 0
        else:
            self._consecutive_crossed[symbol] = 0

        if prev_bid > 0 and prev_ask > 0 and bid > 0 and ask > 0 and bid < ask:
            sp_history = self._spread_history[symbol]
            if len(sp_history) >= 20:
                mean_sp = sum(sp_history[-50:]) / len(sp_history[-50:])
                std_sp = (sum((x - mean_sp) ** 2 for x in sp_history[-50:]) / len(sp_history[-50:])) ** 0.5
                if std_sp > 0 and spread > mean_sp + _SPREAD_SPIKE_MAX_SIGMAS * std_sp:
                    issues.append("spread_spike")
                    quality_score *= 0.3

        total_depth = bid_depth + ask_depth
        if total_depth < _VACUUM_MIN_DEPTH and total_depth > 0:
            issues.append("liquidity_vacuum")
            quality_score *= 0.4

        if bid_depth < _DEPTH_COLLAPSE_MIN_LEVELS or ask_depth < _DEPTH_COLLAPSE_MIN_LEVELS:
            if bid_depth == 0 or ask_depth == 0:
                pass

        halt_issues = [i for i in issues if i in ("crossed_book", "zero_bid_ask")]
        if halt_issues:
            self._halted_symbols.add(symbol)
            self._halt_time[symbol] = now
            self._halt_reasons[symbol] = ",".join(halt_issues)
            self._feed_healthy[symbol] = False
        elif symbol in self._halted_symbols:
            cooldown_end = self._halt_time.get(symbol, 0) + _RECOVERY_COOLDOWN_SECONDS
            if now >= cooldown_end:
                self._halted_symbols.discard(symbol)
                self._halt_reasons.pop(symbol, None)
                self._feed_healthy[symbol] = True
                LOGGER.info("DOM quality recovered for %s", symbol)

        is_stale = False
        last_t = self._last_dom_time.get(symbol, 0)
        if last_t > 0 and (now - last_t) > _STALE_BOOK_MAX_AGE_SECONDS:
            is_stale = True
            issues.append("stale_book")
            quality_score *= 0.5

        return {
            "dom_healthy": len(issues) == 0 and not is_stale,
            "dom_quality_score": round(quality_score, 3),
            "dom_issues": issues,
            "dom_stale": is_stale,
            "dom_halted": symbol in self._halted_symbols,
            "dom_halt_reason": self._halt_reasons.get(symbol, ""),
            "dom_auto_swapped": auto_swapped,
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "spread_bps": round(spread, 2),
        }

    def is_trading_allowed(self, symbol: str | None = None) -> tuple[bool, str]:
        if symbol is None:
            symbol = self._last_symbol
        if not symbol:
            if self._halted_symbols:
                halted = ",".join(sorted(self._halted_symbols))
                return False, f"DOM quality: halted symbols {halted}"
            return True, ""
        if symbol in self._halted_symbols:
            return False, f"DOM quality: {self._halt_reasons.get(symbol, 'unknown')}"
        return True, ""

    def check_heartbeat(self, symbol: str) -> bool:
        now = time.monotonic()
        last_t = self._last_dom_time.get(symbol, 0)
        if last_t == 0:
            return False
        return (now - last_t) <= _STALE_BOOK_MAX_AGE_SECONDS

    def get_status(self) -> dict[str, Any]:
        return {
            "halted_symbols": list(self._halted_symbols),
            "halt_reasons": dict(self._halt_reasons),
            "healthy_feeds": {s: v for s, v in self._feed_healthy.items() if v},
            "last_dom_times": {s: round(t, 2) for s, t in self._last_dom_time.items()},
        }
