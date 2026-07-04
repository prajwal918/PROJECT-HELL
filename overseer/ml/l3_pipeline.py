from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.metrics import accuracy_score, classification_report, log_loss
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier

LOGGER = logging.getLogger("overseer.l3_pipeline")

ROOT = Path(__file__).resolve().parents[1]
JSONL_PATH = ROOT / "logs" / "quantower_l3_raw.jsonl"
MODEL_OUTPUT = Path(__file__).resolve().parent / "l3_xgb_model.pkl"
FEATURE_NAMES_OUTPUT = Path(__file__).resolve().parent / "l3_feature_names.json"
INST_MODEL_OUTPUT = Path(__file__).resolve().parent / "l3_institutional_model.pkl"
INST_FEATURE_NAMES_OUTPUT = Path(__file__).resolve().parent / "l3_institutional_feature_names.json"
WFO_METRICS_OUTPUT = Path(__file__).resolve().parent / "l3_wfo_metrics.json"
SHAP_OUTPUT = Path(__file__).resolve().parent / "l3_shap_importance.json"

TICK_FORWARD = int(os.getenv("L3_TICK_FORWARD", "50"))
WINDOW_EVENTS = int(os.getenv("L3_WINDOW_EVENTS", "200"))
FLAT_ZONE_BPS = float(os.getenv("L3_FLAT_ZONE_BPS", "0.1"))
SAMPLE_LIMIT = int(os.getenv("L3_SAMPLE_LIMIT", "0"))

WFO_SPLITS = int(os.getenv("WFO_SPLITS", "5"))
WFO_MIN_TRADES = int(os.getenv("WFO_MIN_TRADES", "20"))
ML_CONFIDENCE_THRESHOLD = float(os.getenv("ML_CONFIDENCE_THRESHOLD", "0.68"))
WFO_PURGE_EVENTS = int(os.getenv("WFO_PURGE_EVENTS", "50"))
WFO_EARLY_STOPPING_ROUNDS = int(os.getenv("WFO_EARLY_STOPPING_ROUNDS", "30"))
FEATURE_IMPORTANCE_THRESHOLD = float(os.getenv("FEATURE_IMPORTANCE_THRESHOLD", "0.001"))
MODEL_DECAY_THRESHOLD = float(os.getenv("MODEL_DECAY_THRESHOLD", "0.05"))

EXCLUDE_DOM_COUNT = int(os.getenv("L3_EXCLUDE_DOM_COUNT", "0"))
EXCLUDE_DOM_TOP = int(os.getenv("L3_EXCLUDE_DOM_TOP", "0"))


def _parse_event(line: str) -> dict[str, Any] | None:
    try:
        evt = json.loads(line)
    except json.JSONDecodeError:
        return None
    quote = evt.get("quote")
    if not isinstance(quote, dict):
        return None
    side = evt.get("quotePriceType")
    if side not in ("Bid", "Ask"):
        return None
    return {
        "symbol": evt.get("symbol", "?"),
        "timestamp": int(evt.get("timestamp", 0)),
        "side": side,
        "price": float(quote.get("Price", 0.0)),
        "size": float(quote.get("Size", 0.0)),
        "number_orders": int(quote.get("NumberOrders", 0)),
        "implied_size": float(quote.get("ImpliedSize", 0.0)),
        "id": str(quote.get("Id", "")),
        "action": evt.get("action", "ADD"),
        "order_id": str(quote.get("Id", evt.get("exchange_order_id", ""))),
    }


