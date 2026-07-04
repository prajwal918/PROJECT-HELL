from __future__ import annotations
import sqlite3
import json
import pandas as pd
from pathlib import Path

DB_PATH = Path("database/overseer_trades.db")

def find_the_edge():
    if not DB_PATH.exists():
        print("Database not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    
    # Load signals with outcomes
    df = pd.read_sql_query("""
        SELECT symbol, direction, session, risk_regime, 
               score, adjusted_score, framework_scores_json,
               outcome_200ticks, pnl
        FROM signal_log
        WHERE outcome_200ticks IN ('WIN', 'LOSS')
    """, conn)
    
    if df.empty:
        print("No completed signal outcomes found to analyze.")
        return

    print(f"Analyzing {len(df)} completed signals...")
    
    # Convert WIN/LOSS to 1/0
    df['is_win'] = (df['outcome_200ticks'] == 'WIN').astype(int)
    
    # 1. Best Symbol + Direction + Session
    print("\n--- TOP PERFORMANCE GROUPS (Min 20 signals) ---")
    stats = df.groupby(['symbol', 'direction', 'session']).agg({
        'is_win': ['count', 'mean'],
        'score': 'mean'
    })
    stats.columns = ['count', 'win_rate', 'avg_score']
    top_stats = stats[stats['count'] >= 20].sort_values(('win_rate'), ascending=False)
    print(top_stats.head(10))

    # 2. Framework Correlation
    print("\n--- FRAMEWORK IMPORTANCE (Correlation with WIN) ---")
    fw_data = []
    for _, row in df.iterrows():
        try:
            fw = json.loads(row['framework_scores_json'])
            fw['is_win'] = row['is_win']
            fw_data.append(fw)
        except:
            continue
    
    fw_df = pd.DataFrame(fw_data)
    corrs = fw_df.corr()['is_win'].sort_values(ascending=False)
    print(corrs.head(10))

    # 3. The "Loser Zone" (What causes a LOSS?)
    print("\n--- LOSER COMMONALITIES ---")
    losers = df[df['is_win'] == 0]
    if not losers.empty:
        print("Common Sessions for Losers:")
        print(losers['session'].value_counts(normalize=True).head(3))
        print("\nCommon Risk Regimes for Losers:")
        print(losers['risk_regime'].value_counts(normalize=True).head(3))

    conn.close()

if __name__ == "__main__":
    find_the_edge()
