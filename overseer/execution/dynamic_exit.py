from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from ml.l3_institutional_features import InstitutionalFeatureEngine

LOGGER = logging.getLogger("overseer.dynamic_exit")

ICEBERG_EXIT_ENABLED = os.getenv("ICEBERG_EXIT_ENABLED", "true").lower() == "true"
SPOOF_EXIT_ENABLED = os.getenv("SPOOF_EXIT_ENABLED", "true").lower() == "true"
VACUUM_EXIT_ENABLED = os.getenv("VACUUM_EXIT_ENABLED", "true").lower() == "true"
QUEUE_EXIT_ENABLED = os.getenv("QUEUE_EXIT_ENABLED", "true").lower() == "true"
HFT_EXIT_ENABLED = os.getenv("HFT_EXIT_ENABLED", "true").lower() == "true"
ADVERSE_EXIT_THRESHOLD = float(os.getenv("ADVERSE_EXIT_THRESHOLD", "0.4"))
TRAILING_STOP_PIPS = float(os.getenv("TRAILING_STOP_PIPS", "5.0"))
TRAILING_ACTIVATE_PIPS = float(os.getenv("TRAILING_ACTIVATE_PIPS", "10.0"))
STALE_POSITION_SECONDS = float(os.getenv("STALE_POSITION_SECONDS", "3600"))
TIME_STOP_TICKS = int(os.getenv("TIME_STOP_TICKS", "150"))
TIME_STOP_FLAT_PIPS = float(os.getenv("TIME_STOP_FLAT_PIPS", "2.0"))
UNFINISHED_EXIT_ENABLED = os.getenv("UNFINISHED_EXIT_ENABLED", "true").lower() == "true"
UNFINISHED_TOLERANCE_PIPS = float(os.getenv("UNFINISHED_EXIT_TOLERANCE_PIPS", "3.0"))
VOLUME_TP_ENABLED = os.getenv("VOLUME_TP_ENABLED", "true").lower() == "true"

LEGENDARY_BE_RR = float(os.getenv("LEGENDARY_BE_RR", "1.5"))
LEGENDARY_TRAIL_START_RR = float(os.getenv("LEGENDARY_TRAIL_START_RR", "2.0"))
LEGENDARY_TRAIL_STEP_PIPS = float(os.getenv("LEGENDARY_TRAIL_STEP_PIPS", "5"))
LEGENDARY_TP_RR = float(os.getenv("LEGENDARY_TP_RR", "4.0"))

_UNFINISHED_CACHE_PATH = Path(__file__).resolve().parent.parent / "logs" / "unfinished_business.json"
_HVN_CACHE_PATH = Path(__file__).resolve().parent.parent / "logs" / "hvn_levels.json"


