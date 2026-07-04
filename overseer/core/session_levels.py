#!/usr/bin/env python3
"""
Session Levels — PDH/PDL/PWH/PWL/PMH/PML proximity.

Previous session high/low are the most universally respected
institutional reference points. They are not lagging indicators —
they are forward-looking order clusters.

PDH (Previous Day High): cluster of sell stops above + resistance
PDL (Previous Day Low): cluster of buy stops below + support
PWH/PWL: Previous Week High/Low — even stronger
PMH/PML: Previous Month High/Low — strongest of all
"""

import logging
import sqlite3
from typing import Dict, List, Optional

LOGGER = logging.getLogger("overseer.session_levels")

DB_PATH = "database/overseer_trades.db"
PROXIMITY_THRESHOLD_PIPS = 15


class SessionLevels:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_PATH
        self._levels: Dict[str, Dict] = {}
        self._loaded_symbols: set = set()

    def load_levels(self, symbol: str) -> Dict:
        """Load PDH/PDL/PWH/PWL from candle_history table."""
        if symbol in self._loaded_symbols:
            return self._levels.get(symbol, {})

        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")

            daily = conn.execute(
                """
                SELECT open_time, open, high, low, close
                FROM candle_history
                WHERE symbol = ? AND timeframe = 'Daily'
                ORDER BY open_time DESC LIMIT 7
                """,
                (symbol,),
            ).fetchall()

            weekly = conn.execute(
                """
                SELECT open_time, open, high, low, close
                FROM candle_history
                WHERE symbol = ? AND timeframe = '4H'
                ORDER BY open_time DESC LIMIT 30
                """,
                (symbol,),
            ).fetchall()

            conn.close()

        except Exception as e:
            LOGGER.debug("Session levels load failed for %s: %s", symbol, e)
            return {}

        levels = {}

        if len(daily) >= 2:
            prev_day = daily[1]
            levels["PDH"] = prev_day[2]
            levels["PDL"] = prev_day[3]
            levels["PDC"] = prev_day[4]

        if len(daily) >= 7:
            week_highs = [d[2] for d in daily[:7]]
            week_lows = [d[3] for d in daily[:7]]
            levels["PWH"] = max(week_highs)
            levels["PWL"] = min(week_lows)

        self._levels[symbol] = levels
        self._loaded_symbols.add(symbol)
        return levels

    def get_proximity_signal(
        self, symbol: str, price: float, direction: str, pip_size: float
    ) -> Dict:
        """
        Determine if price is at a key session level and whether
        that level acts as support or resistance for the proposed trade.
        """
        levels = self.load_levels(symbol)
        if not levels:
            return {"proximity": "NONE", "level": None, "pips": 999, "conviction": "NONE"}

        signals = []
        for level_name, level_price in levels.items():
            if level_price <= 0:
                continue
            pips_away = abs(price - level_price) / pip_size

            if pips_away > PROXIMITY_THRESHOLD_PIPS:
                continue

            if price > level_price and direction == "BUY":
                signals.append(
                    {
                        "level": level_name,
                        "price": level_price,
                        "pips": round(pips_away, 1),
                        "role": "BROKEN_RESISTANCE_NOW_SUPPORT",
                        "conviction": "HIGH",
                    }
                )
            elif price < level_price and direction == "SELL":
                signals.append(
                    {
                        "level": level_name,
                        "price": level_price,
                        "pips": round(pips_away, 1),
                        "role": "BROKEN_SUPPORT_NOW_RESISTANCE",
                        "conviction": "HIGH",
                    }
                )
            elif price < level_price and direction == "BUY":
                signals.append(
                    {
                        "level": level_name,
                        "price": level_price,
                        "pips": round(pips_away, 1),
                        "role": "APPROACHING_RESISTANCE",
                        "conviction": "LOW",
                    }
                )
            elif price > level_price and direction == "SELL":
                signals.append(
                    {
                        "level": level_name,
                        "price": level_price,
                        "pips": round(pips_away, 1),
                        "role": "APPROACHING_SUPPORT",
                        "conviction": "LOW",
                    }
                )

        if not signals:
            return {"proximity": "NONE", "level": None, "pips": 999, "conviction": "NONE"}

        best = min(signals, key=lambda x: x["pips"])
        return {
            "proximity": best["role"],
            "level": best["level"],
            "pips": best["pips"],
            "conviction": best["conviction"],
        }

    def invalidate_cache(self, symbol: str = None):
        """Force reload on next access (e.g., after new day starts)."""
        if symbol:
            self._loaded_symbols.discard(symbol)
            self._levels.pop(symbol, None)
        else:
            self._loaded_symbols.clear()
            self._levels.clear()
