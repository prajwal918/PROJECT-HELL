from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.order_book_engine")

_MAX_ORDERS_PER_SYMBOL = int(os.getenv("MAX_ORDERS_PER_SYMBOL", "50000"))
_TRADE_BURST_WINDOW_MS = float(os.getenv("TRADE_BURST_WINDOW_MS", "1000.0"))
_TRADE_BURST_THRESHOLD = int(os.getenv("TRADE_BURST_THRESHOLD", "10"))
_QUEUE_DECAY_WINDOW_MS = float(os.getenv("QUEUE_DECAY_WINDOW_MS", "5000.0"))


class PriceLevel:
    __slots__ = ("price", "orders", "visible_size", "implied_size", "order_count", "last_update", "cancel_count", "add_count")

    def __init__(self, price: float) -> None:
        self.price = price
        self.orders: dict[str, dict[str, Any]] = {}
        self.visible_size: float = 0.0
        self.implied_size: float = 0.0
        self.order_count: int = 0
        self.last_update: float = 0.0
        self.cancel_count: int = 0
        self.add_count: int = 0

    def add_order(self, order_id: str, size: float, implied_size: float = 0, timestamp: float = 0) -> None:
        self.orders[order_id] = {"size": size, "implied_size": implied_size, "add_time": timestamp, "modify_count": 0}
        self.visible_size += size
        self.implied_size += implied_size
        self.order_count = len(self.orders)
        self.add_count += 1
        self.last_update = timestamp

    def modify_order(self, order_id: str, new_size: float, new_implied: float = 0, timestamp: float = 0) -> None:
        if order_id in self.orders:
            old = self.orders[order_id]
            self.visible_size -= old["size"]
            self.implied_size -= old["implied_size"]
            old["size"] = new_size
            old["implied_size"] = new_implied
            old["modify_count"] = old.get("modify_count", 0) + 1
            self.visible_size += new_size
            self.implied_size += new_implied
            self.last_update = timestamp

    def remove_order(self, order_id: str, timestamp: float = 0) -> float:
        if order_id in self.orders:
            old = self.orders.pop(order_id)
            self.visible_size -= old["size"]
            self.implied_size -= old["implied_size"]
            self.order_count = len(self.orders)
            self.cancel_count += 1
            self.last_update = timestamp
            return old["size"]
        return 0.0

    def total_size(self) -> float:
        return self.visible_size + self.implied_size


