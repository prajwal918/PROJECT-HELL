from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.currency_exposure import (
    CurrencyExposureTracker,
    check_max_notional,
    check_margin_usage,
    check_spread_efficiency,
    is_rollover_block,
)

LOGGER = logging.getLogger("overseer.risk_engine")

MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "3.0"))
MAX_WEEKLY_LOSS_PCT = float(os.getenv("MAX_WEEKLY_LOSS_PCT", "6.0"))
MAX_DAILY_TRADES = int(os.getenv("MAX_DAILY_TRADES", "3"))
CONSECUTIVE_LOSS_LIMIT = int(os.getenv("CONSECUTIVE_LOSS_LIMIT", "2"))
MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "10.0"))
COOLDOWN_AFTER_LOSS_SECONDS = float(os.getenv("COOLDOWN_AFTER_LOSS_SECONDS", "60"))
COOLDOWN_AFTER_DISCONNECT_SECONDS = float(os.getenv("COOLDOWN_AFTER_DISCONNECT_SECONDS", "120"))
BLOCK_NEWS_MINUTES_BEFORE = int(os.getenv("BLOCK_NEWS_MINUTES_BEFORE", "5"))
BLOCK_NEWS_MINUTES_AFTER = int(os.getenv("BLOCK_NEWS_MINUTES_AFTER", "3"))
YEN_RISK_OFF_SURGE_PIPS = float(os.getenv("YEN_RISK_OFF_SURGE_PIPS", "50.0"))
OPTIONS_EXPIRATION_TIGHTEN_PCT = float(os.getenv("OPTIONS_EXPIRATION_TIGHTEN_PCT", "0.05"))

_OPTIONS_EXP_DATES = [
    "2026-01-09", "2026-02-06", "2026-03-06", "2026-04-03",
    "2026-05-01", "2026-06-05", "2026-07-02", "2026-08-06",
    "2026-09-04", "2026-10-01", "2026-11-06", "2026-12-04",
]

_MACRO_GRID_PATH = Path(__file__).resolve().parent.parent / "config" / "macro_grid.json"


