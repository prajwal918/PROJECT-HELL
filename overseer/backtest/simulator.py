"""Simulated trade executor for OVERSEER backtesting.

Mimics the real MT5 executor interface but simulates fills, spread,
slippage, and position management entirely in-memory.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger("overseer.backtest.simulator")

_SLIPPAGE_BUFFER_PIPS = 1.0


@dataclass
class SimPosition:
    ticket: int
    symbol: str
    direction: str
    entry_price: float
    sl_price: float
    tp_price: float
    lot_size: float
    open_time: int = 0
    partial_closed: float = 0.0

    @property
    def remaining_lots(self) -> float:
        return max(0.0, round(self.lot_size - self.partial_closed, 2))


@dataclass
class SimTrade:
    ticket: int
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    lot_size: float
    pnl: float
    pnl_pips: float
    exit_reason: str
    entry_tick: int
    exit_tick: int
    sl_price: float
    tp_price: float
    score: float
    gate_states: dict[str, bool] = field(default_factory=dict)
    framework_scores: dict[str, float] = field(default_factory=dict)


class SimExecutor:
    """In-memory trade simulator that mimics MT5 executor for backtesting."""

    _next_ticket = 100000

    def __init__(
        self,
        account_balance: float = 10000.0,
        slippage_pips: float = _SLIPPAGE_BUFFER_PIPS,
        max_spread_pips: float = 5.0,
        commission_per_lot: float = 7.0,
    ) -> None:
        self.account_balance = account_balance
        self.initial_balance = account_balance
        self.slippage_pips = slippage_pips
        self.max_spread_pips = max_spread_pips
        self.commission_per_lot = commission_per_lot
        self.open_positions: dict[int, SimPosition] = {}
        self.closed_trades: list[SimTrade] = []
        self._pip_cache: dict[str, float] = {}

    def _pip_size(self, symbol: str) -> float:
        if symbol not in self._pip_cache:
            try:
                from config.instrument_config import InstrumentConfig
                profile = InstrumentConfig.get_instance().get_profile(symbol)
                self._pip_cache[symbol] = profile.pip_size
            except Exception:
                if "JPY" in symbol.upper():
                    self._pip_cache[symbol] = 0.01
                elif symbol.upper().startswith("XAU"):
                    self._pip_cache[symbol] = 0.1
                else:
                    self._pip_cache[symbol] = 0.0001
        return self._pip_cache[symbol]

    def execute_trade(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        sl_pips: float,
        tp_pips: float,
        tick: dict[str, Any],
        tick_count: int,
        score: float,
        gate_states: dict[str, bool],
        framework_scores: dict[str, float],
    ) -> dict[str, Any] | None:
        direction = direction.upper()
        pip = self._pip_size(symbol)
        bid = float(tick.get("bid", 0))
        ask = float(tick.get("ask", 0))
        if bid <= 0 or ask <= 0:
            return None

        spread_pips = (ask - bid) / pip if pip > 0 else 999.0
        if spread_pips > self.max_spread_pips:
            return None

        is_buy = direction == "BUY"
        price = ask if is_buy else bid
        slippage = self.slippage_pips * pip
        fill_price = price + slippage if is_buy else price - slippage

        sl = fill_price - sl_pips * pip if is_buy else fill_price + sl_pips * pip
        tp = fill_price + tp_pips * pip if is_buy else fill_price - tp_pips * pip

        SimExecutor._next_ticket += 1
        ticket = SimExecutor._next_ticket

        self.open_positions[ticket] = SimPosition(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            entry_price=fill_price,
            sl_price=sl,
            tp_price=tp,
            lot_size=lot_size,
            open_time=tick_count,
        )

        commission = self.commission_per_lot * lot_size
        self.account_balance -= commission

        return {
            "ticket": ticket,
            "price": fill_price,
            "requested_price": price,
            "sl": sl,
            "tp": tp,
            "slippage_pips": round(abs(fill_price - price) / pip, 2),
            "sl_pips": round(sl_pips, 2),
            "tp_pips": round(tp_pips, 2),
            "retcode": 10009,
        }

    def close_trade(self, ticket: int, tick: dict[str, Any], tick_count: int, reason: str = "") -> bool:
        pos = self.open_positions.get(ticket)
        if pos is None:
            return False
        return self._close_position(pos, tick, tick_count, reason or "MANUAL_CLOSE")

    def close_trade_partial(self, ticket: int, lots: float, tick: dict[str, Any]) -> bool:
        pos = self.open_positions.get(ticket)
        if pos is None:
            return False
        if lots <= 0 or lots >= pos.remaining_lots:
            return False
        pos.partial_closed += lots
        commission = self.commission_per_lot * lots
        self.account_balance -= commission
        LOGGER.debug("Partial close: ticket=%d closed=%.2f remaining=%.2f", ticket, lots, pos.remaining_lots)
        return True

    def modify_sl(self, ticket: int, new_sl: float) -> bool:
        pos = self.open_positions.get(ticket)
        if pos is None:
            return False
        pos.sl_price = new_sl
        return True

    def check_sl_tp(self, tick: dict[str, Any], tick_count: int) -> list[SimTrade]:
        """Check all open positions for SL/TP hits. Returns closed trades."""
        closed: list[SimTrade] = []
        to_remove: list[int] = []

        for ticket, pos in list(self.open_positions.items()):
            bid = float(tick.get("bid", 0))
            ask = float(tick.get("ask", 0))
            if bid <= 0 or ask <= 0:
                continue
            pip = self._pip_size(pos.symbol)

            if pos.direction == "BUY":
                if bid <= pos.sl_price:
                    self._close_position(pos, tick, tick_count, "STOP_LOSS")
                    to_remove.append(ticket)
                    closed.append(self.closed_trades[-1])
                elif ask >= pos.tp_price:
                    self._close_position(pos, tick, tick_count, "TAKE_PROFIT")
                    to_remove.append(ticket)
                    closed.append(self.closed_trades[-1])
            else:
                if ask >= pos.sl_price:
                    self._close_position(pos, tick, tick_count, "STOP_LOSS")
                    to_remove.append(ticket)
                    closed.append(self.closed_trades[-1])
                elif bid <= pos.tp_price:
                    self._close_position(pos, tick, tick_count, "TAKE_PROFIT")
                    to_remove.append(ticket)
                    closed.append(self.closed_trades[-1])

        for t in to_remove:
            self.open_positions.pop(t, None)

        return closed

    def _close_position(self, pos: SimPosition, tick: dict[str, Any], tick_count: int, reason: str) -> bool:
        pip = self._pip_size(pos.symbol)
        is_buy = pos.direction == "BUY"
        bid = float(tick.get("bid", 0))
        ask = float(tick.get("ask", 0))

        if reason == "STOP_LOSS":
            exit_price = pos.sl_price
        elif reason == "TAKE_PROFIT":
            exit_price = pos.tp_price
        else:
            exit_price = bid if is_buy else ask

        lots = pos.remaining_lots
        if is_buy:
            pnl_pips = (exit_price - pos.entry_price) / pip
        else:
            pnl_pips = (pos.entry_price - exit_price) / pip

        pip_value = 10.0
        pnl = pnl_pips * pip_value * lots
        commission = self.commission_per_lot * lots
        pnl -= commission

        self.account_balance += pnl

        trade = SimTrade(
            ticket=pos.ticket,
            symbol=pos.symbol,
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            lot_size=lots,
            pnl=round(pnl, 2),
            pnl_pips=round(pnl_pips, 2),
            exit_reason=reason,
            entry_tick=pos.open_time,
            exit_tick=tick_count,
            sl_price=pos.sl_price,
            tp_price=pos.tp_price,
            score=0.0,
        )
        self.closed_trades.append(trade)
        self.open_positions.pop(pos.ticket, None)
        return True

    @property
    def equity(self) -> float:
        return self.account_balance
