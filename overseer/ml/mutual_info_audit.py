import os
import logging
import sqlite3
from collections import deque
import numpy as np

log = logging.getLogger(__name__)

_ENABLED = os.getenv("MUTUAL_INFO_ENABLED", "true").lower() == "true"
_DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "overseer_trades.db"))
_REDUNDANCY_THRESHOLD = float(os.getenv("MUTUAL_INFO_REDUNDANCY", "0.70"))


class MutualInfoAudit:
    def __init__(self):
        self._mi_matrix = {}
        self._redundant_pairs = []

    def compute_mi(self, x, y):
        try:
            from sklearn.metrics import mutual_info_score
            return mutual_info_score(x, y)
        except ImportError:
            x_arr = np.array(x)
            y_arr = np.array(y)
            if len(x_arr) < 10:
                return 0.0
            x_bins = np.digitize(x_arr, np.histogram_bin_edges(x_arr, bins=5))
            y_bins = np.digitize(y_arr, np.histogram_bin_edges(y_arr, bins=5))
            contingency = np.zeros((6, 6), dtype=np.float64)
            for xi, yi in zip(x_bins, y_bins):
                contingency[min(xi, 5)][min(yi, 5)] += 1
            total = contingency.sum()
            if total == 0:
                return 0.0
            mi = 0.0
            for i in range(6):
                for j in range(6):
                    pxy = contingency[i][j] / total
                    px = contingency[i].sum() / total
                    py = contingency[:, j].sum() / total
                    if pxy > 0 and px > 0 and py > 0:
                        mi += pxy * np.log(pxy / (px * py))
            return max(0.0, mi)

    def audit_from_db(self, db_path=None):
        if not _ENABLED:
            return
        dp = db_path or _DB_PATH
        try:
            conn = sqlite3.connect(dp, timeout=10)
            cur = conn.cursor()
            cur.execute("SELECT gate_states_json FROM signal_log ORDER BY id DESC LIMIT 5000")
            rows = cur.fetchall()
            conn.close()
            if len(rows) < 100:
                return
            import json
            gate_data = {}
            for row in rows:
                gs = json.loads(row[0]) if row[0] else {}
                for gate, val in gs.items():
                    if gate not in gate_data:
                        gate_data[gate] = []
                    gate_data[gate].append(1 if val else 0)
            gates = list(gate_data.keys())[:30]
            self._redundant_pairs = []
            for i, g1 in enumerate(gates):
                for g2 in gates[i + 1:]:
                    if g1 in gate_data and g2 in gate_data:
                        min_len = min(len(gate_data[g1]), len(gate_data[g2]))
                        mi = self.compute_mi(gate_data[g1][:min_len], gate_data[g2][:min_len])
                        self._mi_matrix[(g1, g2)] = mi
                        if mi > _REDUNDANCY_THRESHOLD:
                            self._redundant_pairs.append((g1, g2, mi))
                            log.warning(f"GATE REDUNDANCY: {g1} and {g2} MI={mi:.2f}")
            log.info(f"MutualInfoAudit: {len(gates)} gates, {len(self._redundant_pairs)} redundant pairs")
        except Exception as e:
            log.warning(f"MutualInfoAudit failed: {e}")

    def get_redundant_pairs(self):
        return list(self._redundant_pairs)


mutual_info_audit = MutualInfoAudit()
