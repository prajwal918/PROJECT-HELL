import os
import logging
import sqlite3
import numpy as np

log = logging.getLogger(__name__)

_ENABLED = os.getenv("SCORE_CALIBRATION_ENABLED", "true").lower() == "true"
_DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "overseer_trades.db"))
_METHOD = os.getenv("SCORE_CALIBRATION_METHOD", "isotonic")
_MIN_CALIBRATION_SAMPLES = int(os.getenv("SCORE_CALIBRATION_MIN_SAMPLES", "50"))


class ScoreCalibrator:
    def __init__(self):
        self._calibrator = None
        self._fitted = False

    def fit(self, scores, outcomes):
        if not _ENABLED:
            return
        if len(scores) < _MIN_CALIBRATION_SAMPLES:
            log.info(f"ScoreCalibrator: only {len(scores)} samples, need {_MIN_CALIBRATION_SAMPLES}")
            return
        scores_arr = np.array(scores, dtype=np.float64).reshape(-1, 1)
        outcomes_arr = np.array(outcomes, dtype=np.float64)
        try:
            if _METHOD == "platt":
                from sklearn.linear_model import LogisticRegression
                self._calibrator = LogisticRegression()
                self._calibrator.fit(scores_arr, outcomes_arr)
            else:
                from sklearn.isotonic import IsotonicRegression
                self._calibrator = IsotonicRegression(out_of_bounds="clip")
                self._calibrator.fit(scores_arr.ravel(), outcomes_arr)
            self._fitted = True
            log.info(f"ScoreCalibrator fitted: method={_METHOD} n={len(scores)}")
        except Exception as e:
            log.warning(f"ScoreCalibrator fit failed: {e}")

    def calibrate(self, raw_score):
        if not _ENABLED or not self._fitted:
            return raw_score
        try:
            if _METHOD == "platt":
                return float(self._calibrator.predict_proba([[raw_score]])[0, 1])
            else:
                return float(self._calibrator.predict([raw_score])[0])
        except Exception:
            return raw_score

    def fit_from_db(self, db_path=None):
        dp = db_path or _DB_PATH
        try:
            conn = sqlite3.connect(dp, timeout=10)
            cur = conn.cursor()
            cur.execute("""
                SELECT score, CASE WHEN outcome_200ticks = 'WIN' THEN 1.0 ELSE 0.0 END as label
                FROM signal_log
                WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
            """)
            rows = cur.fetchall()
            conn.close()
            if rows:
                scores = [r[0] for r in rows]
                outcomes = [r[1] for r in rows]
                self.fit(scores, outcomes)
        except Exception as e:
            log.warning(f"ScoreCalibrator DB fit failed: {e}")


score_calibrator = ScoreCalibrator()
