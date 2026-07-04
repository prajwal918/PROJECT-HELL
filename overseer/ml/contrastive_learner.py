from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

CONTRASTIVE_LEARNER_ENABLED = os.getenv("CONTRASTIVE_LEARNER_ENABLED", "true").lower() == "true"
CONTRASTIVE_LEARNER_BONUS_MAX = float(os.getenv("CONTRASTIVE_LEARNER_BONUS_MAX", "0.10"))
CONTRASTIVE_LEARNER_REFRESH_S = float(os.getenv("CONTRASTIVE_LEARNER_REFRESH_S", "3600"))
CONTRASTIVE_LEARNER_MIN_SAMPLES = int(os.getenv("CONTRASTIVE_LEARNER_MIN_SAMPLES", "50"))
CONTRASTIVE_LEARNER_SIMILARITY_THRESHOLD = float(os.getenv("CONTRASTIVE_LEARNER_SIMILARITY_THRESHOLD", "0.3"))

_FW_NAMES = [
    "FW01_multi_tf_trend", "FW02_price_action", "FW03_volume",
    "FW04_liquidity_sweep", "FW05_weekly_levels", "FW06_session_kz",
    "FW07_econ_event", "FW08_asian_range", "FW09_cot_positioning",
    "FW10_post_news", "FW11_iv_skew", "FW12_dxy_isolation",
    "FW13_lag_arb", "FW14_risk_regime", "FW15_l3_flow",
    "FW16_directional_momentum", "FW17_volume_profile",
    "FW18_technical", "FW19_fundamental",
]


def _cosine_similarity(a, b):
    dot = np.dot(a, b)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


class ContrastiveLearner:
    def __init__(self):
        self._enabled = CONTRASTIVE_LEARNER_ENABLED
        self._bonus_max = CONTRASTIVE_LEARNER_BONUS_MAX
        self._refresh_s = CONTRASTIVE_LEARNER_REFRESH_S
        self._min_samples = CONTRASTIVE_LEARNER_MIN_SAMPLES
        self._sim_threshold = CONTRASTIVE_LEARNER_SIMILARITY_THRESHOLD
        self._win_centroid = None  # type: Optional[np.ndarray]
        self._loss_centroid = None  # type: Optional[np.ndarray]
        self._feature_names = []  # type: List[str]
        self._last_fit_time = 0.0
        self._fitted = False
        if not self._enabled:
            logger.info("ContrastiveLearner disabled via CONTRASTIVE_LEARNER_ENABLED=false")

    def _extract_features(self, fw_scores, l3_features=None, bias_breakdown=None):
        vec = []
        for name in _FW_NAMES:
            vec.append(float(fw_scores.get(name, 0.0)))
        if l3_features:
            for key in ["spoof_reversal_signal", "queue_exhaustion_signal",
                        "iceberg_detected", "adverse_selection_risk",
                        "hft_cluster_detected", "liquidity_vacuum_signal",
                        "l3_prediction", "l3_confidence"]:
                vec.append(float(l3_features.get(key, l3_features.get(
                    key.replace("_signal", ""), 0.0))))
        if bias_breakdown:
            for key in ["spoof_bias", "queue_bias", "iceberg_bias",
                        "adverse_bias", "hft_bias", "vacuum_bias", "iv_bias"]:
                vec.append(float(bias_breakdown.get(key, 0.0)))
        return np.array(vec, dtype=np.float32)

    def fit_from_db(self, db_path):
        if not self._enabled:
            return
        if not os.path.exists(db_path):
            logger.warning("ContrastiveLearner: DB not found at %s", db_path)
            return
        try:
            conn = sqlite3.connect(db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT framework_scores_json, l3_features_json, bias_breakdown_json, outcome_200ticks "
                "FROM signal_log WHERE outcome_200ticks IS NOT NULL "
                "AND outcome_200ticks != 'FLAT'"
            ).fetchall()
            conn.close()
        except Exception as exc:
            logger.error("ContrastiveLearner DB read failed: %s", exc)
            return

        if len(rows) < self._min_samples:
            logger.info("ContrastiveLearner: only %d rows (need %d)", len(rows), self._min_samples)
            return

        win_vecs = []
        loss_vecs = []
        for row in rows:
            try:
                fw = json.loads(row["framework_scores_json"]) if row["framework_scores_json"] else {}
                l3 = json.loads(row["l3_features_json"]) if row["l3_features_json"] else {}
                bb = json.loads(row["bias_breakdown_json"]) if row["bias_breakdown_json"] else {}
            except (json.JSONDecodeError, TypeError):
                continue
            vec = self._extract_features(fw, l3, bb)
            if np.any(np.isnan(vec)):
                continue
            if row["outcome_200ticks"] == "WIN":
                win_vecs.append(vec)
            elif row["outcome_200ticks"] == "LOSS":
                loss_vecs.append(vec)

        if len(win_vecs) < 5 or len(loss_vecs) < 5:
            logger.info("ContrastiveLearner: insufficient WIN=%d LOSS=%d", len(win_vecs), len(loss_vecs))
            return

        self._win_centroid = np.mean(win_vecs, axis=0).astype(np.float32)
        self._loss_centroid = np.mean(loss_vecs, axis=0).astype(np.float32)
        self._fitted = True
        self._last_fit_time = time.time()
        logger.info(
            "ContrastiveLearner fitted: %d wins, %d losses, %d features",
            len(win_vecs), len(loss_vecs), len(self._win_centroid),
        )

    def score_signal(self, features_dict):
        if not self._enabled or not self._fitted:
            return 0.0
        fw = features_dict.get("framework_scores", {})
        l3 = features_dict.get("l3_features", {})
        bb = features_dict.get("bias_breakdown", {})
        vec = self._extract_features(fw, l3, bb)
        if np.any(np.isnan(vec)) or len(vec) != len(self._win_centroid):
            return 0.0
        sim_win = _cosine_similarity(vec, self._win_centroid)
        sim_loss = _cosine_similarity(vec, self._loss_centroid)
        contrastive = sim_win - sim_loss
        return float(np.clip(contrastive, -1.0, 1.0))

    def get_bonus(self, features_dict):
        if not self._enabled or not self._fitted:
            return 0.0
        score = self.score_signal(features_dict)
        if score <= self._sim_threshold:
            return 0.0
        normalized = (score - self._sim_threshold) / (1.0 - self._sim_threshold)
        return float(np.clip(normalized * self._bonus_max, 0.0, self._bonus_max))

    def maybe_refresh(self, db_path):
        if not self._enabled:
            return
        if time.time() - self._last_fit_time > self._refresh_s:
            self.fit_from_db(db_path)


contrastive_learner = ContrastiveLearner()