class OrderBookState:
    def __init__(self) -> None:
        self.bids: dict[float, dict[str, float]] = {}
        self.asks: dict[float, dict[str, float]] = {}
        self._bid_sorted: list[float] = []
        self._ask_sorted: list[float] = []
        self.last_update_ns = 0
        self.total_bid_size: float = 0.0
        self.total_ask_size: float = 0.0
        self.bid_order_count: int = 0
        self.ask_order_count: int = 0

    def apply(self, event: dict[str, Any]) -> None:
        side_dict = self.bids if event["side"] == "Bid" else self.asks
        price = event["price"]
        size = event["size"]
        old = side_dict.get(price, {})
        old_size = old.get("size", 0.0)
        if size <= 0:
            side_dict.pop(price, None)
        else:
            side_dict[price] = {
                "size": size,
                "number_orders": event["number_orders"],
                "implied_size": event["implied_size"],
            }
        if event["side"] == "Bid":
            self.total_bid_size += size - old_size
        else:
            self.total_ask_size += size - old_size
        self.last_update_ns = event["timestamp"]

    def _ensure_sorted(self) -> None:
        self._bid_sorted = sorted(self.bids.keys(), reverse=True)
        self._ask_sorted = sorted(self.asks.keys())

    def best_bid(self) -> float:
        self._ensure_sorted()
        return self._bid_sorted[0] if self._bid_sorted else 0.0

    def best_ask(self) -> float:
        self._ensure_sorted()
        return self._ask_sorted[0] if self._ask_sorted else 0.0

    def mid_price(self) -> float:
        bb = self.best_bid()
        ba = self.best_ask()
        if bb <= 0 or ba <= 0:
            return 0.0
        return (bb + ba) / 2.0

    def spread(self) -> float:
        bb = self.best_bid()
        ba = self.best_ask()
        if bb <= 0 or ba <= 0:
            return 0.0
        return ba - bb

    def spread_bps(self) -> float:
        mid = self.mid_price()
        if mid <= 0:
            return 0.0
        return (self.spread() / mid) * 10000.0

    def depth_size(self, levels: int = 3, side: str = "Bid") -> float:
        self._ensure_sorted()
        src = self._bid_sorted if side == "Bid" else self._ask_sorted
        total = 0.0
        for i, price in enumerate(src[:levels]):
            entry = (self.bids if side == "Bid" else self.asks).get(price, {})
            total += entry.get("size", 0.0)
        return total

    def depth_order_count(self, levels: int = 3, side: str = "Bid") -> int:
        self._ensure_sorted()
        src = self._bid_sorted if side == "Bid" else self._ask_sorted
        total = 0
        for i, price in enumerate(src[:levels]):
            entry = (self.bids if side == "Bid" else self.asks).get(price, {})
            total += int(entry.get("number_orders", 0))
        return total

    def depth_implied(self, levels: int = 3, side: str = "Bid") -> float:
        self._ensure_sorted()
        src = self._bid_sorted if side == "Bid" else self._ask_sorted
        total = 0.0
        for i, price in enumerate(src[:levels]):
            entry = (self.bids if side == "Bid" else self.asks).get(price, {})
            total += entry.get("implied_size", 0.0)
        return total

    def obi(self, levels: int = 3) -> float:
        bid_depth = self.depth_size(levels, "Bid")
        ask_depth = self.depth_size(levels, "Ask")
        total = bid_depth + ask_depth
        if total <= 0:
            return 0.0
        return (bid_depth - ask_depth) / total

    def obi_weighted(self, levels: int = 3) -> float:
        self._ensure_sorted()
        bid_weighted = 0.0
        ask_weighted = 0.0
        for i, price in enumerate(self._bid_sorted[:levels]):
            entry = self.bids.get(price, {})
            bid_weighted += entry.get("size", 0.0) * (levels - i)
        for i, price in enumerate(self._ask_sorted[:levels]):
            entry = self.asks.get(price, {})
            ask_weighted += entry.get("size", 0.0) * (levels - i)
        total = bid_weighted + ask_weighted
        if total <= 0:
            return 0.0
        return (bid_weighted - ask_weighted) / total

    def order_count_imbalance(self) -> float:
        total = self.bid_order_count + self.ask_order_count
        if total <= 0:
            self.bid_order_count = self.depth_order_count(99, "Bid")
            self.ask_order_count = self.depth_order_count(99, "Ask")
            total = self.bid_order_count + self.ask_order_count
        if total <= 0:
            return 0.0
        return (self.bid_order_count - self.ask_order_count) / total

    def implied_imbalance(self, levels: int = 3) -> float:
        bid_imp = self.depth_implied(levels, "Bid")
        ask_imp = self.depth_implied(levels, "Ask")
        total = bid_imp + ask_imp
        if total <= 0:
            return 0.0
        return (bid_imp - ask_imp) / total

    def large_block_ratio(self, threshold_mult: float = 3.0, levels: int = 5) -> float:
        self._ensure_sorted()
        all_sizes = []
        for side_list, side_dict in [(self._bid_sorted, self.bids), (self._ask_sorted, self.asks)]:
            for price in side_list[:levels]:
                entry = side_dict.get(price, {})
                sz = entry.get("size", 0.0)
                if sz > 0:
                    all_sizes.append(sz)
        if not all_sizes:
            return 0.0
        mean_sz = np.mean(all_sizes)
        if mean_sz <= 0:
            return 0.0
        large_count = sum(1 for s in all_sizes if s > mean_sz * threshold_mult)
        return large_count / len(all_sizes)

    def top_level_concentration(self, levels: int = 5) -> float:
        bid_top = self.depth_size(1, "Bid")
        ask_top = self.depth_size(1, "Ask")
        bid_total = self.depth_size(levels, "Bid")
        ask_total = self.depth_size(levels, "Ask")
        bid_conc = bid_top / bid_total if bid_total > 0 else 0.0
        ask_conc = ask_top / ask_total if ask_total > 0 else 0.0
        return (bid_conc + ask_conc) / 2.0