class DynamicExitManager:
    def __init__(self) -> None:
        self.inst_engine = InstitutionalFeatureEngine()
        self.open_positions: dict[int, dict[str, Any]] = {}
        self._unfinished: dict[str, list[float]] = {}
        self._hvn_levels: dict[str, list[float]] = {}
        self._load_unfinished_cache()

    def _load_unfinished_cache(self) -> None:
        try:
            if _UNFINISHED_CACHE_PATH.exists():
                data = json.loads(_UNFINISHED_CACHE_PATH.read_text())
                if isinstance(data, dict):
                    self._unfinished = {k: [float(v) for v in vals] for k, vals in data.items() if isinstance(vals, list)}
        except Exception:
            self._unfinished = {}

    def load_hvn_levels(self, levels: dict[str, list[float]]) -> None:
        self._hvn_levels = levels

    def register_position(self, ticket: int, symbol: str, direction: str,
                          entry_price: float, sl_price: float,
                          tp_price: float, lot_size: float,
                          is_legendary: bool = False, sl_pips: float = 5.0) -> None:
        import time
        self.open_positions[ticket] = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "lot_size": lot_size,
            "breakeven_moved": False,
            "trailing_activated": False,
            "best_pnl_pips": 0.0,
            "entry_time": time.monotonic(),
            "entry_tick_count": 0,
            "is_legendary": is_legendary,
            "sl_pips": sl_pips,
        }

    def set_entry_tick_count(self, ticket: int, tick_count: int) -> None:
        position = self.open_positions.get(ticket)
        if position is not None:
            position["entry_tick_count"] = tick_count

    def unregister_position(self, ticket: int) -> None:
        self.open_positions.pop(ticket, None)

    def confirm_sl_update(self, ticket: int, new_sl: float, reason: str) -> None:
        position = self.open_positions.get(ticket)
        if position is None:
            return
        position["sl_price"] = new_sl
        if reason == "move_breakeven":
            position["breakeven_moved"] = True
        elif reason == "activate_trailing":
            position["trailing_activated"] = True
            position["breakeven_moved"] = True
        elif reason == "move_trailing_sl":
            position["current_trailing_sl"] = new_sl

    def evaluate_exit(self, ticket: int, tick: dict[str, Any]) -> dict[str, Any]:
        position = self.open_positions.get(ticket)
        if position is None:
            return {"should_exit": False, "reason": "unknown_position"}

        mbo_event = {
            "action": tick.get("mbo_action", "ADD"),
            "order_id": tick.get("mbo_order_id", ""),
            "price": float(tick.get("bid", 0) + tick.get("ask", 0)) / 2.0,
            "size": float(tick.get("ask_size", 0) + tick.get("bid_size", 0)),
            "timestamp_ns": int(tick.get("timestamp", 0)),
        }
        bid = float(tick.get("bid", 0))
        ask = float(tick.get("ask", 0))
        self.inst_engine.update_best(bid, ask)
        inst_features = self.inst_engine.process_event(mbo_event)

        direction = position["direction"]
        symbol = position["symbol"]

        if SPOOF_EXIT_ENABLED and inst_features.get("spoof_reversal_signal", 0.0) > 0:
            spoof_side = "bid" if bid > 0 and abs(inst_features.get("spoof_volume_vanished", 0)) > 0 else "ask"
            if (direction == "BUY" and spoof_side == "bid") or (direction == "SELL" and spoof_side == "ask"):
                LOGGER.warning("SPOOF EXIT: ticket=%d direction=%s spoof_side=%s vanished=%.0f", ticket, direction, spoof_side, inst_features.get("spoof_volume_vanished", 0))
                return {"should_exit": True, "reason": "spoof_reversal", "features": inst_features}

        if VACUUM_EXIT_ENABLED and inst_features.get("liquidity_vacuum_signal", 0.0) > 0:
            cv = inst_features.get("liquidity_vacuum_cv", 0.0)
            cascade = inst_features.get("vacuum_cascade_depth", 0.0)
            LOGGER.warning("VACUUM EXIT: ticket=%d cv=%.1f cascade=%.0f", ticket, cv, cascade)
            return {"should_exit": True, "reason": "liquidity_vacuum", "features": inst_features}

        adverse_risk = inst_features.get("adverse_selection_risk", 0.0)
        if adverse_risk >= ADVERSE_EXIT_THRESHOLD:
            LOGGER.warning("ADVERSE EXIT: ticket=%d risk=%.2f", ticket, adverse_risk)
            return {"should_exit": True, "reason": "adverse_selection", "features": inst_features}

        if QUEUE_EXIT_ENABLED and inst_features.get("queue_exhaustion_signal", 0.0) > 0:
            attrition = inst_features.get("queue_attrition_pct", 0.0)
            if direction == "BUY" and attrition > 0.8:
                LOGGER.info("QUEUE EXHAUSTION EXIT: ticket=%d attrition=%.2f - sell pressure exhausted, holding long", ticket, attrition)
            elif direction == "SELL" and attrition > 0.8:
                LOGGER.info("QUEUE EXHAUSTION EXIT: ticket=%d attrition=%.2f - buy pressure exhausted, holding short", ticket, attrition)
            elif attrition < 0.3:
                LOGGER.warning("QUEUE COLLAPSE EXIT: ticket=%d attrition=%.2f - queue defense failed", ticket, attrition)
                return {"should_exit": True, "reason": "queue_collapse", "features": inst_features}

        if HFT_EXIT_ENABLED and inst_features.get("hft_cluster_detected", 0.0) > 0:
            hft_vol = inst_features.get("hft_synchronized_volume", 0.0)
            if hft_vol > 200:
                LOGGER.warning("HFT CLUSTER EXIT: ticket=%d hft_vol=%.0f - predatory algorithm detected", ticket, hft_vol)
                return {"should_exit": True, "reason": "hft_predator", "features": inst_features}

        if ICEBERG_EXIT_ENABLED:
            iceberg_count = inst_features.get("iceberg_replenish_count", 0.0)
            if iceberg_count >= 5.0:
                if (direction == "BUY" and ask > 0 and inst_features.get("iceberg_detected", 0) > 0):
                    LOGGER.info("ICEBERG SHIELD: ticket=%d iceberg_count=%.0f holding long", ticket, iceberg_count)
                elif (direction == "SELL" and bid > 0 and inst_features.get("iceberg_detected", 0) > 0):
                    LOGGER.info("ICEBERG SHIELD: ticket=%d iceberg_count=%.0f holding short", ticket, iceberg_count)

        try:
            from config.instrument_config import InstrumentConfig
            profile = InstrumentConfig.get_instance().get_profile(symbol)
            pip_size = profile.pip_size
        except Exception:
            pip_size = 0.01 if "JPY" in symbol or symbol.startswith("XAU") else 0.0001
        entry = position["entry_price"]
        current_mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else entry

        if direction == "BUY":
            pnl_pips = (current_mid - entry) / pip_size
        else:
            pnl_pips = (entry - current_mid) / pip_size

        if pnl_pips > position["best_pnl_pips"]:
            position["best_pnl_pips"] = pnl_pips

        # --- Time Stop ---
        if TIME_STOP_TICKS > 0 and position.get("entry_tick_count", 0) > 0:
            current_tick_count = tick.get("_tick_count", 0)
            ticks_elapsed = current_tick_count - position["entry_tick_count"]
            if ticks_elapsed > TIME_STOP_TICKS and abs(pnl_pips) < TIME_STOP_FLAT_PIPS:
                LOGGER.warning("TIME STOP: ticket=%d elapsed=%d ticks pnl=%.1f pips", ticket, ticks_elapsed, pnl_pips)
                return {"should_exit": True, "reason": "time_stop", "features": inst_features}

        # --- Unfinished Business Exit ---
        if UNFINISHED_EXIT_ENABLED:
            unfinished_targets = self._unfinished.get(symbol, [])
            for target in unfinished_targets:
                distance_pips = abs(current_mid - target) / pip_size if pip_size > 0 else 999
                if distance_pips < UNFINISHED_TOLERANCE_PIPS:
                    if direction == "SELL" and target > current_mid:
                        LOGGER.warning("UNFINISHED BUSINESS EXIT: ticket=%d target=%.5f above current=%.5f — magnet pull on short", ticket, target, current_mid)
                        return {"should_exit": True, "reason": "unfinished_business_magnet", "features": inst_features}
                    if direction == "BUY" and target < current_mid:
                        LOGGER.warning("UNFINISHED BUSINESS EXIT: ticket=%d target=%.5f below current=%.5f — magnet pull on long", ticket, target, current_mid)
                        return {"should_exit": True, "reason": "unfinished_business_magnet", "features": inst_features}

        # --- Volume-Based TP ---
        if VOLUME_TP_ENABLED and pnl_pips > 0:
            hvn_list = self._hvn_levels.get(symbol, [])
            for hvn_price in hvn_list:
                if direction == "BUY" and hvn_price > current_mid:
                    distance_pips = (hvn_price - current_mid) / pip_size
                    if distance_pips > 0 and distance_pips < 3:
                        LOGGER.info("VOLUME TP: ticket=%d HVN wall at %.5f (%.1f pips ahead) — tightening TP", ticket, hvn_price, distance_pips)
                        return {"should_exit": True, "reason": "volume_tp_hvn_wall", "features": inst_features}
                if direction == "SELL" and hvn_price < current_mid:
                    distance_pips = (current_mid - hvn_price) / pip_size
                    if distance_pips > 0 and distance_pips < 3:
                        LOGGER.info("VOLUME TP: ticket=%d HVN wall at %.5f (%.1f pips ahead) — tightening TP", ticket, hvn_price, distance_pips)
                        return {"should_exit": True, "reason": "volume_tp_hvn_wall", "features": inst_features}

        # --- Legendary Position Exit Logic ---
        if position.get("is_legendary", False):
            sl_pips = position.get("sl_pips", 5.0)
            be_target_pips = sl_pips * LEGENDARY_BE_RR
            trail_start_pips = sl_pips * LEGENDARY_TRAIL_START_RR

            if not position["breakeven_moved"] and pnl_pips >= be_target_pips:
                new_sl = entry + pip_size * 0.5 if direction == "BUY" else entry - pip_size * 0.5
                LOGGER.info(
                    "LEGENDARY BREAKEVEN: ticket=%d pnl=%.1f pips (target=%.1f)",
                    ticket, pnl_pips, be_target_pips,
                )
                return {"should_exit": False, "reason": "move_breakeven",
                        "new_sl": new_sl, "features": inst_features}

            if position["breakeven_moved"] and pnl_pips >= trail_start_pips:
                if direction == "BUY":
                    trail_sl = current_mid - LEGENDARY_TRAIL_STEP_PIPS * pip_size
                else:
                    trail_sl = current_mid + LEGENDARY_TRAIL_STEP_PIPS * pip_size

                current_sl = position.get("current_trailing_sl", position["sl_price"])
                should_move = (direction == "BUY" and trail_sl > current_sl) or \
                              (direction == "SELL" and trail_sl < current_sl)

                if should_move:
                    LOGGER.info(
                        "LEGENDARY TRAIL: ticket=%d pnl=%.1f pips trail_sl=%.5f",
                        ticket, pnl_pips, trail_sl,
                    )
                    return {"should_exit": False, "reason": "move_trailing_sl",
                            "new_sl": trail_sl, "features": inst_features}

                if direction == "BUY" and current_mid <= current_sl:
                    LOGGER.warning("LEGENDARY TRAIL HIT: ticket=%d pnl=%.1f pips", ticket, pnl_pips)
                    return {"should_exit": True, "reason": "legendary_trailing_stop", "features": inst_features}
                elif direction == "SELL" and current_mid >= current_sl:
                    LOGGER.warning("LEGENDARY TRAIL HIT: ticket=%d pnl=%.1f pips", ticket, pnl_pips)
                    return {"should_exit": True, "reason": "legendary_trailing_stop", "features": inst_features}

            if not position["breakeven_moved"] and not position.get("trailing_activated"):
                return {"should_exit": False, "reason": "legendary_hold", "features": inst_features}

        # --- Standard Breakeven / Trailing ---
        if not position["breakeven_moved"]:
            if pnl_pips >= TRAILING_ACTIVATE_PIPS:
                new_sl = entry + pip_size * 0.5 if direction == "BUY" else entry - pip_size * 0.5
                LOGGER.info("BREAKEVEN MOVE: ticket=%d pnl=%.1f pips", ticket, pnl_pips)
                return {"should_exit": False, "reason": "move_breakeven",
                        "new_sl": new_sl, "features": inst_features}

        if position["breakeven_moved"] and not position["trailing_activated"]:
            if pnl_pips >= TRAILING_ACTIVATE_PIPS + TRAILING_STOP_PIPS:
                LOGGER.info("TRAILING STOP ACTIVATED: ticket=%d best_pnl=%.1f pips", ticket, position["best_pnl_pips"])
                return {"should_exit": False, "reason": "activate_trailing",
                        "features": inst_features}

        if position.get("trailing_activated"):
            trail_sl_pips = position["best_pnl_pips"] - TRAILING_STOP_PIPS
            if pnl_pips <= trail_sl_pips and position["best_pnl_pips"] > TRAILING_STOP_PIPS + 2:
                LOGGER.warning("TRAILING STOP HIT: ticket=%d pnl=%.1f best=%.1f", ticket, pnl_pips, position["best_pnl_pips"])
                return {"should_exit": True, "reason": "trailing_stop", "features": inst_features}
            new_sl_pips = position["best_pnl_pips"] - TRAILING_STOP_PIPS
            if direction == "BUY":
                new_sl = entry + new_sl_pips * pip_size
            else:
                new_sl = entry - new_sl_pips * pip_size
            current_sl = position.get("current_trailing_sl", position["sl_price"])
            if (direction == "BUY" and new_sl > current_sl) or (direction == "SELL" and new_sl < current_sl):
                return {"should_exit": False, "reason": "move_trailing_sl",
                        "new_sl": new_sl, "features": inst_features}

        import time
        elapsed = time.monotonic() - position["entry_time"]
        if elapsed > STALE_POSITION_SECONDS and abs(pnl_pips) < 2.0:
            LOGGER.warning("STALE POSITION EXIT: ticket=%d elapsed=%.0fs pnl=%.1f pips", ticket, elapsed, pnl_pips)
            return {"should_exit": True, "reason": "stale_position", "features": inst_features}

        return {"should_exit": False, "reason": "hold", "features": inst_features}