class SymbolBook:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.bids: dict[float, PriceLevel] = {}
        self.asks: dict[float, PriceLevel] = {}
        self.best_bid: float = 0.0
        self.best_ask: float = 0.0
        self._order_side: dict[str, str] = {}
        self._order_price: dict[str, float] = {}
        self._trade_prints: deque[dict[str, Any]] = deque(maxlen=1000)
        self._cancel_rate_window: deque[tuple[float, str]] = deque(maxlen=5000)
        self._last_snapshot_time: float = 0.0

    def process_add(self, order_id: str, side: str, price: float, size: float, implied_size: float = 0, timestamp: float = 0) -> None:
        if timestamp == 0:
            timestamp = time.time()
        levels = self.bids if side == "bid" else self.asks
        if price not in levels:
            levels[price] = PriceLevel(price)
        levels[price].add_order(order_id, size, implied_size, timestamp)
        self._order_side[order_id] = side
        self._order_price[order_id] = price
        self._update_bbo()
        self._cancel_rate_window.append((timestamp, "ADD"))

    def process_modify(self, order_id: str, new_size: float, new_implied: float = 0, timestamp: float = 0) -> None:
        if timestamp == 0:
            timestamp = time.time()
        side = self._order_side.get(order_id)
        price = self._order_price.get(order_id)
        if side is None or price is None:
            return
        levels = self.bids if side == "bid" else self.asks
        level = levels.get(price)
        if level is not None:
            level.modify_order(order_id, new_size, new_implied, timestamp)
            self._cancel_rate_window.append((timestamp, "MODIFY"))

    def process_cancel(self, order_id: str, timestamp: float = 0) -> None:
        if timestamp == 0:
            timestamp = time.time()
        side = self._order_side.pop(order_id, None)
        price = self._order_price.pop(order_id, None)
        if side is None or price is None:
            return
        levels = self.bids if side == "bid" else self.asks
        level = levels.get(price)
        if level is not None:
            removed_size = level.remove_order(order_id, timestamp)
            if level.order_count == 0:
                del levels[price]
            self._update_bbo()
        self._cancel_rate_window.append((timestamp, "CANCEL"))

    def process_trade(self, aggressor_side: str, price: float, size: float, timestamp: float = 0) -> None:
        if timestamp == 0:
            timestamp = time.time()
        self._trade_prints.append({
            "side": aggressor_side,
            "price": price,
            "size": size,
            "timestamp": timestamp,
        })
        levels = self.asks if aggressor_side == "buy" else self.bids
        level = levels.get(price)
        if level is not None:
            remaining = size
            to_remove = []
            for oid, order in level.orders.items():
                if remaining <= 0:
                    break
                if order["size"] <= remaining:
                    remaining -= order["size"]
                    to_remove.append(oid)
                else:
                    order["size"] -= remaining
                    level.visible_size -= remaining
                    remaining = 0
            for oid in to_remove:
                level.remove_order(oid, timestamp)
                self._order_side.pop(oid, None)
                self._order_price.pop(oid, None)
            if level.order_count == 0 and price in levels:
                del levels[price]
            self._update_bbo()
        self._cancel_rate_window.append((timestamp, "TRADE"))

    def _update_bbo(self) -> None:
        if self.bids:
            self.best_bid = max(self.bids.keys())
        else:
            self.best_bid = 0
        if self.asks:
            self.best_ask = min(self.asks.keys())
        else:
            self.best_ask = 0

    def reconcile_with_snapshot(self, dom: dict[str, Any], timestamp: float = 0) -> dict[str, Any]:
        if timestamp == 0:
            timestamp = time.time()
        bid_levels = dom.get("bids", [])
        ask_levels = dom.get("asks", [])
        drift: dict[str, Any] = {"bid_drift": 0, "ask_drift": 0, "reconciled": False}

        snap_bids: dict[float, float] = {}
        for lvl in bid_levels:
            p = float(lvl.get("price", lvl.get("Price", 0)))
            s = float(lvl.get("size", lvl.get("Size", 0)))
            if p > 0:
                snap_bids[p] = s

        snap_asks: dict[float, float] = {}
        for lvl in ask_levels:
            p = float(lvl.get("price", lvl.get("Price", 0)))
            s = float(lvl.get("size", lvl.get("Size", 0)))
            if p > 0:
                snap_asks[p] = s

        for price, level in self.bids.items():
            snap_size = snap_bids.get(price, 0)
            if abs(level.visible_size - snap_size) > level.visible_size * 0.1 + 1:
                drift["bid_drift"] += 1

        for price, level in self.asks.items():
            snap_size = snap_asks.get(price, 0)
            if abs(level.visible_size - snap_size) > level.visible_size * 0.1 + 1:
                drift["ask_drift"] += 1

        drift["reconciled"] = True
        self._last_snapshot_time = timestamp
        return drift

    def get_queue_stats(self) -> dict[str, Any]:
        now = time.time()
        window_start = now - _QUEUE_DECAY_WINDOW_MS / 1000.0

        bid_cancel_count = 0
        ask_cancel_count = 0
        bid_add_count = 0
        ask_add_count = 0
        for ts, event_type in self._cancel_rate_window:
            if ts < window_start:
                continue
            if event_type == "CANCEL":
                bid_cancel_count += 1
            elif event_type == "ADD":
                bid_add_count += 1

        bid_cancel_rate = bid_cancel_count / max(1, bid_add_count + bid_cancel_count) * 100
        ask_cancel_rate = ask_cancel_count / max(1, bid_add_count + ask_cancel_count) * 100

        bid_depth = sum(lvl.total_size() for lvl in self.bids.values())
        ask_depth = sum(lvl.total_size() for lvl in self.asks.values())

        return {
            "bid_depth": round(bid_depth, 1),
            "ask_depth": round(ask_depth, 1),
            "bid_levels": len(self.bids),
            "ask_levels": len(self.asks),
            "bid_cancel_rate": round(bid_cancel_rate, 1),
            "ask_cancel_rate": round(ask_cancel_rate, 1),
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "spread": round(self.best_ask - self.best_bid, 6) if self.best_bid > 0 and self.best_ask > 0 else 0,
        }

    def get_time_and_sales(self, window_ms: float = 5000) -> dict[str, Any]:
        now = time.time()
        cutoff = now - window_ms / 1000.0

        buy_vol = 0.0
        sell_vol = 0.0
        trade_count = 0
        burst_prices: list[float] = []

        for trade in self._trade_prints:
            if trade["timestamp"] < cutoff:
                continue
            trade_count += 1
            burst_prices.append(trade["price"])
            if trade["side"] == "buy":
                buy_vol += trade["size"]
            else:
                sell_vol += trade["size"]

        delta = buy_vol - sell_vol
        total_vol = buy_vol + sell_vol
        aggressor_ratio = buy_vol / total_vol if total_vol > 0 else 0.5

        bid_level = self.bids.get(self.best_bid) if self.best_bid > 0 else None
        ask_level = self.asks.get(self.best_ask) if self.best_ask > 0 else None

        absorption_bid = False
        absorption_ask = False
        if bid_level and sell_vol > 0:
            if sell_vol > bid_level.total_size() * 0.5 and self.best_bid > 0:
                absorption_bid = True
        if ask_level and buy_vol > 0:
            if buy_vol > ask_level.total_size() * 0.5 and self.best_ask > 0:
                absorption_ask = True

        trade_burst = trade_count >= _TRADE_BURST_THRESHOLD

        return {
            "buy_volume": round(buy_vol, 1),
            "sell_volume": round(sell_vol, 1),
            "delta": round(delta, 1),
            "aggressor_ratio": round(aggressor_ratio, 3),
            "trade_count": trade_count,
            "trade_burst": trade_burst,
            "absorption_bid": absorption_bid,
            "absorption_ask": absorption_ask,
        }

    def get_order_count(self) -> int:
        return len(self._order_side)

    def get_depth_at_price(self, price: float, side: str) -> float:
        levels = self.bids if side == "bid" else self.asks
        level = levels.get(price)
        return level.total_size() if level else 0.0

    def get_book_snapshot(self, num_levels: int = 5) -> dict[str, Any]:
        top_bids = sorted(self.bids.items(), key=lambda x: -x[0])[:num_levels]
        top_asks = sorted(self.asks.items(), key=lambda x: x[0])[:num_levels]

        def level_info(level: PriceLevel) -> dict[str, Any]:
            return {
                "price": level.price,
                "visible_size": round(level.visible_size, 1),
                "implied_size": round(level.implied_size, 1),
                "order_count": level.order_count,
                "cancel_count": level.cancel_count,
            }

        return {
            "bids": [level_info(lvl) for _, lvl in top_bids],
            "asks": [level_info(lvl) for _, lvl in top_asks],
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
        }