class TimeSeriesRoller:
    def __init__(self, window: int) -> None:
        self.window = window
        self._buffer: list[float] = []

    def push(self, value: float) -> None:
        self._buffer.append(value)
        if len(self._buffer) > self.window:
            self._buffer.pop(0)

    def mean(self) -> float:
        if not self._buffer:
            return 0.0
        return float(np.mean(self._buffer))

    def std(self) -> float:
        if len(self._buffer) < 2:
            return 0.0
        return float(np.std(self._buffer, ddof=1))

    def zscore(self, value: float) -> float:
        s = self.std()
        if s <= 0:
            return 0.0
        return (value - self.mean()) / s

    def latest(self) -> float:
        return self._buffer[-1] if self._buffer else 0.0

    def slope(self, n: int = 5) -> float:
        if len(self._buffer) < max(n, 2):
            return 0.0
        recent = self._buffer[-n:]
        x = np.arange(len(recent))
        if np.std(x) == 0:
            return 0.0
        return float(np.polyfit(x, recent, 1)[0])

    def full(self) -> bool:
        return len(self._buffer) >= self.window


class PurgedTimeSeriesSplit:
    def __init__(self, n_splits: int = 5, purge_events: int = WFO_PURGE_EVENTS) -> None:
        self.n_splits = n_splits
        self.purge_events = purge_events

    def split(self, x: pd.DataFrame) -> Any:
        n = len(x)
        fold_size = n // (self.n_splits + 1)
        for i in range(self.n_splits):
            train_end = fold_size * (i + 1)
            val_start = train_end + self.purge_events
            val_end = min(fold_size * (i + 2), n)
            if val_start >= val_end:
                continue
            train_idx = np.arange(0, train_end)
            val_idx = np.arange(val_start, val_end)
            yield train_idx, val_idx

    def get_n_splits(self) -> int:
        return self.n_splits


def compute_shap_importance(model: XGBClassifier, x_val: pd.DataFrame,
                            max_samples: int = 5000) -> dict[str, float]:
    try:
        import shap
    except ImportError:
        LOGGER.warning("shap not installed — skipping SHAP analysis")
        return {}
    sample = x_val
    if len(x_val) > max_samples:
        sample = x_val.sample(n=max_samples, random_state=42)
    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(sample)
    except Exception as exc:
        LOGGER.warning("SHAP computation failed: %s", exc)
        return {}
    if isinstance(shap_values, list):
        shap_values = shap_values[-1]
    mean_abs = np.abs(shap_values).mean(axis=0)
    feature_names = list(sample.columns)
    result = {feature_names[i]: float(mean_abs[i]) for i in range(len(feature_names))}
    sorted_result = dict(sorted(result.items(), key=lambda kv: kv[1], reverse=True))
    return sorted_result


def detect_model_decay(prev_metrics: dict | None, current_accuracy: float,
                       threshold: float = MODEL_DECAY_THRESHOLD) -> dict[str, Any]:
    if prev_metrics is None:
        return {"decayed": False, "delta": 0.0, "prev_accuracy": None, "current_accuracy": current_accuracy}
    prev_acc = prev_metrics.get("mean_accuracy", prev_metrics.get("oos_accuracy", 0.0))
    delta = prev_acc - current_accuracy
    decayed = delta > threshold
    return {
        "decayed": decayed,
        "delta": float(delta),
        "prev_accuracy": float(prev_acc),
        "current_accuracy": float(current_accuracy),
        "threshold": float(threshold),
    }


