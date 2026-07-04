from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

LOGGER = logging.getLogger("overseer.causal_importance")

_ENABLED = os.getenv("CAUSAL_IMPORTANCE_ENABLED", "true").lower() == "true"
_DB_PATH = os.getenv("DB_PATH", "database/overseer_trades.db")
_HIGH_THRESHOLD = float(os.getenv("CAUSAL_HIGH_THRESHOLD", "0.7"))
_LOW_THRESHOLD = float(os.getenv("CAUSAL_LOW_THRESHOLD", "0.3"))
_MIN_SAMPLES = int(os.getenv("CAUSAL_MIN_SAMPLES", "30"))
_DECORATIVE_THRESHOLD = float(os.getenv("CAUSAL_DECORATIVE_THRESHOLD", "0.03"))
_DEFAULT_WEIGHT = float(os.getenv("CAUSAL_DEFAULT_WEIGHT", "1.0"))

_FW_NAMES = [
    "FW01_multi_tf_trend",
    "FW02_price_action",
    "FW03_volume",
    "FW04_liquidity_sweep",
    "FW05_weekly_levels",
    "FW06_session_kz",
    "FW07_econ_event",
    "FW08_asian_range",
    "FW09_cot_positioning",
    "FW10_post_news",
    "FW11_iv_skew",
    "FW12_dxy_isolation",
    "FW13_lag_arb",
    "FW14_risk_regime",
    "FW15_l3_flow",
    "FW16_directional_momentum",
    "FW17_volume_profile",
    "FW18_technical",
    "FW19_fundamental",
]


class CausalImportance:
    def __init__(self) -> None:
        self._effects: Dict[str, float] = {}
        self._weights: Dict[str, float] = {}
        self._wr_high: Dict[str, float] = {}
        self._wr_low: Dict[str, float] = {}
        self._n_high: Dict[str, int] = {}
        self._n_low: Dict[str, int] = {}
        self._fitted = False
        for fw in _FW_NAMES:
            self._effects[fw] = 0.0
            self._weights[fw] = _DEFAULT_WEIGHT

    def fit_from_db(self, db_path: Optional[str] = None) -> Dict[str, Any]:
        if not _ENABLED:
            return {}
        path = db_path or _DB_PATH
        try:
            conn = sqlite3.connect(path, timeout=10)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT framework_scores_json, outcome_200ticks
                FROM signal_log
                WHERE outcome_200ticks IS NOT NULL
                AND outcome_200ticks != 'FLAT'
                AND framework_scores_json IS NOT NULL
                """
            ).fetchall()
            conn.close()
        except Exception as exc:
            LOGGER.warning("CausalImportance DB query failed: %s", exc)
            return {}
        if len(rows) < _MIN_SAMPLES:
            LOGGER.info("CausalImportance: only %d samples, need %d", len(rows), _MIN_SAMPLES)
            return {}
        high_wins = {}
        high_total = {}
        low_wins = {}
        low_total = {}
        for fw in _FW_NAMES:
            high_wins[fw] = 0
            high_total[fw] = 0
            low_wins[fw] = 0
            low_total[fw] = 0
        for row in rows:
            try:
                scores = json.loads(row["framework_scores_json"])
                outcome = row["outcome_200ticks"]
                won = 1 if outcome == "WIN" else 0
                for fw in _FW_NAMES:
                    val = float(scores.get(fw, 0.0))
                    if val >= _HIGH_THRESHOLD:
                        high_total[fw] += 1
                        if won:
                            high_wins[fw] += 1
                    elif val <= _LOW_THRESHOLD:
                        low_total[fw] += 1
                        if won:
                            low_wins[fw] += 1
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
        results = {}
        for fw in _FW_NAMES:
            wr_high = (high_wins[fw] / high_total[fw]) if high_total[fw] >= 5 else None
            wr_low = (low_wins[fw] / low_total[fw]) if low_total[fw] >= 5 else None
            self._wr_high[fw] = wr_high or 0.0
            self._wr_low[fw] = wr_low or 0.0
            self._n_high[fw] = high_total[fw]
            self._n_low[fw] = low_total[fw]
            if wr_high is not None and wr_low is not None:
                effect = wr_high - wr_low
            else:
                effect = 0.0
            self._effects[fw] = effect
            if abs(effect) < _DECORATIVE_THRESHOLD:
                self._weights[fw] = 0.5
            elif effect > 0:
                self._weights[fw] = min(_DEFAULT_WEIGHT + effect * 2.0, 2.0)
            else:
                self._weights[fw] = max(_DEFAULT_WEIGHT + effect * 2.0, 0.3)
            results[fw] = {
                "wr_high": round(wr_high, 4) if wr_high is not None else None,
                "wr_low": round(wr_low, 4) if wr_low is not None else None,
                "effect": round(effect, 4),
                "weight": round(self._weights[fw], 4),
                "n_high": high_total[fw],
                "n_low": low_total[fw],
            }
        self._fitted = True
        LOGGER.info("CausalImportance fitted on %d samples, %d frameworks", len(rows), len(_FW_NAMES))
        return results

    def get_framework_weight(self, fw_name: str) -> float:
        if not _ENABLED:
            return _DEFAULT_WEIGHT
        return self._weights.get(fw_name, _DEFAULT_WEIGHT)

    def is_causal(self, fw_name: str) -> bool:
        if not _ENABLED:
            return True
        effect = abs(self._effects.get(fw_name, 0.0))
        return effect >= _DECORATIVE_THRESHOLD

    def get_effect(self, fw_name: str) -> float:
        return self._effects.get(fw_name, 0.0)

    def get_all_effects(self) -> Dict[str, float]:
        return {k: round(v, 4) for k, v in self._effects.items()}

    def get_all_weights(self) -> Dict[str, float]:
        return {k: round(v, 4) for k, v in self._weights.items()}

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": _ENABLED,
            "fitted": self._fitted,
            "effects": self.get_all_effects(),
            "weights": self.get_all_weights(),
            "decorative_threshold": _DECORATIVE_THRESHOLD,
        }


causal_importance = CausalImportance()
