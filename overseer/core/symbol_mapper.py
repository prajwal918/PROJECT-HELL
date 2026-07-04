from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "config" / "symbol_map.json"


@lru_cache(maxsize=1)
def load_symbol_map() -> dict[str, dict[str, Any]]:
    if not MAP_PATH.exists():
        return {}
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def resolve_futures_root(symbol: str) -> str:
    if len(symbol) >= 2:
        prefix = symbol[:2]
        symbol_map = load_symbol_map()
        if prefix in symbol_map:
            return prefix
    if len(symbol) >= 3:
        prefix3 = symbol[:3]
        symbol_map = load_symbol_map()
        if prefix3 in symbol_map:
            return prefix3
    return symbol


@lru_cache(maxsize=1)
def get_future_to_spot_and_reverse_map() -> tuple[dict[str, str], dict[str, str]]:
    symbol_map = load_symbol_map()
    future_to_spot = {}
    spot_to_future = {}
    for future, info in symbol_map.items():
        spot = info.get("mt5_symbol")
        if spot:
            future_to_spot[future] = spot
            spot_to_future[spot] = future
    return future_to_spot, spot_to_future


def resolve_counterpart(symbol: str) -> str | None:
    f2s, s2f = get_future_to_spot_and_reverse_map()
    if symbol in f2s:
        return f2s[symbol]
    if symbol in s2f:
        return s2f[symbol]
    root = resolve_futures_root(symbol)
    if root in f2s:
        return f2s[root]
    return None


def resolve_execution_symbol(feed_symbol: str) -> str:
    root = resolve_futures_root(feed_symbol)
    mapping = load_symbol_map().get(root, {})
    return str(mapping.get("mt5_symbol", feed_symbol))


def resolve_direction(feed_symbol: str, raw_direction: str) -> str:
    root = resolve_futures_root(feed_symbol)
    mapping = load_symbol_map().get(root, {})
    direction = raw_direction.upper()
    if mapping.get("inverted"):
        return "SELL" if direction == "BUY" else "BUY"
    return direction


def annotate_tick(tick: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(tick)
    feed_symbol = str(enriched.get("symbol", ""))
    raw_direction = str(enriched.get("direction", "BUY"))
    enriched["feed_symbol"] = feed_symbol
    enriched["execution_symbol"] = resolve_execution_symbol(feed_symbol)
    enriched["direction"] = resolve_direction(feed_symbol, raw_direction)
    return enriched

