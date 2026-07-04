"""VPIN (Volume-Synchronized Probability of Informed Trading).

Easley, Lopez de Prado, O'Hara (2012) — the gold standard toxicity metric.
VPIN measures the probability that a random trade is informed (toxic).
High VPIN → informed traders are active → adverse selection is high → avoid entry.

Also computes:
- PIN (Probability of Informed Trading) — structural model
- Trade-to-Order Volume Ratio (TOVR) — aggressive trade vol / total order vol
- Cancel-to-Trade Ratio (CTR) — high cancel ratio = likely spoofing/toxic
- Composite Toxicity Score — weighted combination

Designed to operate on the CME MBO data already flowing through OrderBookEngine.
"""
from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.vpin")

VPIN_VOLUME_BUCKET_SIZE = float(os.getenv("VPIN_VOLUME_BUCKET_SIZE", "5000"))
VPIN_LOOKBACK_BUCKETS = int(os.getenv("VPIN_LOOKBACK_BUCKETS", "50"))
VPIN_TOXIC_THRESHOLD = float(os.getenv("VPIN_TOXIC_THRESHOLD", "0.70"))
VPIN_EXTREME_THRESHOLD = float(os.getenv("VPIN_EXTREME_THRESHOLD", "0.90"))
PIN_ALPHA = float(os.getenv("PIN_ALPHA", "0.30"))
PIN_DELTA = float(os.getenv("PIN_DELTA", "0.50"))
PIN_MU = float(os.getenv("PIN_MU", "2.0"))
PIN_EPSILON = float(os.getenv("PIN_EPSILON", "1.0"))
TOVR_WINDOW_MS = float(os.getenv("TOVR_WINDOW_MS", "5000"))
CTR_WINDOW_MS = float(os.getenv("CTR_WINDOW_MS", "5000"))
COMPOSITE_WEIGHTS = {
    "vpin": float(os.getenv("TOXIC_WEIGHT_VPIN", "0.40")),
    "pin": float(os.getenv("TOXIC_WEIGHT_PIN", "0.20")),
    "tovr": float(os.getenv("TOXIC_WEIGHT_TOVR", "0.20")),
    "ctr": float(os.getenv("TOXIC_WEIGHT_CTR", "0.20")),
}


