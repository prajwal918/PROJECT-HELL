from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.l3_institutional")

SPOOF_MIN_SIZE = int(os.getenv("SPOOF_MIN_SIZE", "150"))
SPOOF_TICK_DISTANCE = float(os.getenv("SPOOF_TICK_DISTANCE", "0.50"))
TICK_SIZE_DEFAULT = float(os.getenv("TICK_SIZE_DEFAULT", "0.25"))

ICEBERG_REPLENISH_MS = float(os.getenv("ICEBERG_REPLENISH_MS", "1.0"))

QUEUE_EXHAUSTION_MIN_ABSORB = int(os.getenv("QUEUE_EXHAUSTION_MIN_ABSORB", "50"))
QUEUE_EXHAUSTION_ATTRITION_THRESHOLD = float(os.getenv("QUEUE_EXHAUSTION_ATTRITION_THRESHOLD", "0.80"))

ADVERSE_LIFESPAN_THRESHOLD_MS = float(os.getenv("ADVERSE_LIFESPAN_THRESHOLD_MS", "500.0"))
ADVERSE_MIN_SIZE = int(os.getenv("ADVERSE_MIN_SIZE", "50"))
ADVERSE_RISK_CAP = float(os.getenv("ADVERSE_RISK_CAP", "1.0"))

HFT_CLUSTER_MIN_ORDERS = int(os.getenv("HFT_CLUSTER_MIN_ORDERS", "5"))
HFT_BUCKET_US = int(os.getenv("HFT_BUCKET_US", "100"))

VACUUM_WINDOW_MS = float(os.getenv("VACUUM_WINDOW_MS", "50.0"))
VACUUM_CV_THRESHOLD = float(os.getenv("VACUUM_CV_THRESHOLD", "5.0"))
VACUUM_CASCADE_LEVELS = int(os.getenv("VACUUM_CASCADE_LEVELS", "3"))

ASR_LIFESPAN_MS = float(os.getenv("ASR_LIFESPAN_MS", "500.0"))
ASR_MIN_SIZE = int(os.getenv("ASR_MIN_SIZE", "50"))

MAX_REGISTRY_SIZE = int(os.getenv("L3_REGISTRY_MAX_SIZE", "50000"))


