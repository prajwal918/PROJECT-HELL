from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.l3_institutional_features import InstitutionalFeatureEngine
from config.instrument_config import InstrumentConfig
from ml.l3_pipeline import (
    FEATURE_NAMES_OUTPUT,
    MODEL_OUTPUT,
    OrderBookState,
    TimeSeriesRoller,
    extract_features,
    load_trained_model,
)

ROLLER_WINDOW = 200
CONFIDENCE_CALIBRATION_WINDOW = 500


class L3RealTimeScorer:
    def __init__(self) -> None:
        self.model = load_trained_model()
        self.books: dict[str, OrderBookState] = defaultdict(OrderBookState)
        self.mid_rollers: dict[str, TimeSeriesRoller] = defaultdict(lambda: TimeSeriesRoller(ROLLER_WINDOW))
        self.spread_rollers: dict[str, TimeSeriesRoller] = defaultdict(lambda: TimeSeriesRoller(ROLLER_WINDOW))
        self.obi_rollers: dict[str, TimeSeriesRoller] = defaultdict(lambda: TimeSeriesRoller(ROLLER_WINDOW))
        self.inst_engines: dict[str, InstitutionalFeatureEngine] = {}
        self.last_updates: dict[str, int] = {}
        self.warm = False
        self.warm_count: dict[str, int] = defaultdict(int)
        self.feature_names: list[str] = []
        self._confidence_history: list[float] = []
        self._correct_predictions: list[bool] = []
        if FEATURE_NAMES_OUTPUT.exists():
            self.feature_names = json.loads(FEATURE_NAMES_OUTPUT.read_text())

    def _get_inst_engine(self, symbol: str) -> InstitutionalFeatureEngine:
        if symbol not in self.inst_engines:
            config = InstrumentConfig.get_instance()
            profile = config.get_profile(symbol)
            self.inst_engines[symbol] = InstitutionalFeatureEngine(tick_size=profile.tick_size)
        return self.inst_engines[symbol]

    @staticmethod
    def _get(obj: dict, *keys, default=0):
        for k in keys:
            if k in obj:
                return obj[k]
        return default

    def _rebuild_book_from_dom(self, symbol: str, dom: dict) -> OrderBookState:
        book = OrderBookState()
        for bid in dom.get("bids", []):
            price = float(self._get(bid, "Price", "price"))
            book.bids[price] = {
                "size": float(self._get(bid, "Size", "size")),
                "number_orders": int(self._get(bid, "NumberOrders", "number_orders", "order_count")),
                "implied_size": float(self._get(bid, "ImpliedSize", "implied_size")),
            }
        for ask in dom.get("asks", []):
            price = float(self._get(ask, "Price", "price"))
            book.asks[price] = {
                "size": float(self._get(ask, "Size", "size")),
                "number_orders": int(self._get(ask, "NumberOrders", "number_orders", "order_count")),
                "implied_size": float(self._get(ask, "ImpliedSize", "implied_size")),
            }
        book.total_bid_size = sum(v["size"] for v in book.bids.values())
        book.total_ask_size = sum(v["size"] for v in book.asks.values())
        return book

    def score(self, tick: dict[str, Any]) -> dict[str, Any]:
        symbol = tick.get("symbol", "?")
        dom = tick.get("dom", {})
        ts = int(tick.get("timestamp", 0))

        book = self._rebuild_book_from_dom(symbol, dom)
        if book.mid_price() <= 0:
            return {"l3_prediction": 0, "l3_confidence": 0.0, "l3_ready": False,
                    "spoof_reversal_signal": 0.0, "spoof_volume_vanished": 0.0,
                    "queue_attrition_pct": 0.0, "queue_absorbed_volume": 0.0,
                    "queue_exhaustion_signal": 0.0, "iceberg_detected": 0.0,
                    "iceberg_replenish_count": 0.0, "iceberg_hidden_depth": 0.0,
                    "adverse_selection_risk": 0.0, "institutional_flight_volume": 0.0,
                    "adverse_selection_ratio": 0.0, "hft_cluster_detected": 0.0,
                    "hft_synchronized_volume": 0.0, "liquidity_vacuum_cv": 0.0,
                    "liquidity_vacuum_signal": 0.0, "vacuum_cascade_depth": 0.0}

        self.books[symbol] = book
        inst_engine = self._get_inst_engine(symbol)
        inst_engine.update_best(book.best_bid(), book.best_ask())
        last_ts = self.last_updates.get(symbol, ts)
        self.last_updates[symbol] = ts

        features = extract_features(
            book, self.mid_rollers[symbol], self.spread_rollers[symbol],
            self.obi_rollers[symbol], last_ts, ts,
        )

        inst_features = inst_engine.get_latest_features()
        features.update(inst_features)

        self.warm_count[symbol] += 1
        # Warm up removed to match standard orderflow readiness
        if self.warm_count[symbol] < 1:
            return {"l3_prediction": 0, "l3_confidence": 0.0, "l3_ready": False, **inst_features}

        self.warm = True

        if self.model is None:
            return {"l3_prediction": 0, "l3_confidence": 0.0, "l3_ready": True, **inst_features}

        cols = self.feature_names if self.feature_names else list(features.keys())
        x = pd.DataFrame([{k: features.get(k, 0.0) for k in cols}])
        x = x.replace([np.inf, -np.inf], np.nan).fillna(0.0)

        if hasattr(self.model, "feature_names_in_"):
            x = x.reindex(columns=list(self.model.feature_names_in_), fill_value=0.0)

        proba = self.model.predict_proba(x)[0]
        pred_class = int(self.model.classes_[proba.argmax()])
        raw_confidence = float(proba.max())
        n_classes = len(self.model.classes_)
        if n_classes == 2:
            prediction = -1 if pred_class == 0 else 1
        elif n_classes == 3:
            prediction_map = {0: -1, 1: 0, 2: 1}
            prediction = prediction_map.get(pred_class, 0)
        else:
            prediction = 1 if pred_class > 0 else -1

        calibrated_confidence = raw_confidence
        if len(self._confidence_history) >= 50:
            avg_conf = sum(self._confidence_history[-100:]) / min(len(self._confidence_history), 100)
            if avg_conf > 0:
                calibrated_confidence = raw_confidence * (0.68 / avg_conf)
            calibrated_confidence = min(1.0, max(0.0, calibrated_confidence))

        self._confidence_history.append(raw_confidence)
        if len(self._confidence_history) > CONFIDENCE_CALIBRATION_WINDOW:
            self._confidence_history = self._confidence_history[-CONFIDENCE_CALIBRATION_WINDOW:]

        return {
            "l3_prediction": prediction,
            "l3_confidence": calibrated_confidence,
            "l3_ready": True,
            **inst_features,
        }

    def process_mbo_event(self, symbol: str, event: dict[str, Any]) -> dict[str, float]:
        engine = self._get_inst_engine(symbol)
        if self.books.get(symbol):
            engine.update_best(self.books[symbol].best_bid(), self.books[symbol].best_ask())
        return engine.process_event(event)

    def signal_bias(self, tick: dict[str, Any]) -> float:
        result = self.score(tick)
        if not result["l3_ready"]:
            return 0.0
        bias = result["l3_prediction"] * result["l3_confidence"]
        spoof_bias = result.get("spoof_reversal_signal", 0.0) * 0.15
        queue_bias = result.get("queue_exhaustion_signal", 0.0) * 0.10
        iceberg_bias = result.get("iceberg_detected", 0.0) * 0.05
        adverse_bias = -result.get("adverse_selection_risk", 0.0) * 0.20
        hft_bias = result.get("hft_cluster_detected", 0.0) * 0.08
        vacuum_bias = -result.get("liquidity_vacuum_signal", 0.0) * 0.12
        total = bias + spoof_bias + queue_bias + iceberg_bias + adverse_bias + hft_bias + vacuum_bias
        return float(np.clip(total, -0.50, 0.50))