def prune_features(feature_cols: list[str], importances: dict[str, float],
                   threshold: float = FEATURE_IMPORTANCE_THRESHOLD) -> list[str]:
    return [f for f in feature_cols if importances.get(f, 0.0) >= threshold]


def extract_features(book: OrderBookState, mid_roller: TimeSeriesRoller,
                     spread_roller: TimeSeriesRoller,
                     obi_roller: TimeSeriesRoller,
                     last_book_update: int,
                     current_ts: int) -> dict[str, float]:
    mid = book.mid_price()
    spread_bps = book.spread_bps()
    mid_roller.push(mid)
    spread_roller.push(spread_bps)
    obi_3 = book.obi(levels=3)
    obi_5 = book.obi(levels=5)
    obi_10 = book.obi(levels=10)
    obi_roller.push(obi_5)
    
    # Identify if this is a spot Forex symbol (thin DOM book with only 1 level)
    is_forex_spot = 1.0 if len(book.bids) <= 1 and len(book.asks) <= 1 else 0.0
    
    features: dict[str, float] = {
        "obi_3": obi_3,
        "obi_5": obi_5,
        "obi_10": obi_10,
        "obi_weighted_3": book.obi_weighted(3),
        "obi_weighted_5": book.obi_weighted(5),
        "spread_bps": spread_bps,
        "depth_bid_1": book.depth_size(1, "Bid"),
        "depth_ask_1": book.depth_size(1, "Ask"),
        "depth_bid_3": book.depth_size(3, "Bid"),
        "depth_ask_3": book.depth_size(3, "Ask"),
        "depth_bid_5": book.depth_size(5, "Bid"),
        "depth_ask_5": book.depth_size(5, "Ask"),
        "order_count_bid_3": float(book.depth_order_count(3, "Bid")),
        "order_count_ask_3": float(book.depth_order_count(3, "Ask")),
        "order_count_imb": book.order_count_imbalance(),
        "implied_bid_3": book.depth_implied(3, "Bid"),
        "implied_ask_3": book.depth_implied(3, "Ask"),
        "implied_imb": book.implied_imbalance(3),
        "large_block_ratio": book.large_block_ratio(3.0, 5),
        "top_concentration": book.top_level_concentration(5),
        "mid_velocity": mid_roller.slope(5),
        "mid_accel": mid_roller.slope(10),
        "mid_zscore": mid_roller.zscore(mid),
        "spread_zscore": spread_roller.zscore(spread_bps),
        "obi_zscore": obi_roller.zscore(obi_5),
        "obi_ma_5": obi_roller.mean(),
        "time_since_update_ms": float(current_ts - last_book_update),
        "is_forex_spot": is_forex_spot,
    }
    if mid_roller.full() and spread_roller.full():
        features["mid_volatility"] = mid_roller.std()
        features["spread_volatility"] = spread_roller.std()
    else:
        features["mid_volatility"] = 0.0
        features["spread_volatility"] = 0.0
    return features


def label_target(future_mids: list[float], entry_mid: float, flat_zone_bps: float) -> int:
    if not future_mids:
        return 0
    future_mid = np.mean(future_mids)
    if entry_mid <= 0:
        return 0
    change_bps = ((future_mid - entry_mid) / entry_mid) * 10000.0
    if change_bps > flat_zone_bps:
        return 1
    if change_bps < -flat_zone_bps:
        return -1
    return 0