class InstitutionalFeatureEngine:
    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size
        self.spoof_registry: dict[str, dict[str, Any]] = {}
        self.queue_absorption: dict[str, dict[str, Any]] = {}
        self.iceberg_last_fill: dict[float, dict[str, Any]] = {}
        self.iceberg_active: dict[float, dict[str, Any]] = {}
        self.order_lifespan: dict[str, dict[str, Any]] = {}
        self.us_clusters: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self.cancel_window: deque[dict[str, Any]] = deque(maxlen=10000)
        self.add_window: deque[dict[str, Any]] = deque(maxlen=10000)
        self.best_bid: float = 0.0
        self.best_ask: float = 0.0
        self.price_level_volume: dict[float, float] = defaultdict(float)
        self.cancel_cascade_depth: int = 0
        self._last_cancel_price: float = 0.0
        self._event_count: int = 0
        self._latest_features: dict[str, float] = {
            "spoof_reversal_signal": 0.0,
            "spoof_volume_vanished": 0.0,
            "queue_attrition_pct": 0.0,
            "queue_absorbed_volume": 0.0,
            "queue_exhaustion_signal": 0.0,
            "iceberg_detected": 0.0,
            "iceberg_replenish_count": 0.0,
            "iceberg_hidden_depth": 0.0,
            "adverse_selection_risk": 0.0,
            "institutional_flight_volume": 0.0,
            "adverse_selection_ratio": 0.0,
            "hft_cluster_detected": 0.0,
            "hft_synchronized_volume": 0.0,
            "liquidity_vacuum_cv": 0.0,
            "liquidity_vacuum_signal": 0.0,
            "vacuum_cascade_depth": 0.0,
        }

    def _current_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def _ms_from_ts(self, ts: int) -> float:
        return ts / 1_000_000.0

    def _cleanup_registries(self) -> None:
        total = (
            len(self.spoof_registry)
            + len(self.queue_absorption)
            + len(self.iceberg_last_fill)
            + len(self.iceberg_active)
            + len(self.order_lifespan)
            + len(self.us_clusters)
        )
        if total < MAX_REGISTRY_SIZE:
            return
        now_ms = time.time() * 1000.0
        cutoff_ms = now_ms - 5000.0
        expired_spoof = [
            oid
            for oid, d in self.spoof_registry.items()
            if self._ms_from_ts(d.get("entry_time_ns", 0)) < cutoff_ms
        ]
        for oid in expired_spoof:
            del self.spoof_registry[oid]
        expired_absorb = [
            oid
            for oid, d in self.queue_absorption.items()
            if self._ms_from_ts(d.get("entry_time_ns", 0)) < cutoff_ms
        ]
        for oid in expired_absorb:
            del self.queue_absorption[oid]
        expired_lifespan = [
            oid
            for oid, d in self.order_lifespan.items()
            if self._ms_from_ts(d.get("entry_time_ns", 0)) < cutoff_ms
        ]
        for oid in expired_lifespan:
            del self.order_lifespan[oid]
        expired_ts = [
            ts
            for ts in list(self.us_clusters.keys())
            if self._ms_from_ts(ts) < cutoff_ms
        ]
        for ts in expired_ts:
            del self.us_clusters[ts]

    def update_best(self, bid: float, ask: float) -> None:
        if bid > 0:
            self.best_bid = bid
        if ask > 0:
            self.best_ask = ask

    def process_event(self, event: dict[str, Any]) -> dict[str, float]:
        action = str(event.get("action", "")).upper()
        order_id = str(event.get("order_id", event.get("exchange_order_id", "")))
        price = float(event.get("price", 0.0))
        size = float(event.get("size", 0.0))
        timestamp_ns = int(event.get("timestamp_ns", event.get("timestamp", self._current_ns())))

        if action in ("ADD",) and size > 0:
            self.add_window.append({"ts_ns": timestamp_ns, "size": size, "price": price})

        self._cleanup_registries()

        features: dict[str, float] = {
            "spoof_reversal_signal": 0.0,
            "spoof_volume_vanished": 0.0,
            "queue_attrition_pct": 0.0,
            "queue_absorbed_volume": 0.0,
            "queue_exhaustion_signal": 0.0,
            "iceberg_detected": 0.0,
            "iceberg_replenish_count": 0.0,
            "iceberg_hidden_depth": 0.0,
            "adverse_selection_risk": 0.0,
            "institutional_flight_volume": 0.0,
            "adverse_selection_ratio": 0.0,
            "hft_cluster_detected": 0.0,
            "hft_synchronized_volume": 0.0,
            "liquidity_vacuum_cv": 0.0,
            "liquidity_vacuum_signal": 0.0,
            "vacuum_cascade_depth": 0.0,
        }

        spoof_f = self._process_spoof(action, order_id, price, size, timestamp_ns)
        features.update(spoof_f)

        queue_f = self._process_queue_exhaustion(action, order_id, price, size, timestamp_ns)
        features.update(queue_f)

        iceberg_f = self._process_iceberg(action, order_id, price, size, timestamp_ns)
        features.update(iceberg_f)

        adverse_f = self._process_adverse_selection(action, order_id, price, size, timestamp_ns)
        features.update(adverse_f)

        hft_f = self._process_hft_synchronicity(action, order_id, price, size, timestamp_ns)
        features.update(hft_f)

        vacuum_f = self._process_liquidity_vacuum(action, order_id, price, size, timestamp_ns)
        features.update(vacuum_f)

        self._latest_features.update(features)
        return features

    def get_latest_features(self) -> dict[str, float]:
        return dict(self._latest_features)

    def _process_spoof(
        self, action: str, order_id: str, price: float, size: float, timestamp_ns: int
    ) -> dict[str, float]:
        features: dict[str, float] = {
            "spoof_reversal_signal": 0.0,
            "spoof_volume_vanished": 0.0,
        }

        if action == "ADD" and size >= SPOOF_MIN_SIZE:
            self.spoof_registry[order_id] = {
                "price": price,
                "initial_size": size,
                "entry_time_ns": timestamp_ns,
            }
            return features

        if action == "CANCEL" and order_id in self.spoof_registry:
            tracked = self.spoof_registry[order_id]
            ref_price = self.best_bid if price <= self.best_bid else self.best_ask
            tick_distance = abs(ref_price - tracked["price"]) if ref_price > 0 else abs(price - tracked["price"])
            if tick_distance <= SPOOF_TICK_DISTANCE * self.tick_size / 0.25:
                features["spoof_reversal_signal"] = 1.0
                features["spoof_volume_vanished"] = tracked["initial_size"]
            del self.spoof_registry[order_id]

        elif action in ("FILL", "PARTIAL_FILL") and order_id in self.spoof_registry:
            del self.spoof_registry[order_id]

        return features

    def _process_queue_exhaustion(
        self, action: str, order_id: str, price: float, size: float, timestamp_ns: int
    ) -> dict[str, float]:
        features: dict[str, float] = {
            "queue_attrition_pct": 0.0,
            "queue_absorbed_volume": 0.0,
            "queue_exhaustion_signal": 0.0,
        }

        if action == "ADD" and size >= QUEUE_EXHAUSTION_MIN_ABSORB:
            is_at_best = (
                abs(price - self.best_bid) < self.tick_size
                or abs(price - self.best_ask) < self.tick_size
            )
            if is_at_best:
                self.queue_absorption[order_id] = {
                    "price": price,
                    "initial_size": size,
                    "remaining_size": size,
                    "total_absorbed": 0.0,
                    "entry_time_ns": timestamp_ns,
                    "modify_count": 0,
                }
            return features

        if order_id not in self.queue_absorption:
            return features

        tracked = self.queue_absorption[order_id]

        if action == "MODIFY" and size > 0:
            delta = size - tracked["remaining_size"]
            if delta > 0:
                tracked["total_absorbed"] += delta
                tracked["remaining_size"] = size
                tracked["modify_count"] += 1

            attrition = tracked["total_absorbed"] / tracked["initial_size"] if tracked["initial_size"] > 0 else 0.0
            features["queue_attrition_pct"] = min(1.0, attrition)
            features["queue_absorbed_volume"] = tracked["total_absorbed"]
            if attrition >= QUEUE_EXHAUSTION_ATTRITION_THRESHOLD and tracked["modify_count"] >= 2:
                features["queue_exhaustion_signal"] = 1.0

        elif action in ("FILL", "PARTIAL_FILL"):
            fill_amount = min(size, tracked["remaining_size"])
            tracked["total_absorbed"] += fill_amount
            tracked["remaining_size"] -= fill_amount
            if tracked["remaining_size"] <= 0:
                attrition = tracked["total_absorbed"] / tracked["initial_size"] if tracked["initial_size"] > 0 else 0.0
                features["queue_attrition_pct"] = min(1.0, attrition)
                features["queue_absorbed_volume"] = tracked["total_absorbed"]
                if attrition >= QUEUE_EXHAUSTION_ATTRITION_THRESHOLD:
                    features["queue_exhaustion_signal"] = 1.0
                del self.queue_absorption[order_id]
            else:
                features["queue_attrition_pct"] = min(
                    1.0, tracked["total_absorbed"] / tracked["initial_size"]
                )
                features["queue_absorbed_volume"] = tracked["total_absorbed"]

        elif action == "CANCEL":
            del self.queue_absorption[order_id]

        return features

    def _process_iceberg(
        self, action: str, order_id: str, price: float, size: float, timestamp_ns: int
    ) -> dict[str, float]:
        features: dict[str, float] = {
            "iceberg_detected": 0.0,
            "iceberg_replenish_count": 0.0,
            "iceberg_hidden_depth": 0.0,
        }

        if action in ("FILL", "PARTIAL_FILL") and size > 0:
            self.iceberg_last_fill[price] = {
                "timestamp_ns": timestamp_ns,
                "filled_size": size,
                "order_id": order_id,
            }

        elif action == "ADD" and price in self.iceberg_last_fill:
            fill_meta = self.iceberg_last_fill[price]
            time_delta_ms = (timestamp_ns - fill_meta["timestamp_ns"]) / 1_000_000.0

            if time_delta_ms <= ICEBERG_REPLENISH_MS and abs(size - fill_meta["filled_size"]) < 1.0:
                if price not in self.iceberg_active:
                    self.iceberg_active[price] = {
                        "replenishment_count": 1,
                        "total_hidden_volume": fill_meta["filled_size"],
                    }
                else:
                    self.iceberg_active[price]["replenishment_count"] += 1
                    self.iceberg_active[price]["total_hidden_volume"] += fill_meta["filled_size"]

                features["iceberg_detected"] = 1.0
                features["iceberg_replenish_count"] = float(
                    self.iceberg_active[price]["replenishment_count"]
                )
                features["iceberg_hidden_depth"] = float(
                    self.iceberg_active[price]["total_hidden_volume"]
                )
            elif time_delta_ms > ICEBERG_REPLENISH_MS * 10:
                if price in self.iceberg_active:
                    del self.iceberg_active[price]

            del self.iceberg_last_fill[price]

        return features

    def _process_adverse_selection(
        self, action: str, order_id: str, price: float, size: float, timestamp_ns: int
    ) -> dict[str, float]:
        features: dict[str, float] = {
            "adverse_selection_risk": 0.0,
            "institutional_flight_volume": 0.0,
            "adverse_selection_ratio": 0.0,
        }

        if action == "ADD":
            self.order_lifespan[order_id] = {
                "entry_time_ns": timestamp_ns,
                "size": size,
                "price": price,
            }
            self.price_level_volume[price] = self.price_level_volume.get(price, 0.0) + size
            return features

        if action == "CANCEL" and (price == self.best_bid or price == self.best_ask) and order_id in self.order_lifespan:
            order_data = self.order_lifespan[order_id]
            order_age_ms = (timestamp_ns - order_data["entry_time_ns"]) / 1_000_000.0

            if order_age_ms >= ADVERSE_LIFESPAN_THRESHOLD_MS and order_data["size"] >= ADVERSE_MIN_SIZE:
                features["institutional_flight_volume"] = order_data["size"]
                age_weight = min(
                    ADVERSE_RISK_CAP,
                    (order_age_ms / ADVERSE_LIFESPAN_THRESHOLD_MS) * 0.2,
                )
                features["adverse_selection_risk"] = age_weight

            total_at_level = self.price_level_volume.get(price, 0.0)
            if total_at_level > 0 and order_data["size"] >= ASR_MIN_SIZE and order_age_ms >= ASR_LIFESPAN_MS:
                features["adverse_selection_ratio"] = min(1.0, order_data["size"] / total_at_level)

            self.price_level_volume[price] = max(0.0, self.price_level_volume.get(price, 0.0) - order_data["size"])
            del self.order_lifespan[order_id]

        elif action in ("FILL", "PARTIAL_FILL") and order_id in self.order_lifespan:
            old_size = self.order_lifespan[order_id].get("size", 0.0)
            self.price_level_volume[price] = max(0.0, self.price_level_volume.get(price, 0.0) - min(size, old_size))
            del self.order_lifespan[order_id]

        return features

    def _process_hft_synchronicity(
        self, action: str, order_id: str, price: float, size: float, timestamp_ns: int
    ) -> dict[str, float]:
        features: dict[str, float] = {
            "hft_cluster_detected": 0.0,
            "hft_synchronized_volume": 0.0,
        }

        bucket_us = timestamp_ns // (HFT_BUCKET_US * 1_000)
        self.us_clusters[bucket_us].append(
            {"order_id": order_id, "size": size, "action": action, "price": price}
        )

        cluster = self.us_clusters[bucket_us]
        if len(cluster) >= HFT_CLUSTER_MIN_ORDERS:
            action_types: set[str] = {item["action"] for item in cluster}
            if len(action_types) == 1:
                features["hft_cluster_detected"] = 1.0
                features["hft_synchronized_volume"] = float(sum(item["size"] for item in cluster))

        return features

    def _process_liquidity_vacuum(
        self, action: str, order_id: str, price: float, size: float, timestamp_ns: int
    ) -> dict[str, float]:
        features: dict[str, float] = {
            "liquidity_vacuum_cv": 0.0,
            "liquidity_vacuum_signal": 0.0,
            "vacuum_cascade_depth": 0.0,
        }

        if action == "CANCEL":
            self.cancel_window.append({"ts_ns": timestamp_ns, "size": size, "price": price})
            if self._last_cancel_price > 0 and price > 0:
                level_distance = abs(price - self._last_cancel_price) / self.tick_size if self.tick_size > 0 else 0
                if 0 < level_distance <= VACUUM_CASCADE_LEVELS:
                    self.cancel_cascade_depth += 1
                else:
                    self.cancel_cascade_depth = 1
            else:
                self.cancel_cascade_depth = max(1, self.cancel_cascade_depth)
            self._last_cancel_price = price
            features["vacuum_cascade_depth"] = float(self.cancel_cascade_depth)

        if len(self.cancel_window) < 5 or len(self.add_window) < 5:
            return features

        window_ns = int(VACUUM_WINDOW_MS * 1_000_000)
        now_ns = timestamp_ns

        recent_cancels = sum(
            1 for evt in self.cancel_window if (now_ns - evt["ts_ns"]) <= window_ns
        )
        recent_adds = sum(
            1 for evt in self.add_window if (now_ns - evt["ts_ns"]) <= window_ns
        )

        if recent_adds > 0:
            cv = recent_cancels / recent_adds
        elif recent_cancels > 0:
            cv = float(recent_cancels) * 10.0
        else:
            cv = 0.0

        features["liquidity_vacuum_cv"] = min(cv, 20.0)
        if cv > VACUUM_CV_THRESHOLD:
            features["liquidity_vacuum_signal"] = 1.0

        if self.cancel_cascade_depth >= VACUUM_CASCADE_LEVELS:
            features["liquidity_vacuum_signal"] = 1.0

        return features

    def get_all_feature_names(self) -> list[str]:
        return [
            "spoof_reversal_signal",
            "spoof_volume_vanished",
            "queue_attrition_pct",
            "queue_absorbed_volume",
            "queue_exhaustion_signal",
            "iceberg_detected",
            "iceberg_replenish_count",
            "iceberg_hidden_depth",
            "adverse_selection_risk",
            "institutional_flight_volume",
            "adverse_selection_ratio",
            "hft_cluster_detected",
            "hft_synchronized_volume",
            "liquidity_vacuum_cv",
            "liquidity_vacuum_signal",
            "vacuum_cascade_depth",
        ]

    def reset(self) -> None:
        self.spoof_registry.clear()
        self.queue_absorption.clear()
        self.iceberg_last_fill.clear()
        self.iceberg_active.clear()
        self.order_lifespan.clear()
        self.us_clusters.clear()
        self.cancel_window.clear()
        self.add_window.clear()
        self.price_level_volume.clear()
        self.cancel_cascade_depth = 0
        self._last_cancel_price = 0.0
        self._event_count = 0
        self._latest_features = {k: 0.0 for k in self._latest_features}