class VPINCalculator:
    """Per-symbol VPIN and toxicity metrics."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._bucket_buy: float = 0.0
        self._bucket_sell: float = 0.0
        self._bucket_total: float = 0.0
        self._completed_buckets: deque[dict[str, float]] = deque(maxlen=VPIN_LOOKBACK_BUCKETS)
        self._vpin: float = 0.0
        self._pin: float = 0.0
        self._tovr: float = 0.0
        self._ctr: float = 0.0
        self._composite: float = 0.0
        self._trade_volume_window: deque[dict[str, Any]] = deque(maxlen=10000)
        self._order_event_window: deque[dict[str, Any]] = deque(maxlen=10000)
        self._buy_volume_total: float = 0.0
        self._sell_volume_total: float = 0.0
        self._no_trade_days: int = 0
        self._trade_days: int = 0

    def on_trade(self, side: str, size: float, timestamp: float) -> None:
        is_buy = 1.0 if side.lower() in ("buy", "bid") else 0.0
        is_sell = 1.0 if side.lower() in ("sell", "ask") else 0.0
        self._trade_volume_window.append({
            "ts": timestamp, "buy_vol": size * is_buy, "sell_vol": size * is_sell, "total": size
        })
        self._buy_volume_total += size * is_buy
        self._sell_volume_total += size * is_sell
        self._accumulate_bucket(size, is_buy, is_sell)

    def on_order_event(self, event_type: str, size: float, timestamp: float) -> None:
        self._order_event_window.append({"ts": timestamp, "type": event_type, "size": size})

    def _accumulate_bucket(self, size: float, is_buy: float, is_sell: float) -> None:
        self._bucket_buy += size * is_buy
        self._bucket_sell += size * is_sell
        self._bucket_total += size
        if self._bucket_total >= VPIN_VOLUME_BUCKET_SIZE:
            self._completed_buckets.append({
                "buy": self._bucket_buy,
                "sell": self._bucket_sell,
                "total": self._bucket_total,
            })
            self._bucket_buy = 0.0
            self._bucket_sell = 0.0
            self._bucket_total = 0.0
            self._compute_vpin()
            self._compute_tovr(timestamp_s=0)
            self._compute_ctr(timestamp_s=0)
            self._compute_composite()

    def _compute_vpin(self) -> None:
        if len(self._completed_buckets) < 5:
            return
        recent = list(self._completed_buckets)[-VPIN_LOOKBACK_BUCKETS:]
        total_vol = sum(b["total"] for b in recent)
        if total_vol <= 0:
            return
        abs_delta = sum(abs(b["buy"] - b["sell"]) for b in recent)
        self._vpin = abs_delta / total_vol

    def _compute_pin(self) -> None:
        alpha = PIN_ALPHA
        mu = PIN_MU
        epsilon = PIN_EPSILON
        denom = alpha * mu + 2 * epsilon
        if denom > 0:
            self._pin = (alpha * mu) / denom
        else:
            self._pin = 0.0

    def _compute_tovr(self, timestamp_s: float) -> None:
        now = timestamp_s if timestamp_s > 0 else 0
        cutoff = now - TOVR_WINDOW_MS / 1000.0
        trade_vol = 0.0
        order_vol = 0.0
        for evt in self._trade_volume_window:
            if evt.get("ts", 0) >= cutoff:
                trade_vol += evt.get("total", 0)
        for evt in self._order_event_window:
            if evt.get("ts", 0) >= cutoff:
                order_vol += evt.get("size", 0)
        self._tovr = trade_vol / max(1.0, order_vol)

    def _compute_ctr(self, timestamp_s: float) -> None:
        now = timestamp_s if timestamp_s > 0 else 0
        cutoff = now - CTR_WINDOW_MS / 1000.0
        cancel_count = 0
        cancel_size = 0.0
        trade_count = 0
        trade_size = 0.0
        for evt in self._order_event_window:
            if evt.get("ts", 0) < cutoff:
                continue
            if evt.get("type") == "CANCEL":
                cancel_count += 1
                cancel_size += evt.get("size", 0)
            elif evt.get("type") == "TRADE":
                trade_count += 1
                trade_size += evt.get("size", 0)
        if trade_count > 0:
            self._ctr = cancel_count / trade_count
        else:
            self._ctr = 0.0

    def _compute_composite(self) -> None:
        self._compute_pin()
        w = COMPOSITE_WEIGHTS
        self._composite = (
            w["vpin"] * min(1.0, self._vpin / VPIN_TOXIC_THRESHOLD)
            + w["pin"] * self._pin
            + w["tovr"] * min(1.0, self._tovr / 2.0)
            + w["ctr"] * min(1.0, self._ctr / 5.0)
        )

    def get_metrics(self) -> dict[str, float]:
        return {
            "vpin": round(self._vpin, 4),
            "pin": round(self._pin, 4),
            "tovr": round(self._tovr, 4),
            "ctr": round(self._ctr, 4),
            "toxicity_composite": round(self._composite, 4),
            "is_toxic": 1.0 if self._vpin >= VPIN_TOXIC_THRESHOLD else 0.0,
            "is_extreme_toxic": 1.0 if self._vpin >= VPIN_EXTREME_THRESHOLD else 0.0,
            "buckets_filled": len(self._completed_buckets),
        }

    def is_toxic(self) -> bool:
        return self._vpin >= VPIN_TOXIC_THRESHOLD

    def is_extreme_toxic(self) -> bool:
        return self._vpin >= VPIN_EXTREME_THRESHOLD


class ToxicityEngine:
    """Multi-symbol toxicity monitor — integrates with OrderBookEngine."""

    def __init__(self) -> None:
        self._calculators: dict[str, VPINCalculator] = {}

    def get_calculator(self, symbol: str) -> VPINCalculator:
        if symbol not in self._calculators:
            self._calculators[symbol] = VPINCalculator(symbol)
        return self._calculators[symbol]

    def on_trade(self, symbol: str, side: str, size: float, timestamp: float) -> None:
        self.get_calculator(symbol).on_trade(side, size, timestamp)

    def on_order_event(self, symbol: str, event_type: str, size: float, timestamp: float) -> None:
        self.get_calculator(symbol).on_order_event(event_type, size, timestamp)

    def get_all_metrics(self) -> dict[str, dict[str, float]]:
        return {sym: calc.get_metrics() for sym, calc in self._calculators.items()}

    def get_toxicity_for_symbol(self, symbol: str) -> dict[str, float]:
        calc = self.get_calculator(symbol)
        return calc.get_metrics()

    def any_symbol_toxic(self) -> bool:
        return any(calc.is_toxic() for calc in self._calculators.values())

    def get_status(self) -> dict[str, Any]:
        metrics = self.get_all_metrics()
        return {
            "symbols": list(self._calculators.keys()),
            "toxic_symbols": [s for s, m in metrics.items() if m.get("is_toxic", 0)],
            "extreme_toxic_symbols": [s for s, m in metrics.items() if m.get("is_extreme_toxic", 0)],
            "max_vpin": max((m["vpin"] for m in metrics.values()), default=0.0),
        }