class RiskEngine:
    def __init__(self, exposure_tracker: CurrencyExposureTracker) -> None:
        self._exposure = exposure_tracker
        self._peak_equity: float = 0.0
        self._last_loss_time: float = 0.0
        self._last_disconnect_time: float = 0.0
        self._news_block_until: float = 0.0
        self._yen_baseline_mids: dict[str, float] = {}
        self._macro_grid: dict[str, dict[str, float]] = {}
        self._load_macro_grid()

    def _load_macro_grid(self) -> None:
        try:
            if _MACRO_GRID_PATH.exists():
                data = json.loads(_MACRO_GRID_PATH.read_text())
                if isinstance(data, dict):
                    self._macro_grid = data
        except Exception:
            self._macro_grid = {}

    def update_yen_baseline(self, symbol: str, mid: float) -> None:
        if "6J" in symbol or "JPY" in symbol.upper():
            self._yen_baseline_mids[symbol] = mid

    def notify_disconnect(self) -> None:
        self._last_disconnect_time = __import__("time").monotonic()

    def notify_news_event(self, minutes_before: int = 0) -> None:
        import time
        duration = (minutes_before + BLOCK_NEWS_MINUTES_AFTER) * 60
        self._news_block_until = time.monotonic() + duration

    def _check_yen_risk_off(self, symbol: str, direction: str) -> tuple[bool, str]:
        if not self._yen_baseline_mids:
            return True, ""
        for yen_sym, baseline in self._yen_baseline_mids.items():
            from core.candle_aggregator import _pip_size
            pip = _pip_size(yen_sym)
            latest = self._yen_baseline_mids.get(yen_sym, baseline)
            surge_pips = (latest - baseline) / pip if pip > 0 else 0
            if surge_pips > YEN_RISK_OFF_SURGE_PIPS:
                if symbol != yen_sym and direction == "BUY":
                    return False, f"yen_risk_off: {yen_sym} surged {surge_pips:.0f} pips"
        return True, ""

    def _check_options_expiration(self) -> tuple[bool, str]:
        today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        if today_str in _OPTIONS_EXP_DATES:
            return True, f"options_expiration: tightened threshold by {OPTIONS_EXPIRATION_TIGHTEN_PCT}"
        for exp_date in _OPTIONS_EXP_DATES:
            try:
                exp_dt = datetime.strptime(exp_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                today_dt = datetime.now(tz=timezone.utc)
                days_to_exp = (exp_dt - today_dt).days
                if 0 < days_to_exp <= 2:
                    return True, f"options_expiration_approaching: {days_to_exp}d to {exp_date}"
            except Exception:
                pass
        return True, ""

    def _check_macro_grid(self, symbol: str, direction: str, current_mid: float) -> tuple[bool, str]:
        grid = self._macro_grid.get(symbol)
        if not grid:
            return True, ""
        yearly_high = grid.get("yearly_high", 0)
        yearly_low = grid.get("yearly_low", 0)
        monthly_high = grid.get("monthly_high", 0)
        monthly_low = grid.get("monthly_low", 0)
        if yearly_high > 0 and current_mid >= yearly_high and direction == "BUY":
            return True, ""
        if yearly_low > 0 and current_mid <= yearly_low and direction == "SELL":
            return True, ""
        return True, ""

    def check_all(
        self,
        conn: sqlite3.Connection,
        account_balance: float,
        symbol: str,
        direction: str,
        lot_size: float,
        sl_pips: float,
        spread_bps: float,
    ) -> tuple[bool, str]:
        now = __import__("time").monotonic()

        if now - self._last_disconnect_time < COOLDOWN_AFTER_DISCONNECT_SECONDS:
            remaining = COOLDOWN_AFTER_DISCONNECT_SECONDS - (now - self._last_disconnect_time)
            return False, f"Post-disconnect cooldown: {remaining:.0f}s remaining"

        if now - self._last_loss_time < COOLDOWN_AFTER_LOSS_SECONDS:
            remaining = COOLDOWN_AFTER_LOSS_SECONDS - (now - self._last_loss_time)
            return False, f"Post-loss cooldown: {remaining:.0f}s remaining"

        if now < self._news_block_until:
            remaining = self._news_block_until - now
            return False, f"News block: {remaining:.0f}s remaining"

        if is_rollover_block():
            return False, "Rollover block (20:55-21:05 UTC)"

        yen_ok, yen_reason = self._check_yen_risk_off(symbol, direction)
        if not yen_ok:
            return False, yen_reason

        daily_loss_limit = account_balance * (MAX_DAILY_LOSS_PCT / 100.0)
        weekly_loss_limit = account_balance * (MAX_WEEKLY_LOSS_PCT / 100.0)

        row = conn.execute(
            """
            SELECT
            COALESCE(SUM(CASE WHEN date(timestamp) = date('now') THEN pnl ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN timestamp >= datetime('now', '-7 days') THEN pnl ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN date(timestamp) = date('now') THEN 1 ELSE 0 END), 0)
            FROM trade_executions
            WHERE exit_price IS NOT NULL
            """
        ).fetchone()

        if row is not None:
            daily_pnl, weekly_pnl, daily_trades = row[0], row[1], row[2]

            if daily_pnl < -daily_loss_limit:
                return False, f"daily_loss_limit: pnl={daily_pnl:.2f} < -{daily_loss_limit:.2f}"

            if weekly_pnl < -weekly_loss_limit:
                return False, f"weekly_loss_limit: pnl={weekly_pnl:.2f} < -{weekly_loss_limit:.2f}"

            if daily_trades >= MAX_DAILY_TRADES:
                return False, f"max_daily_trades: {daily_trades} >= {MAX_DAILY_TRADES}"

        recent = conn.execute(
            """
            SELECT pnl FROM trade_executions
            WHERE exit_price IS NOT NULL
            ORDER BY timestamp DESC LIMIT ?
            """,
            (CONSECUTIVE_LOSS_LIMIT,),
        ).fetchall()

        if len(recent) >= CONSECUTIVE_LOSS_LIMIT and all(r[0] < 0 for r in recent):
            return False, f"consecutive_losses: {CONSECUTIVE_LOSS_LIMIT} in a row"

        current_equity = account_balance
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity
        if self._peak_equity > 0:
            drawdown_pct = (self._peak_equity - current_equity) / self._peak_equity * 100
            if drawdown_pct > MAX_DRAWDOWN_PCT:
                return False, f"max_drawdown: {drawdown_pct:.1f}% > {MAX_DRAWDOWN_PCT}%"

        ok, reason = self._exposure.check_new_position(symbol, direction)
        if not ok:
            return False, reason

        ok, reason = check_max_notional(symbol, lot_size, account_balance)
        if not ok:
            return False, reason

        ok, reason = check_margin_usage(account_balance)
        if not ok:
            return False, reason

        ok, reason = check_spread_efficiency(spread_bps, sl_pips)
        if not ok:
            return False, reason

        return True, ""

    def notify_loss(self) -> None:
        self._last_loss_time = __import__("time").monotonic()
