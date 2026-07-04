import os
import logging

log = logging.getLogger(__name__)

_ENABLED = os.getenv("STRUCTURAL_SL_ENABLED", "true").lower() == "true"
_MIN_BUFFER_PIPS = float(os.getenv("STRUCTURAL_SL_MIN_BUFFER_PIPS", "2.0"))
_MAX_SL_PIPS = float(os.getenv("STRUCTURAL_SL_MAX_PIPS", "50.0"))


class StructuralSL:
    def __init__(self):
        self._psych_levels = {}
        self._session_levels = {}
        self._sweep_levels = {}

    def update_psych_levels(self, symbol, levels):
        self._psych_levels[symbol] = levels

    def update_session_levels(self, symbol, levels):
        self._session_levels[symbol] = levels

    def update_sweep_levels(self, symbol, levels):
        self._sweep_levels[symbol] = levels

    def compute_sl(self, symbol, direction, entry_price, pip_size, default_sl_pips):
        if not _ENABLED:
            return entry_price + (-1 if direction == "BUY" else 1) * default_sl_pips * pip_size
        candidates = []
        default_sl = entry_price + (-1 if direction == "BUY" else 1) * default_sl_pips * pip_size
        psych = self._psych_levels.get(symbol, [])
        for lvl in psych:
            price = lvl.get("price", 0)
            if direction == "BUY" and price < entry_price:
                dist = (entry_price - price) / pip_size
                if dist > _MIN_BUFFER_PIPS:
                    candidates.append(price - _MIN_BUFFER_PIPS * pip_size)
            elif direction == "SELL" and price > entry_price:
                dist = (price - entry_price) / pip_size
                if dist > _MIN_BUFFER_PIPS:
                    candidates.append(price + _MIN_BUFFER_PIPS * pip_size)
        sess = self._session_levels.get(symbol, {})
        for key in ("pdh", "pdl", "pwh", "pwl"):
            price = sess.get(key, 0)
            if price <= 0:
                continue
            if direction == "BUY" and price < entry_price:
                dist = (entry_price - price) / pip_size
                if dist > _MIN_BUFFER_PIPS:
                    candidates.append(price - _MIN_BUFFER_PIPS * pip_size)
            elif direction == "SELL" and price > entry_price:
                dist = (price - entry_price) / pip_size
                if dist > _MIN_BUFFER_PIPS:
                    candidates.append(price + _MIN_BUFFER_PIPS * pip_size)
        sweep = self._sweep_levels.get(symbol, [])
        for lvl in sweep:
            price = lvl if isinstance(lvl, (int, float)) else lvl.get("price", 0)
            if direction == "BUY" and price < entry_price:
                dist = (entry_price - price) / pip_size
                if dist > _MIN_BUFFER_PIPS:
                    candidates.append(price - _MIN_BUFFER_PIPS * pip_size)
            elif direction == "SELL" and price > entry_price:
                dist = (price - entry_price) / pip_size
                if dist > _MIN_BUFFER_PIPS:
                    candidates.append(price + _MIN_BUFFER_PIPS * pip_size)
        if not candidates:
            return default_sl
        if direction == "BUY":
            best = min(candidates, key=lambda x: abs(x - default_sl))
            sl_dist_pips = (entry_price - best) / pip_size
            if sl_dist_pips > _MAX_SL_PIPS or sl_dist_pips < _MIN_BUFFER_PIPS:
                return default_sl
            return best
        else:
            best = min(candidates, key=lambda x: abs(x - default_sl))
            sl_dist_pips = (best - entry_price) / pip_size
            if sl_dist_pips > _MAX_SL_PIPS or sl_dist_pips < _MIN_BUFFER_PIPS:
                return default_sl
            return best


structural_sl = StructuralSL()
