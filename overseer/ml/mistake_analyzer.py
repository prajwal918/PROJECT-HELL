#!/usr/bin/env python3
"""
MISTAKE ANALYZER v1.1
Learns from historical losses by identifying 'Liar Gates'—filters that 
passed during a loss but were supposed to protect the account.
"""

import sqlite3
import json
import os
from collections import defaultdict

DB_PATH = 'database/overseer_trades.db'

def run_analysis():
    if not os.path.exists(DB_PATH):
        return "Error: Database not found."

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Query all signals with outcomes from last 7 days
    cursor.execute('''
        SELECT gate_states_json, outcome_200ticks 
        FROM signal_log 
        WHERE outcome_200ticks IN ('WIN', 'LOSS')
        AND timestamp > datetime('now', '-7 days')
    ''')
    rows = cursor.fetchall()

    if not rows:
        return "No new resolved outcomes found in the last 7 days."

    gate_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total': 0})
    
    for gate_json, outcome in rows:
        try:
            gates = json.loads(gate_json)
            for gate_name, state in gates.items():
                if state:
                    gate_stats[gate_name]['total'] += 1
                    if outcome == 'WIN':
                        gate_stats[gate_name]['wins'] += 1
                    else:
                        gate_stats[gate_name]['losses'] += 1
        except:
            continue

    liars = []
    for name, stats in gate_stats.items():
        if stats['total'] > 30:
            fail_rate = (stats['losses'] / stats['total']) * 100
            liars.append((name, fail_rate, stats['total']))

    liars.sort(key=lambda x: x[1], reverse=True)
    
    report = ["=== MISTAKE AUDIT (Last 7 Days) ==="]
    report.append(f"Analyzed {len(rows)} resolved signals.")
    report.append("\nTop Liar Gates (Penalize these):")
    for name, frate, total in liars[:5]:
        report.append(f"- {name}: {frate:.1f}% failure rate ({total} samples)")
        
    report.append("\nTop Reliable Gates (Trust these):")
    reliables = sorted(liars, key=lambda x: x[1])
    for name, frate, total in reliables[:5]:
        report.append(f"- {name}: {100-frate:.1f}% win rate ({total} samples)")

    conn.close()
    return "\n".join(report)

if __name__ == "__main__":
    print(run_analysis())