def events_to_dataframe(jsonl_path: Path, symbol_filter: str | None = None,
                        tick_forward: int = TICK_FORWARD,
                        window: int = WINDOW_EVENTS,
                        flat_zone_bps: float = FLAT_ZONE_BPS,
                        sample_limit: int = SAMPLE_LIMIT) -> pd.DataFrame:
    from ml.l3_institutional_features import InstitutionalFeatureEngine

    books: dict[str, OrderBookState] = defaultdict(OrderBookState)
    mid_rollers: dict[str, TimeSeriesRoller] = defaultdict(lambda: TimeSeriesRoller(window))
    spread_rollers: dict[str, TimeSeriesRoller] = defaultdict(lambda: TimeSeriesRoller(window))
    obi_rollers: dict[str, TimeSeriesRoller] = defaultdict(lambda: TimeSeriesRoller(window))
    inst_engines: dict[str, InstitutionalFeatureEngine] = defaultdict(InstitutionalFeatureEngine)
    pending: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows: list[dict[str, Any]] = []
    processed = 0

    with open(jsonl_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            evt = _parse_event(line)
            if evt is None:
                continue
            symbol = evt["symbol"]
            if symbol_filter and symbol != symbol_filter:
                continue

            mid_before = books[symbol].mid_price()

            books[symbol].apply(evt)
            inst_engines[symbol].update_best(books[symbol].best_bid(), books[symbol].best_ask())

            mid_after = books[symbol].mid_price()
            if mid_after <= 0:
                continue

            inst_features = inst_engines[symbol].process_event({
                "action": evt.get("action", "ADD"),
                "order_id": evt.get("order_id", ""),
                "price": evt["price"],
                "size": evt["size"],
                "timestamp_ns": evt["timestamp"],
            })

            features = extract_features(
                books[symbol], mid_rollers[symbol], spread_rollers[symbol],
                obi_rollers[symbol], books[symbol].last_update_ns, evt["timestamp"],
            )
            features.update(inst_features)

            pending[symbol].append({
                "features": dict(features),
                "entry_mid": mid_after,
                "symbol": symbol,
            })

            while len(pending[symbol]) > tick_forward + 1:
                entry = pending[symbol].pop(0)
                future_mids = [
                    pending[symbol][j]["entry_mid"]
                    for j in range(min(tick_forward, len(pending[symbol])))
                ]
                target = label_target(future_mids, entry["entry_mid"], flat_zone_bps)
                row = entry["features"]
                row["symbol"] = entry["symbol"]
                row["mid_price"] = entry["entry_mid"]
                row["target"] = target
                rows.append(row)
                processed += 1
                if sample_limit > 0 and processed >= sample_limit:
                    return pd.DataFrame(rows)

    for symbol, entries in pending.items():
        for i, entry in enumerate(entries):
            remaining = len(entries) - i - 1
            if remaining < 1:
                break
            future_mids = [
                entries[j]["entry_mid"]
                for j in range(i + 1, min(i + 1 + tick_forward, len(entries)))
            ]
            target = label_target(future_mids, entry["entry_mid"], flat_zone_bps)
            row = entry["features"]
            row["symbol"] = entry["symbol"]
            row["mid_price"] = entry["entry_mid"]
            row["target"] = target
            rows.append(row)
            processed += 1
            if sample_limit > 0 and processed >= sample_limit:
                break

    return pd.DataFrame(rows)


def walk_forward_train(df: pd.DataFrame, feature_cols: list[str],
                       target_col: str = "target",
                       n_splits: int = WFO_SPLITS,
                       confidence_threshold: float = ML_CONFIDENCE_THRESHOLD,
                       purge_events: int = WFO_PURGE_EVENTS,
                       early_stopping_rounds: int = WFO_EARLY_STOPPING_ROUNDS) -> tuple[XGBClassifier, list[str], dict]:
    y = df[target_col].values
    label_map = {v: i for i, v in enumerate(sorted(np.unique(y)))}
    y_encoded = np.array([label_map[v] for v in y])
    reverse_label = {i: v for v, i in label_map.items()}
    n_classes = len(label_map)
    print(f"Label mapping: {label_map}")
    unique_classes = np.unique(y_encoded)
    if len(unique_classes) < 2:
        raise RuntimeError("Target has only one class. Cannot train.")
    x = df[feature_cols].copy()
    x = x.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    purged_cv = PurgedTimeSeriesSplit(n_splits=n_splits, purge_events=purge_events)
    actual_splits = list(purged_cv.split(x))
    if not actual_splits:
        LOGGER.warning("Purged split produced no folds — falling back to TimeSeriesSplit")
        actual_splits = list(TimeSeriesSplit(n_splits=min(n_splits, len(y_encoded) // 100)).split(x))

    base_params = {
        "n_estimators": 500,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "eval_metric": "mlogloss",
        "random_state": 42,
        "n_jobs": -1,
        "early_stopping_rounds": early_stopping_rounds,
    }
    if n_classes == 2:
        base_params["objective"] = "binary:logistic"
    else:
        base_params["objective"] = "multi:softprob"
        base_params["num_class"] = n_classes

    fold_accuracies: list[float] = []
    fold_logloss: list[float] = []
    fold_reports: list[dict] = []
    fold_best_iterations: list[int] = []
    shap_importance_global: dict[str, float] = {}
    last_val_x: pd.DataFrame | None = None
    best_fold_model: XGBClassifier | None = None
    best_fold_acc: float = 0.0

    for fold_idx, (train_idx, val_idx) in enumerate(actual_splits):
        x_train_raw, x_val = x.iloc[train_idx], x.iloc[val_idx]
        y_train_raw, y_val = y_encoded[train_idx], y_encoded[val_idx]
        minority_count = min(np.bincount(y_train_raw))
        k_neighbors = max(1, min(5, minority_count - 1))
        try:
            smote = SMOTE(k_neighbors=k_neighbors, random_state=42)
            x_train, y_train = smote.fit_resample(x_train_raw, y_train_raw)
        except (ValueError, RuntimeError):
            x_train, y_train = x_train_raw, y_train_raw
        fold_model = XGBClassifier(**base_params)
        fold_model.fit(
            x_train, y_train,
            eval_set=[(x_val, y_val)],
            verbose=False,
        )
        y_pred = fold_model.predict(x_val)
        y_proba = fold_model.predict_proba(x_val)
        acc = float(np.mean(y_pred == y_val))
        try:
            ll = float(log_loss(y_val, y_proba))
        except Exception:
            ll = float("inf")
        fold_accuracies.append(acc)
        fold_logloss.append(ll)
        best_iter = fold_model.best_iteration if hasattr(fold_model, "best_iteration") and fold_model.best_iteration > 0 else base_params["n_estimators"]
        fold_best_iterations.append(best_iter)
        report = classification_report(y_val, y_pred, output_dict=True, zero_division=0)
        fold_reports.append(report)
        print(f"WFO Fold {fold_idx + 1}/{len(actual_splits)} OOS Acc={acc:.4f} LogLoss={ll:.4f} BestIter={best_iter}")
        if acc > best_fold_acc:
            best_fold_acc = acc
            best_fold_model = fold_model
        last_val_x = x_val

    mean_acc = float(np.mean(fold_accuracies)) if fold_accuracies else 0.0
    std_acc = float(np.std(fold_accuracies)) if fold_accuracies else 0.0
    mean_ll = float(np.mean(fold_logloss)) if fold_logloss else float("inf")
    avg_best_iter = int(np.mean(fold_best_iterations)) if fold_best_iterations else base_params["n_estimators"]
    print(f"\nWFO Mean Accuracy: {mean_acc:.4f} (+/- {std_acc:.4f})")
    print(f"WFO Mean LogLoss:  {mean_ll:.4f}")
    print(f"WFO Avg Best Iter: {avg_best_iter}")

    if last_val_x is not None and best_fold_model is not None:
        shap_importance_global = compute_shap_importance(best_fold_model, last_val_x)
        if shap_importance_global:
            print("\nTop 20 SHAP Importances:")
            for i, (feat, val) in enumerate(list(shap_importance_global.items())[:20]):
                print(f"  {feat:40s} {val:.6f}")

    prev_metrics = None
    if WFO_METRICS_OUTPUT.exists():
        try:
            prev_metrics = json.loads(WFO_METRICS_OUTPUT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    decay_info = detect_model_decay(prev_metrics, mean_acc)
    if decay_info["decayed"]:
        LOGGER.warning("MODEL DECAY DETECTED: prev=%.4f current=%.4f delta=%.4f",
                       decay_info["prev_accuracy"], mean_acc, decay_info["delta"])
    print(f"Decay check: {decay_info}")

    final_params = dict(base_params)
    final_params["n_estimators"] = avg_best_iter
    final_params.pop("early_stopping_rounds", None)
    if n_classes == 2:
        final_params["objective"] = "binary:logistic"
    else:
        final_params["objective"] = "multi:softprob"
        final_params["num_class"] = n_classes
    final_model = XGBClassifier(**final_params)

    minority_count = min(np.bincount(y_encoded))
    k_neighbors = max(1, min(5, minority_count - 1))
    try:
        smote = SMOTE(k_neighbors=k_neighbors, random_state=42)
        x_resampled, y_resampled = smote.fit_resample(x, y_encoded)
    except (ValueError, RuntimeError):
        x_resampled, y_resampled = x, y_encoded
    final_model.fit(x_resampled, y_resampled)

    xgb_importances = pd.Series(final_model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print("\nTop 30 XGB Feature Importances (incl. institutional):")
    for feat, imp in xgb_importances.head(30).items():
        print(f"  {feat:40s} {imp:.6f}")

    importance_dict = {feat: float(imp) for feat, imp in xgb_importances.items()}
    pruned_cols = prune_features(feature_cols, importance_dict)
    pruned_count = len(feature_cols) - len(pruned_cols)
    if pruned_count > 0:
        print(f"\nFeature pruning: {len(feature_cols)} -> {len(pruned_cols)} (removed {pruned_count} below threshold {FEATURE_IMPORTANCE_THRESHOLD})")
    else:
        pruned_cols = feature_cols

    metrics = {
        "fold_accuracies": fold_accuracies,
        "fold_logloss": fold_logloss,
        "fold_best_iterations": fold_best_iterations,
        "mean_accuracy": mean_acc,
        "std_accuracy": std_acc,
        "mean_logloss": mean_ll,
        "avg_best_iteration": avg_best_iter,
        "feature_importances": importance_dict,
        "shap_importances": shap_importance_global,
        "label_map": label_map,
        "reverse_label": reverse_label,
        "decay_info": decay_info,
        "n_features_original": len(feature_cols),
        "n_features_pruned": len(pruned_cols),
        "purge_events": purge_events,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return final_model, pruned_cols, metrics


def train_pipeline(jsonl_path: Path | None = None, symbol_filter: str | None = None,
                   tick_forward: int = TICK_FORWARD,
                   window: int = WINDOW_EVENTS,
                   flat_zone_bps: float = FLAT_ZONE_BPS,
                   sample_limit: int = SAMPLE_LIMIT) -> tuple[XGBClassifier, list[str], dict]:
    if jsonl_path is None:
        jsonl_path = JSONL_PATH
    print(f"Building features from {jsonl_path}")
    frame = events_to_dataframe(jsonl_path, symbol_filter=symbol_filter,
                                tick_forward=tick_forward, window=window,
                                flat_zone_bps=flat_zone_bps, sample_limit=sample_limit)
    if frame.empty:
        raise RuntimeError("No features extracted. Check JSONL data or symbol filter.")
    print(f"Dataset shape: {frame.shape}")
    print("Target distribution:")
    print(frame["target"].value_counts().sort_index())
    drop_cols = ["symbol", "mid_price", "target"]
    feature_cols = [c for c in frame.columns if c not in drop_cols]
    model, feature_cols, metrics = walk_forward_train(frame, feature_cols)
    MODEL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_OUTPUT)
    print(f"\nModel saved: {MODEL_OUTPUT}")
    FEATURE_NAMES_OUTPUT.write_text(json.dumps(feature_cols, indent=2), encoding="utf-8")
    print(f"Feature names saved: {FEATURE_NAMES_OUTPUT}")
    WFO_METRICS_OUTPUT.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    print(f"WFO metrics saved: {WFO_METRICS_OUTPUT}")
    if metrics.get("shap_importances"):
        SHAP_OUTPUT.write_text(json.dumps(metrics["shap_importances"], indent=2), encoding="utf-8")
        print(f"SHAP importances saved: {SHAP_OUTPUT}")
    return model, feature_cols, metrics


def load_trained_model() -> XGBClassifier | None:
    if MODEL_OUTPUT.exists():
        return joblib.load(MODEL_OUTPUT)
    return None


def predict_from_book(book: OrderBookState, mid_roller: TimeSeriesRoller,
                      spread_roller: TimeSeriesRoller,
                      obi_roller: TimeSeriesRoller,
                      last_update: int, current_ts: int) -> tuple[int, float]:
    model = load_trained_model()
    if model is None:
        return 0, 0.0
    features = extract_features(book, mid_roller, spread_roller, obi_roller,
                                last_update, current_ts)
    feature_cols = json.loads(FEATURE_NAMES_OUTPUT.read_text()) if FEATURE_NAMES_OUTPUT.exists() else list(features.keys())
    x = pd.DataFrame([{k: features.get(k, 0.0) for k in feature_cols}])
    x = x.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if hasattr(model, "feature_names_in_"):
        x = x.reindex(columns=list(model.feature_names_in_), fill_value=0.0)
    proba = model.predict_proba(x)[0]
    pred_class = int(model.classes_[proba.argmax()])
    confidence = float(proba.max())
    return pred_class, confidence


if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else None
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else SAMPLE_LIMIT
    train_pipeline(symbol_filter=symbol, sample_limit=limit)
