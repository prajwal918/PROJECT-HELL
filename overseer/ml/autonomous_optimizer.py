from __future__ import annotations
import json
import math
import sqlite3
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger("overseer.optimizer")

# Reuse definitions from dynamic_pair_selector
STATUS_TRADE_CANDIDATE = "TRADE_CANDIDATE"
STATUS_WATCHLIST = "WATCHLIST"
STATUS_BLOCK = "BLOCK"

DB_PATH = Path("database/overseer_trades.db")
CONFIG_PATH = Path("config/dynamic_elite_params_rare_min5.json")

FRAMEWORK_FEATURES = [
    "FW01_multi_tf_trend", "FW02_price_action", "FW03_volume", "FW04_liquidity_sweep",
    "FW05_weekly_levels", "FW06_session_kz", "FW07_econ_event", "FW08_asian_range",
    "FW09_cot_positioning", "FW10_post_news", "FW11_iv_skew", "FW12_dxy_isolation",
    "FW13_lag_arb", "FW14_risk_regime", "FW15_l3_flow", "FW16_directional_momentum",
    "FW17_volume_profile", "FW18_technical", "FW19_fundamental"
]

@dataclass
class BestRule:
    feature: str
    threshold: float
    wr: float
    count: int

def run_autonomous_optimization():
    """
    Scans the database, finds the best framework filters for each symbol/direction,
    and autonomously updates the configuration file.
    """
    if not DB_PATH.exists():
        return

    LOGGER.info("Starting autonomous rule optimization...")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT symbol, direction, framework_scores_json, outcome_200ticks
        FROM signal_log
        WHERE outcome_200ticks IN ('WIN', 'LOSS')
    """).fetchall()
    conn.close()

    if len(rows) < 500:
        LOGGER.info("Not enough data to optimize rules yet (need 500+ outcomes).")
        return

    # Group records by symbol/direction
    data = {}
    for r in rows:
        key = (r['symbol'], r['direction'])
        if key not in data: data[key] = []
        fw = json.loads(r['framework_scores_json']) if r['framework_scores_json'] else {}
        fw['is_win'] = 1 if r['outcome_200ticks'] == 'WIN' else 0
        data[key].append(fw)

    elite_params = []

    for (sym, direct), records in data.items():
        if len(records) < 20: continue
        
        # Base stats
        base_wins = sum(r['is_win'] for r in records)
        base_wr = base_wins / len(records)
        
        best_fw_rule = None
        max_wr_gain = 0.0

        # Simple greedy search for the best framework filter
        for feat in FRAMEWORK_FEATURES:
            for thresh in [0.5, 0.6, 0.7, 0.8, 0.9]:
                filtered = [r for r in records if r.get(feat, 0.0) >= thresh]
                if len(filtered) < 10: continue
                
                win_rate = sum(r['is_win'] for r in filtered) / len(filtered)
                if win_rate > base_wr and win_rate > 0.80:
                    gain = win_rate - base_wr
                    if gain > max_wr_gain:
                        max_wr_gain = gain
                        best_fw_rule = BestRule(feat, thresh, win_rate, len(filtered))

        # Generate entry
        rules = []
        if best_fw_rule:
            rules.append({"feature": best_fw_rule.feature, "op": ">=", "threshold": best_fw_rule.threshold})
            reason = f"Autonomously optimized: {best_fw_rule.feature} >= {best_fw_rule.threshold} yields {best_fw_rule.wr:.1%} WR (n={best_fw_rule.count})"
        else:
            reason = f"Baseline performance: {base_wr:.1%} WR"

        status = STATUS_TRADE_CANDIDATE if (best_fw_rule and best_fw_rule.wr >= 0.90) or base_wr >= 0.90 else STATUS_WATCHLIST
        
        elite_params.append({
            "symbol": sym,
            "direction": direct,
            "status": status,
            "rules": rules,
            "reason": reason,
            "validation": {"wr_ex_flat": best_fw_rule.wr if best_fw_rule else base_wr, "nonflat": len(records)}
        })

    if elite_params:
        # Save the new rules autonomously
        with open(CONFIG_PATH, "w") as f:
            json.dump(elite_params, f, indent=2)
        LOGGER.info(f"Autonomous optimization complete. Updated {len(elite_params)} symbol rules.")
    else:
        LOGGER.warning("Autonomous optimization found no high-probability rules.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_autonomous_optimization()
