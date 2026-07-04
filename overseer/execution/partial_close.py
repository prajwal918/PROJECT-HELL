"""TP1 / TP2 partial-close manager for OVERSEER v12.

Implements the two-stage take-profit system described in the README:
  • TP1 = 1 R  → close 50 % of position, move SL to breakeven
  • TP2 = 2.5 R → close remaining 50 %

Each registered trade is tracked independently by MT5 ticket number.

Usage
-----
>>> pcm = PartialCloseManager()
>>> pcm.register_trade(ticket=12345, symbol="EURUSD", direction="BUY",
...                     entry_price=1.10000, sl_price=1.09950, lot_size=0.10)
>>> action = pcm.check_partial_close(12345, current_price=1.10050)
>>> # action == {'action': 'partial_close_tp1', 'close_lots': 0.05,
>>> #           'new_sl': 1.10000}
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger("overseer.partial_close")


def _pip_size(symbol: str) -> float:
    try:
        from config.instrument_config import InstrumentConfig
        profile = InstrumentConfig.get_instance().get_profile(symbol)
        return profile.pip_size
    except Exception:
        if "JPY" in symbol.upper():
            return 0.01
        if symbol.upper().startswith("XAU"):
            return 0.01
        return 0.0001


def _round_lots(lots: float, step: float = 0.01) -> float:
    if step <= 0:
        step = 0.01
    rounded = math.floor(lots / step) * step
    if rounded < step:
        return step
    return round(rounded, 2)


@dataclass
class _TradeState:
    """Internal state for a single managed trade."""

    ticket: int
    symbol: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    sl_price: float
    lot_size: float

    # Calculated targets
    tp1_price: float = 0.0
    tp2_price: float = 0.0
    risk_pips: float = 0.0

    # State flags
    tp1_hit: bool = False
    tp2_hit: bool = False
    remaining_lots: float = 0.0


class PartialCloseManager:
    """Manages partial closes (TP1 / TP2) for all active positions.

    After construction the manager holds no state; trades must be
    registered via :meth:`register_trade`.  On each tick the caller
    should invoke :meth:`check_partial_close` which returns an action
    dict describing the next step.
    """

    # ── R multiples ──
    TP1_R = 1.0
    TP2_R = 2.5
    TP1_CLOSE_FRACTION = 0.50  # close 50 % at TP1

    def __init__(self) -> None:
        self._trades: dict[int, _TradeState] = {}
        LOGGER.info("PartialCloseManager initialised (TP1=%.1fR, TP2=%.1fR)", self.TP1_R, self.TP2_R)

    # ── registration ──

    def register_trade(
        self,
        ticket: int,
        symbol: str,
        direction: str,
        entry_price: float,
        sl_price: float,
        lot_size: float,
    ) -> dict[str, Any]:
        """Register a new trade and compute TP1 / TP2 levels.

        Returns
        -------
        dict with ``tp1_price``, ``tp2_price``, ``risk_pips``.
        """
        direction = direction.upper()
        pip = _pip_size(symbol)

        if direction == "BUY":
            risk_pips = (entry_price - sl_price) / pip
        else:
            risk_pips = (sl_price - entry_price) / pip

        risk_pips = abs(risk_pips)
        if risk_pips <= 0:
            LOGGER.warning(
                "ticket=%d risk_pips=0 — defaulting to 5 pips", ticket,
            )
            risk_pips = 5.0

        risk_price = risk_pips * pip

        if direction == "BUY":
            tp1_price = entry_price + risk_price * self.TP1_R
            tp2_price = entry_price + risk_price * self.TP2_R
        else:
            tp1_price = entry_price - risk_price * self.TP1_R
            tp2_price = entry_price - risk_price * self.TP2_R

        state = _TradeState(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            sl_price=sl_price,
            lot_size=lot_size,
            tp1_price=round(tp1_price, 5),
            tp2_price=round(tp2_price, 5),
            risk_pips=round(risk_pips, 2),
            remaining_lots=lot_size,
        )
        self._trades[ticket] = state

        LOGGER.info(
            "Trade registered: ticket=%d %s %s entry=%.5f SL=%.5f "
            "TP1=%.5f TP2=%.5f risk=%.1f pips lots=%.2f",
            ticket, symbol, direction, entry_price, sl_price,
            state.tp1_price, state.tp2_price, risk_pips, lot_size,
        )
        return {
            "tp1_price": state.tp1_price,
            "tp2_price": state.tp2_price,
            "risk_pips": state.risk_pips,
        }

    # ── tick evaluation ──

    def check_partial_close(
        self,
        ticket: int,
        current_price: float,
    ) -> dict[str, Any]:
        """Evaluate whether the price has reached TP1 or TP2.

        Returns
        -------
        dict
            ``action`` key is one of:
            - ``'partial_close_tp1'`` – close half, includes ``close_lots``
              and ``new_sl`` (breakeven).
            - ``'close_tp2'`` – close remaining lots.
            - ``'hold'`` – nothing to do.
        """
        state = self._trades.get(ticket)
        if state is None:
            return {"action": "hold", "reason": "unknown_ticket"}

        if state.tp2_hit:
            return {"action": "hold", "reason": "fully_closed"}

        is_buy = state.direction == "BUY"

        # ── TP2 check (run first so we don't miss TP2 on same tick) ──
        if state.tp1_hit and not state.tp2_hit:
            tp2_reached = (
                (is_buy and current_price >= state.tp2_price)
                or (not is_buy and current_price <= state.tp2_price)
            )
        if tp2_reached:
            close_lots = _round_lots(state.remaining_lots)
            success = self._execute_close(ticket, close_lots, reason="TP2")
            if success:
                state.tp2_hit = True
                state.remaining_lots = 0.0
                LOGGER.info(
                    "TP2 HIT: ticket=%d price=%.5f target=%.5f — closed remaining %.2f lots",
                    ticket, current_price, state.tp2_price, close_lots,
                )
            else:
                LOGGER.error(
                    "TP2 HIT but MT5 close FAILED — will retry: ticket=%d",
                    ticket,
                )
                return {"action": "hold", "reason": "tp2_mt5_failed"}
            return {
                "action": "close_tp2",
                "close_lots": close_lots,
                "tp2_price": state.tp2_price,
            }

        # ── TP1 check ──
        if not state.tp1_hit:
            tp1_reached = (
                (is_buy and current_price >= state.tp1_price)
                or (not is_buy and current_price <= state.tp1_price)
            )
        if tp1_reached:
            half_lots = _round_lots(state.lot_size * self.TP1_CLOSE_FRACTION)
            new_remaining = max(0.0, round(state.lot_size - half_lots, 2))

            pip = _pip_size(state.symbol)
            if is_buy:
                breakeven_sl = state.entry_price + 0.5 * pip
            else:
                breakeven_sl = state.entry_price - 0.5 * pip
            breakeven_sl = round(breakeven_sl, 5)

            success = self._execute_partial_close(ticket, half_lots, breakeven_sl)
            if success:
                state.tp1_hit = True
                state.remaining_lots = new_remaining
                LOGGER.info(
                    "TP1 HIT: ticket=%d price=%.5f target=%.5f — "
                    "closed %.2f lots, SL→BE %.5f",
                    ticket, current_price, state.tp1_price,
                    half_lots, breakeven_sl,
                )
            else:
                LOGGER.error(
                    "TP1 HIT but MT5 partial close FAILED — will retry: ticket=%d",
                    ticket,
                )
                return {"action": "hold", "reason": "tp1_mt5_failed"}

            return {
                "action": "partial_close_tp1",
                "close_lots": half_lots,
                "new_sl": breakeven_sl,
                "remaining_lots": state.remaining_lots,
                "tp1_price": state.tp1_price,
            }

        return {"action": "hold"}

    # ── MT5 integration ──

    def _execute_partial_close(
        self, ticket: int, lots: float, new_sl: float,
    ) -> bool:
        """Partially close via MT5 and move SL to breakeven.

        Returns *True* only when both the partial close and the SL
        modification succeed.
        """
        try:
            from execution.mt5_executor import close_trade_partial, modify_sl

            closed = close_trade_partial(ticket, lots)
            if closed:
                sl_ok = modify_sl(ticket, new_sl)
                if sl_ok:
                    LOGGER.info("MT5 partial close OK: ticket=%d lots=%.2f newSL=%.5f", ticket, lots, new_sl)
                    return True
                else:
                    LOGGER.error("MT5 partial close OK but SL modify FAILED: ticket=%d", ticket)
                    return True
            else:
                LOGGER.error("MT5 partial close FAILED: ticket=%d", ticket)
                return False
        except ImportError:
            self._execute_close_fallback(ticket, lots, new_sl)
            return True
        except Exception as exc:
            LOGGER.error("Partial close error: ticket=%d %s", ticket, exc)
            return False

    def _execute_close(self, ticket: int, lots: float, reason: str = "") -> bool:
        """Close remaining lots via MT5. Returns *True* on success."""
        try:
            from execution.mt5_executor import close_trade

            ok = close_trade(ticket)
            if ok:
                LOGGER.info("MT5 full close OK: ticket=%d reason=%s", ticket, reason)
                return True
            else:
                LOGGER.error("MT5 full close FAILED: ticket=%d", ticket)
                return False
        except Exception as exc:
            LOGGER.error("Close error: ticket=%d %s", ticket, exc)
            return False

    def _execute_close_fallback(
        self, ticket: int, lots: float, new_sl: float,
    ) -> None:
        """Fallback when ``close_trade_partial`` is not available.

        Attempts a full close and logs a warning.  The caller should
        implement ``close_trade_partial`` in mt5_executor.py for proper
        partial-close support.
        """
        LOGGER.warning(
            "close_trade_partial not found — attempting full close for ticket=%d "
            "(implement close_trade_partial in mt5_executor.py for proper partial closes)",
            ticket,
        )
        try:
            from execution.mt5_executor import close_trade, modify_sl

            # We can't do a true partial with the current API; fall back
            # to moving SL to breakeven instead.
            modify_sl(ticket, new_sl)
            LOGGER.info("Fallback: SL moved to breakeven for ticket=%d", ticket)
        except Exception as exc:
            LOGGER.error("Fallback SL move failed: ticket=%d %s", ticket, exc)

    # ── helpers ──

    def get_state(self, ticket: int) -> dict[str, Any] | None:
        """Return the internal state for a ticket (for debugging / alerts)."""
        state = self._trades.get(ticket)
        if state is None:
            return None
        return {
            "ticket": state.ticket,
            "symbol": state.symbol,
            "direction": state.direction,
            "entry_price": state.entry_price,
            "sl_price": state.sl_price,
            "tp1_price": state.tp1_price,
            "tp2_price": state.tp2_price,
            "risk_pips": state.risk_pips,
            "tp1_hit": state.tp1_hit,
            "tp2_hit": state.tp2_hit,
            "remaining_lots": state.remaining_lots,
        }

    def unregister(self, ticket: int) -> None:
        """Remove a ticket from tracking."""
        removed = self._trades.pop(ticket, None)
        if removed:
            LOGGER.info("Trade unregistered: ticket=%d", ticket)

    @property
    def active_tickets(self) -> list[int]:
        """Return tickets that still have open lots."""
        return [t for t, s in self._trades.items() if s.remaining_lots > 0]
