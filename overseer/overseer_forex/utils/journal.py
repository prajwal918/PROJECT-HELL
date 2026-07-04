"""
SQLite Trade Journal for OVERSEER
Tracks all signals, trades, and analytics
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
import os


class TradeJournal:
    """SQLite-based trade journal with analytics."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.getenv('DB_PATH', './data/trades.db')
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            asset TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL,
            sl_price REAL,
            tp1_price REAL,
            tp2_price REAL,
            lot_size REAL,
            risk_amount REAL,
            rr_ratio REAL,
            quality_score REAL,
            quality_grade TEXT,
            gate_b_score INTEGER,
            gate_a_score INTEGER,
            session TEXT,
            kill_zone TEXT,
            phase1_body_pct REAL,
            phase1_wick_pct REAL,
            phase1_vol_ratio REAL,
            spread_pips REAL,
            atr_pips REAL,
            htf_aligned INTEGER,
            dxy_aligned INTEGER,
            levels_hit TEXT,
            order_flow_checks TEXT,
            of_edges_active TEXT,
            l_edges_active TEXT,
            p_edges_active TEXT,
            fx_gates_passed TEXT,
            result TEXT DEFAULT 'PENDING',
            exit_price REAL,
            pnl REAL DEFAULT 0,
            pnl_pips REAL,
            hold_time_minutes INTEGER,
            slippage_pips REAL,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        c.execute("""
        CREATE TABLE IF NOT EXISTS rejections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            asset TEXT NOT NULL,
            failed_gate TEXT,
            gate_scores TEXT,
            raw_signal TEXT
        )
        """)
        
        # Create indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_trades_asset ON trades(asset)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_trades_result ON trades(result)")
        
        conn.commit()
        conn.close()
        
    def log_signal(self, signal: dict) -> int:
        """Log a new signal and return trade_id."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
        INSERT INTO trades (
            timestamp, asset, direction, entry_price, sl_price, tp1_price, tp2_price,
            lot_size, risk_amount, rr_ratio, quality_score, quality_grade,
            gate_b_score, gate_a_score, session, kill_zone,
            phase1_body_pct, phase1_wick_pct, phase1_vol_ratio,
            spread_pips, atr_pips, htf_aligned, dxy_aligned,
            levels_hit, order_flow_checks, of_edges_active, l_edges_active, p_edges_active, fx_gates_passed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal.get('timestamp', datetime.utcnow().isoformat()),
            signal.get('asset'),
            signal.get('direction'),
            signal.get('entry_price'),
            signal.get('sl_price'),
            signal.get('tp1_price'),
            signal.get('tp2_price'),
            signal.get('lot_size'),
            signal.get('risk_amount'),
            signal.get('rr_ratio'),
            signal.get('quality_score'),
            signal.get('quality_grade'),
            signal.get('gate_b_score'),
            signal.get('gate_a_score'),
            signal.get('session'),
            signal.get('kill_zone'),
            signal.get('body_pct'),
            signal.get('wick_pct'),
            signal.get('volume_ratio'),
            signal.get('spread_pips'),
            signal.get('atr_pips'),
            int(signal.get('htf_aligned', False)),
            int(signal.get('dxy_aligned', False)),
            json.dumps(signal.get('levels_hit', [])),
            json.dumps(signal.get('order_flow_checks', {})),
            json.dumps(signal.get('of_edges_active', [])),
            json.dumps(signal.get('l_edges_active', [])),
            json.dumps(signal.get('p_edges_active', [])),
            json.dumps(signal.get('fx_gates_passed', []))
        ))
        
        trade_id = c.lastrowid
        conn.commit()
        conn.close()
        
        return trade_id
        
    def log_rejection(self, signal: dict, result: dict):
        """Log a rejected signal."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
        INSERT INTO rejections (timestamp, asset, failed_gate, gate_scores, raw_signal)
        VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            signal.get('asset'),
            result.get('failed_gate'),
            json.dumps(result.get('gate_scores', {})),
            json.dumps(signal)
        ))
        
        conn.commit()
        conn.close()
        
    def update_result(self, trade_id: int, result: str, pnl: float, 
                      exit_price: float = None, slippage: float = None):
        """Update trade result after exit."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
        UPDATE trades 
        SET result = ?, pnl = ?, exit_price = ?, slippage_pips = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (result, pnl, exit_price, slippage, trade_id))
        
        conn.commit()
        conn.close()
        
    def get_analytics(self, days: int = 30) -> dict:
        """Get performance analytics."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        analytics = {}
        
        # Overall stats
        c.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) as wins,
            SUM(pnl) as total_pnl
        FROM trades 
        WHERE result != 'PENDING' 
        AND timestamp >= datetime('now', ?)
        """, (f'-{days} days',))
        
        row = c.fetchone()
        if row and row[0] > 0:
            analytics['overall'] = {
                'total_trades': row[0],
                'wins': row[1],
                'win_rate': round(row[1] / row[0] * 100, 1),
                'total_pnl': round(row[2] or 0, 2)
            }
        
        # By Gate B score
        c.execute("""
        SELECT gate_b_score, COUNT(*), 
               ROUND(AVG(CASE WHEN result = 'WIN' THEN 1.0 ELSE 0 END) * 100, 1),
               SUM(pnl)
        FROM trades WHERE result != 'PENDING'
        GROUP BY gate_b_score ORDER BY gate_b_score DESC
        """)
        analytics['by_gate_b'] = [
            {'score': r[0], 'trades': r[1], 'win_rate': r[2], 'pnl': r[3]}
            for r in c.fetchall()
        ]
        
        # By asset
        c.execute("""
        SELECT asset, COUNT(*), 
               ROUND(AVG(CASE WHEN result = 'WIN' THEN 1.0 ELSE 0 END) * 100, 1),
               SUM(pnl)
        FROM trades WHERE result != 'PENDING'
        GROUP BY asset ORDER BY SUM(pnl) DESC
        """)
        analytics['by_asset'] = [
            {'asset': r[0], 'trades': r[1], 'win_rate': r[2], 'pnl': r[3]}
            for r in c.fetchall()
        ]
        
        # By session
        c.execute("""
        SELECT session, COUNT(*), 
               ROUND(AVG(CASE WHEN result = 'WIN' THEN 1.0 ELSE 0 END) * 100, 1),
               SUM(pnl)
        FROM trades WHERE result != 'PENDING'
        GROUP BY session
        """)
        analytics['by_session'] = [
            {'session': r[0], 'trades': r[1], 'win_rate': r[2], 'pnl': r[3]}
            for r in c.fetchall()
        ]
        
        # By quality grade
        c.execute("""
        SELECT quality_grade, COUNT(*), 
               ROUND(AVG(CASE WHEN result = 'WIN' THEN 1.0 ELSE 0 END) * 100, 1),
               SUM(pnl)
        FROM trades WHERE result != 'PENDING'
        GROUP BY quality_grade
        """)
        analytics['by_grade'] = [
            {'grade': r[0], 'trades': r[1], 'win_rate': r[2], 'pnl': r[3]}
            for r in c.fetchall()
        ]
        
        conn.close()
        return analytics
        
    def print_analytics(self):
        """Print formatted analytics to console."""
        analytics = self.get_analytics(days=30)
        
        print("\n" + "=" * 60)
        print("OVERSEER TRADE JOURNAL ANALYTICS (Last 30 Days)")
        print("=" * 60)
        
        if 'overall' in analytics:
            o = analytics['overall']
            print(f"\nOverall: {o['wins']}/{o['total_trades']} ({o['win_rate']}%) | PnL: ${o['total_pnl']:+.2f}")
        
        if 'by_gate_b' in analytics:
            print("\n-- By Gate B Score --")
            for row in analytics['by_gate_b']:
                print(f"  Gate B {row['score']}/17: {row['trades']} trades, {row['win_rate']}% WR, ${row['pnl']:+.2f}")
        
        if 'by_asset' in analytics:
            print("\n-- By Asset --")
            for row in analytics['by_asset']:
                print(f"  {row['asset']}: {row['trades']} trades, {row['win_rate']}% WR, ${row['pnl']:+.2f}")
        
        if 'by_session' in analytics:
            print("\n-- By Session --")
            for row in analytics['by_session']:
                print(f"  {row['session']}: {row['trades']} trades, {row['win_rate']}% WR, ${row['pnl']:+.2f}")
        
        if 'by_grade' in analytics:
            print("\n-- By Quality Grade --")
            for row in analytics['by_grade']:
                print(f"  Grade {row['grade']}: {row['trades']} trades, {row['win_rate']}% WR, ${row['pnl']:+.2f}")
        
        print("\n" + "=" * 60 + "\n")
