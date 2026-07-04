"""Vector Memory Engine — ChromaDB-based long-term experience storage.

Every signal is stored as a 128-dim vector embedding (19 framework scores +
L3 features + market context). Before taking a trade, the system queries:
"Have I seen a similar state before? What happened?"

If the nearest neighbor was a big loss, auto-downgrade the score.
If the nearest neighbors were all wins, boost confidence.

ChromaDB with hnswlib runs fine on 2 cores. 50K embeddings = ~200MB RAM.
Query time: ~5ms.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.vector_memory")

VECTOR_DIM = int(os.getenv("VECTOR_DIM", "128"))
VECTOR_MEMORY_MAX = int(os.getenv("VECTOR_MEMORY_MAX_ENTRIES", "50000"))
VECTOR_SIMILARITY_THRESHOLD = float(os.getenv("VECTOR_SIMILARITY_THRESHOLD", "0.92"))
VECTOR_LOSS_PENALTY = float(os.getenv("VECTOR_LOSS_PENALTY", "0.15"))
VECTOR_WIN_BOOST = float(os.getenv("VECTOR_WIN_BOOST", "0.05"))
VECTOR_COLLECTION_NAME = "overseer_signals"


class NumpyVectorStore:
    """Fallback vector store using NumPy — no ChromaDB dependency needed.

    Uses cosine similarity with brute-force search.
    Scales to ~50K vectors on 2 cores in ~10ms.
    """

    def __init__(self, dim: int = VECTOR_DIM, max_entries: int = VECTOR_MEMORY_MAX) -> None:
        self.dim = dim
        self.max_entries = max_entries
        self._vectors: np.ndarray = np.zeros((0, dim))
        self._metadata: list[dict[str, Any]] = []
        self._ids: list[str] = []
        self._counter: int = 0

    def add(self, vector: np.ndarray, metadata: dict[str, Any], uid: str = "") -> str:
        if len(vector) != self.dim:
            vector = vector[:self.dim] if len(vector) > self.dim else np.pad(vector, (0, self.dim - len(vector)))
        if not uid:
            self._counter += 1
            uid = f"sig-{self._counter:08d}"
        if len(self._vectors) == 0:
            self._vectors = vector.reshape(1, -1)
        else:
            self._vectors = np.vstack([self._vectors, vector.reshape(1, -1)])
        self._metadata.append(metadata)
        self._ids.append(uid)
        if len(self._vectors) > self.max_entries:
            self._vectors = self._vectors[-self.max_entries:]
            self._metadata = self._metadata[-self.max_entries:]
            self._ids = self._ids[-self.max_entries:]
        return uid

    def query(self, vector: np.ndarray, top_k: int = 5) -> list[dict[str, Any]]:
        if len(self._vectors) == 0:
            return []
        if len(vector) != self.dim:
            vector = vector[:self.dim] if len(vector) > self.dim else np.pad(vector, (0, self.dim - len(vector)))
        norms = np.linalg.norm(self._vectors, axis=1)
        query_norm = np.linalg.norm(vector)
        if query_norm < 1e-10:
            return []
        valid = norms > 1e-10
        similarities = np.zeros(len(self._vectors))
        if valid.any():
            similarities[valid] = self._vectors[valid] @ vector / (norms[valid] * query_norm)
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        results = []
        for idx in top_indices:
            if similarities[idx] > 0:
                results.append({
                    "id": self._ids[idx],
                    "similarity": round(float(similarities[idx]), 4),
                    "metadata": self._metadata[idx],
                })
        return results

    def update_outcome(self, uid: str, outcome: str, pnl: float = 0.0) -> bool:
        for i, id_ in enumerate(self._ids):
            if id_ == uid:
                self._metadata[i]["outcome"] = outcome
                self._metadata[i]["pnl"] = pnl
                return True
        return False

    def count(self) -> int:
        return len(self._vectors)

    def stats(self) -> dict[str, Any]:
        if not self._metadata:
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0}
        wins = sum(1 for m in self._metadata if m.get("outcome") == "WIN")
        losses = sum(1 for m in self._metadata if m.get("outcome") == "LOSS")
        total = wins + losses
        return {"total": len(self._metadata), "wins": wins, "losses": losses, "win_rate": round(wins / max(1, total), 4)}


class ChromaVectorStore:
    """ChromaDB vector store — used when chromadb is installed."""

    def __init__(self, dim: int = VECTOR_DIM, max_entries: int = VECTOR_MEMORY_MAX) -> None:
        self.dim = dim
        self.max_entries = max_entries
        self._client = None
        self._collection = None
        self._counter: int = 0
        self._available = False
        try:
            import chromadb
            self._client = chromadb.Client()
            self._collection = self._client.get_or_create_collection(
                name=VECTOR_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
            LOGGER.info("ChromaDB vector memory initialized")
        except ImportError:
            LOGGER.info("ChromaDB not available — using NumPy vector store")

    def is_available(self) -> bool:
        return self._available

    def add(self, vector: np.ndarray, metadata: dict[str, Any], uid: str = "") -> str:
        if not self._available or self._collection is None:
            return ""
        if not uid:
            self._counter += 1
            uid = f"sig-{self._counter:08d}"
        str_metadata = {k: str(v) if not isinstance(v, str) else v for k, v in metadata.items()}
        try:
            self._collection.add(
                ids=[uid],
                embeddings=[vector.tolist()],
                metadatas=[str_metadata],
            )
        except Exception as e:
            LOGGER.warning("ChromaDB add failed: %s", e)
        return uid

    def query(self, vector: np.ndarray, top_k: int = 5) -> list[dict[str, Any]]:
        if not self._available or self._collection is None:
            return []
        try:
            results = self._collection.query(
                query_embeddings=[vector.tolist()],
                n_results=min(top_k, self._collection.count()) if self._collection.count() > 0 else top_k,
            )
            items = []
            if results and results["ids"] and results["ids"][0]:
                for i, id_ in enumerate(results["ids"][0]):
                    dist = results["distances"][0][i] if results["distances"] else 0
                    similarity = 1.0 - dist
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    items.append({"id": id_, "similarity": round(similarity, 4), "metadata": meta})
            return items
        except Exception as e:
            LOGGER.warning("ChromaDB query failed: %s", e)
            return []

    def count(self) -> int:
        if not self._available or self._collection is None:
            return 0
        return self._collection.count()


class VectorMemory:
    """Unified vector memory — ChromaDB if available, NumPy fallback.

    Usage in main.py:
        vm = VectorMemory()
        # After signal:
        vm.store_signal(signal_id, framework_scores, l3_features, tick, outcome="PENDING")
        # Before trade:
        adj = vm.check_experience(symbol, framework_scores, l3_features, tick)
        # adj = {"score_adjustment": -0.15, "nearest_loss_similarity": 0.95, ...}
    """

    def __init__(self) -> None:
        self._chroma = ChromaVectorStore()
        if self._chroma.is_available():
            self._store: ChromaVectorStore | NumpyVectorStore = self._chroma
        else:
            self._store = NumpyVectorStore()
        self._signal_count: int = 0

    def _build_embedding(self, framework_scores: dict[str, float], l3_features: dict[str, float] | None = None, tick: dict[str, Any] | None = None) -> np.ndarray:
        parts = []
        fw_values = [float(framework_scores.get(f"FW{i:02d}", framework_scores.get(name, 0.0))) for i, name in enumerate([
            "FW01_multi_tf_trend", "FW02_price_action", "FW03_volume", "FW04_liquidity_sweep",
            "FW05_weekly_levels", "FW06_session_kz", "FW07_econ_event", "FW08_asian_range",
            "FW09_cot_positioning", "FW10_post_news", "FW11_iv_skew", "FW12_dxy_isolation",
            "FW13_lag_arb", "FW14_risk_regime", "FW15_l3_flow", "FW16_directional_momentum",
            "FW17_volume_profile", "FW18_technical", "FW19_fundamental",
        ], start=1)]
        parts.append(np.array(fw_values))
        if l3_features:
            l3_vals = [float(l3_features.get(k, 0.0)) for k in [
                "spoof_reversal_signal", "queue_exhaustion_signal", "iceberg_detected",
                "adverse_selection_risk", "hft_cluster_detected", "liquidity_vacuum_signal",
            ]]
            parts.append(np.array(l3_vals))
        else:
            parts.append(np.zeros(6))
        if tick:
            ctx = np.array([
                float(tick.get("spread_bps", 0)) / 5.0,
                float(tick.get("dxy", 0)) / 100.0,
                1.0 if tick.get("direction") == "BUY" else 0.0,
                1.0 if tick.get("risk_regime") == "risk_on" else 0.0,
                float(tick.get("_ofi", 0)) / 100.0,
                float(tick.get("_cumulative_delta", 0)) / 500.0,
            ])
            parts.append(ctx)
        else:
            parts.append(np.zeros(6))
        embedding = np.concatenate(parts)
        if len(embedding) < VECTOR_DIM:
            embedding = np.pad(embedding, (0, VECTOR_DIM - len(embedding)))
        elif len(embedding) > VECTOR_DIM:
            embedding = embedding[:VECTOR_DIM]
        norm = np.linalg.norm(embedding)
        if norm > 1e-10:
            embedding = embedding / norm
        return embedding

    def store_signal(self, signal_id: str, framework_scores: dict[str, float], l3_features: dict[str, float] | None = None, tick: dict[str, Any] | None = None, score: float = 0.0) -> str:
        embedding = self._build_embedding(framework_scores, l3_features, tick)
        metadata = {
            "signal_id": signal_id,
            "symbol": tick.get("symbol", "") if tick else "",
            "direction": tick.get("direction", "") if tick else "",
            "score": str(score),
            "outcome": "PENDING",
            "pnl": "0.0",
            "timestamp": str(time.time()),
        }
        uid = self._store.add(embedding, metadata, signal_id)
        self._signal_count += 1
        return uid

    def update_outcome(self, signal_id: str, outcome: str, pnl: float = 0.0) -> bool:
        if isinstance(self._store, NumpyVectorStore):
            return self._store.update_outcome(signal_id, outcome, pnl)
        return False

    def check_experience(self, symbol: str, framework_scores: dict[str, float], l3_features: dict[str, float] | None = None, tick: dict[str, Any] | None = None) -> dict[str, Any]:
        embedding = self._build_embedding(framework_scores, l3_features, tick)
        neighbors = self._store.query(embedding, top_k=5)
        if not neighbors:
            return {"score_adjustment": 0.0, "neighbors": 0, "experience_signal": "no_memory"}
        similar_losses = [n for n in neighbors if n.get("similarity", 0) > VECTOR_SIMILARITY_THRESHOLD and n.get("metadata", {}).get("outcome") == "LOSS"]
        similar_wins = [n for n in neighbors if n.get("similarity", 0) > VECTOR_SIMILARITY_THRESHOLD and n.get("metadata", {}).get("outcome") == "WIN"]
        score_adj = 0.0
        nearest_loss_sim = 0.0
        if similar_losses:
            nearest_loss_sim = max(n["similarity"] for n in similar_losses)
            loss_count = len(similar_losses)
            penalty = VECTOR_LOSS_PENALTY * nearest_loss_sim * min(1.0, loss_count / 3.0)
            score_adj -= penalty
        if similar_wins:
            win_count = len(similar_wins)
            max_win_sim = max(n["similarity"] for n in similar_wins)
            boost = VECTOR_WIN_BOOST * max_win_sim * min(1.0, win_count / 3.0)
            score_adj += boost
        if score_adj < -0.10:
            signal = "dangerous_memory"
        elif score_adj < -0.05:
            signal = "cautionary_memory"
        elif score_adj > 0.03:
            signal = "confident_memory"
        else:
            signal = "neutral_memory"
        return {
            "score_adjustment": round(score_adj, 4),
            "nearest_loss_similarity": round(nearest_loss_sim, 4),
            "similar_losses": len(similar_losses),
            "similar_wins": len(similar_wins),
            "experience_signal": signal,
            "top_neighbor_sim": round(neighbors[0]["similarity"], 4) if neighbors else 0.0,
        }

    def backfill_from_db(self) -> dict[str, int]:
        try:
            import sqlite3
            from database.setup_db import DB_PATH
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            rows = conn.execute("""
                SELECT id, symbol, direction, score, framework_scores_json,
                       l3_features_json, outcome_200ticks, pnl
                FROM signal_log
                WHERE outcome_200ticks IS NOT NULL
                ORDER BY timestamp DESC LIMIT 10000
            """).fetchall()
            conn.close()
            count = 0
            for row in rows:
                sig_id, symbol, direction, score, fw_json, l3_json, outcome, pnl = row
                try:
                    fw = json.loads(fw_json) if fw_json else {}
                    l3 = json.loads(l3_json) if l3_json else {}
                    tick = {"symbol": symbol, "direction": direction}
                    outcome_str = "WIN" if outcome == "WIN" else "LOSS" if outcome == "LOSS" else "FLAT"
                    uid = self.store_signal(str(sig_id), fw, l3, tick, score)
                    self.update_outcome(str(sig_id), outcome_str, float(pnl or 0))
                    count += 1
                except Exception:
                    continue
            LOGGER.info("Backfilled %d signals into vector memory", count)
            return {"backfilled": count}
        except Exception as e:
            LOGGER.warning("Backfill failed: %s", e)
            return {"backfilled": 0, "error": str(e)}

    def get_status(self) -> dict[str, Any]:
        return {
            "store_type": "chromadb" if self._chroma.is_available() else "numpy",
            "total_entries": self._store.count(),
            "total_signals": self._signal_count,
        }