class OrderBookEngine:
    def __init__(self) -> None:
        self._books: dict[str, SymbolBook] = {}

    def get_book(self, symbol: str) -> SymbolBook:
        if symbol not in self._books:
            self._books[symbol] = SymbolBook(symbol)
        return self._books[symbol]

    def process_event(self, symbol: str, event: dict[str, Any]) -> None:
        action = event.get("action", event.get("Action", "")).upper()
        book = self.get_book(symbol)

        timestamp = float(event.get("timestamp", event.get("Timestamp", time.time())))
        order_id = str(event.get("order_id", event.get("OrderId", event.get("order_id_str", ""))))

        if action == "ADD":
            side = event.get("side", event.get("Side", "")).lower()
            price = float(event.get("price", event.get("Price", 0)))
            size = float(event.get("size", event.get("Size", 0)))
            implied = float(event.get("implied_size", event.get("ImpliedSize", 0)))
            book.process_add(order_id, side, price, size, implied, timestamp)

        elif action == "MODIFY":
            new_size = float(event.get("new_size", event.get("Size", 0)))
            new_implied = float(event.get("new_implied", event.get("ImpliedSize", 0)))
            book.process_modify(order_id, new_size, new_implied, timestamp)

        elif action == "CANCEL":
            book.process_cancel(order_id, timestamp)

        elif action == "TRADE":
            aggressor = event.get("side", event.get("Side", "buy")).lower()
            price = float(event.get("price", event.get("Price", 0)))
            size = float(event.get("size", event.get("Size", 0)))
            book.process_trade(aggressor, price, size, timestamp)

    def get_all_queue_stats(self) -> dict[str, dict[str, Any]]:
        return {symbol: book.get_queue_stats() for symbol, book in self._books.items()}

    def get_all_time_and_sales(self, window_ms: float = 5000) -> dict[str, dict[str, Any]]:
        return {symbol: book.get_time_and_sales(window_ms) for symbol, book in self._books.items()}

    def get_status(self) -> dict[str, Any]:
        return {
            "symbols": list(self._books.keys()),
            "order_counts": {s: b.get_order_count() for s, b in self._books.items()},
        }

    def get_naked_pocs(self, symbol: str, current_price: float, tolerance_pips: float = 5.0, pip_size: float = 0.0001) -> list[float]:
        """Find Naked POCs from historical candle data that haven't been re-tested.

        A Naked POC is a previous session's Point of Control that price has not
        returned to touch since that session closed. These act as price magnets.
        """
        naked = []
        try:
            import sqlite3
            from database.setup_db import DB_PATH
            conn = sqlite3.connect(str(DB_PATH), timeout=5)
            rows = conn.execute("""
                SELECT open, high, low, close, volume
                FROM candle_history
                WHERE symbol = ? AND timeframe = 'Daily'
                ORDER BY close_time DESC LIMIT 30
            """, (symbol,)).fetchall()
            conn.close()

            for row in rows:
                _, high, low, close, volume = row
                candle_range = high - low
                if candle_range <= 0 or volume <= 0:
                    continue
                poc_approx = low + candle_range * 0.5
                distance_pips = abs(current_price - poc_approx) / pip_size if pip_size > 0 else 999
                if distance_pips > tolerance_pips:
                    naked.append(poc_approx)
        except Exception:
            pass
        return naked[:10]

    def detect_double_triple_hvn(self, symbol: str, pip_size: float = 0.0001, tolerance_pips: float = 3.0) -> list[dict[str, Any]]:
        """Detect Double/Triple High Volume Nodes across consecutive candles.

        When 2-3 consecutive candles share a volume node at the same price level,
        it represents institutional commitment and acts as strong S/R.
        """
        nodes = []
        try:
            import sqlite3
            from database.setup_db import DB_PATH
            conn = sqlite3.connect(str(DB_PATH), timeout=5)
            rows = conn.execute("""
                SELECT open, high, low, close, volume
                FROM candle_history
                WHERE symbol = ? AND timeframe = '1H'
                ORDER BY close_time DESC LIMIT 20
            """, (symbol,)).fetchall()
            conn.close()

            if len(rows) < 3:
                return nodes

            poc_list = []
            for row in rows:
                _, high, low, close, volume = row
                candle_range = high - low
                if candle_range <= 0 or volume <= 0:
                    poc_list.append(None)
                    continue
                poc = low + candle_range * 0.5
                poc_list.append(poc)

            consecutive = 1
            for i in range(1, len(poc_list)):
                if poc_list[i] is None or poc_list[i-1] is None:
                    consecutive = 1
                    continue
                distance = abs(poc_list[i] - poc_list[i-1]) / pip_size
                if distance < tolerance_pips:
                    consecutive += 1
                    if consecutive >= 2:
                        node_type = "TRIPLE_NODE" if consecutive >= 3 else "DOUBLE_NODE"
                        nodes.append({
                            "price": poc_list[i],
                            "type": node_type,
                            "consecutive": consecutive,
                        })
                else:
                    consecutive = 1
        except Exception:
            pass
        return nodes
