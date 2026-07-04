"""
trade_tracker.py – Monitors MT5 positions and records closures in the database.

Part of the OVERSEER forex trading system.  Polls MetaTrader 5 for position
changes and, when a tracked position disappears (i.e. is closed), retrieves
the closing deal details and persists exit_price / pnl / close_reason back
to the ``trade_executions`` table.  A database trigger
(``trg_trade_closed_features``) handles the downstream insert into
``model_features`` automatically.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None  # type: ignore[assignment]

from execution.mt5_executor import get_open_positions

logger = logging.getLogger("overseer.trade_tracker")


class TradeTracker:
    """Track live MT5 tickets and reconcile closures with the local database."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, poll_interval: float = 2.0) -> None:
        """Initialise the tracker.

        Parameters
        ----------
        poll_interval:
            Seconds between successive MT5 polls (used by external loop /
            scheduler – this class does *not* spawn its own thread).
        """
        self.poll_interval: float = poll_interval
        self.known_open_tickets: set[int] = set()
        self.ticket_to_trade_id: dict[int, int] = {}
        self._lock: threading.Lock = threading.Lock()

        logger.info(
            "TradeTracker initialised  (poll_interval=%.1fs)", poll_interval
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_trade(self, ticket: int, trade_id: int) -> None:
        """Register an MT5 *ticket* together with its database *trade_id*.

        Must be called immediately after a new position is opened so that the
        tracker is aware of it.
        """
        with self._lock:
            self.known_open_tickets.add(ticket)
            self.ticket_to_trade_id[ticket] = trade_id

        logger.info(
            "Registered ticket %d  ↔  trade_id %d", ticket, trade_id
        )

    def check_closed_positions(
        self, conn: sqlite3.Connection
    ) -> list[dict[str, Any]]:
        """Detect positions that have been closed since the last poll.

        Returns
        -------
        list[dict]
            One dict per newly-closed position with keys
            ``ticket``, ``trade_id``, ``exit_price``, ``pnl``,
            ``close_reason``.
        """
        if mt5 is None:
            logger.warning("MetaTrader5 not available – skipping poll")
            return []

        open_positions = get_open_positions()
        if open_positions is None:
            logger.warning(
                "MT5 positions_get() returned None — cannot determine "
                "open positions, skipping closure check"
            )
            return []

        open_tickets: set[int] = {
            int(pos["ticket"]) for pos in open_positions
        }

        # Determine which tracked tickets have disappeared
        with self._lock:
            closed_tickets: set[int] = self.known_open_tickets - open_tickets

        if not closed_tickets:
            return []

        logger.info(
            "Detected %d closed ticket(s): %s",
            len(closed_tickets),
            closed_tickets,
        )

        closed_trades: list[dict[str, Any]] = []

        for ticket in closed_tickets:
            with self._lock:
                trade_id: int | None = self.ticket_to_trade_id.get(ticket)

            if trade_id is None:
                logger.warning(
                    "Closed ticket %d has no mapped trade_id – skipping",
                    ticket,
                )
                continue

            # Retrieve closing deal details from MT5 history
            details = self._get_close_details(ticket)

            if details is None:
                logger.error(
                    "Could not resolve close details for ticket %d", ticket
                )
                continue

            # Persist to database
            success = self._update_trade_in_db(
                conn,
                trade_id,
                details["exit_price"],
                details["pnl"],
                details["close_reason"],
            )

            if success:
                closed_trades.append(
                    {
                        "ticket": ticket,
                        "trade_id": trade_id,
                        "exit_price": details["exit_price"],
                        "pnl": details["pnl"],
                        "close_reason": details["close_reason"],
                    }
                )

            # Remove from tracking regardless of DB success so we don't
            # retry indefinitely for a position that no longer exists.
            with self._lock:
                self.known_open_tickets.discard(ticket)
                self.ticket_to_trade_id.pop(ticket, None)

        return closed_trades

    def sync_existing_positions(self, conn: sqlite3.Connection) -> None:
        """Reconcile the database with MT5 on startup.

        * Trades marked open in the DB that are still open in MT5 are added
          to the tracking sets.
        * Trades marked open in the DB but **missing** from MT5 are treated
          as having been closed while the tracker was offline and are
          finalised with the best available information.
        """
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT trade_id, symbol
                FROM   trade_executions
                WHERE  exit_price IS NULL
                """
            )
            db_open_rows: list[tuple[int, str]] = cursor.fetchall()
        except sqlite3.Error:
            logger.exception("Failed to query open trades from database")
            return
        finally:
            cursor.close()

        if not db_open_rows:
            logger.info("No open trades found in database during sync")
            return

        logger.info(
            "Database reports %d open trade(s) – syncing with MT5",
            len(db_open_rows),
        )

        # Fetch live MT5 positions
        if mt5 is None:
            logger.warning(
                "MetaTrader5 not available – cannot sync existing positions"
            )
            return

        open_positions = get_open_positions()
        if open_positions is None:
            logger.warning(
                "MT5 positions_get() returned None during sync — "
                "cannot reconcile, leaving DB state unchanged"
            )
            return

        # Build a lookup: ticket -> position dict
        mt5_ticket_map: dict[int, dict[str, Any]] = {
            int(pos["ticket"]): pos for pos in open_positions
        }

        for trade_id, symbol in db_open_rows:
            # Try to find a matching MT5 position by ticket stored as
            # trade_id (convention: trade_id == MT5 ticket when opened
            # through the executor).  A more robust implementation might
            # store the ticket separately.
            matched_ticket: int | None = None

            for ticket, pos in mt5_ticket_map.items():
                if pos.get("symbol") == symbol:
                    # Heuristic: match by symbol.  When multiple positions
                    # exist for the same symbol this may need refinement.
                    matched_ticket = ticket
                    break

            if matched_ticket is not None:
                # Position is still alive – register for tracking
                with self._lock:
                    self.known_open_tickets.add(matched_ticket)
                    self.ticket_to_trade_id[matched_ticket] = trade_id

                logger.info(
                    "Synced: trade_id %d  ↔  ticket %d  (%s)",
                    trade_id,
                    matched_ticket,
                    symbol,
                )

                # Remove from map so it can't match a second DB row
                del mt5_ticket_map[matched_ticket]
            else:
                # Position is gone – it was closed while we were offline
                logger.warning(
                    "trade_id %d (%s) not found in MT5 – marking as "
                    "closed offline",
                    trade_id,
                    symbol,
                )
                self._update_trade_in_db(
                    conn,
                    trade_id,
                    exit_price=0.0,
                    pnl=0.0,
                    close_reason="CLOSED_OFFLINE",
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_close_details(self, ticket: int) -> dict[str, Any] | None:
        """Query MT5 deal history and extract closing-deal information.

        Parameters
        ----------
        ticket:
            The MT5 position ticket whose closing deal we want.

        Returns
        -------
        dict | None
            ``{exit_price, pnl, close_reason}`` on success, *None* on
            failure.
        """
        if mt5 is None:
            logger.error("MetaTrader5 module not available")
            return None

        now = datetime.now(tz=timezone.utc)
        date_from = now - timedelta(days=7)
        date_to = now + timedelta(days=1)

        try:
            deals = mt5.history_deals_get(
                date_from, date_to, position=ticket
            )
        except Exception:
            logger.exception(
                "MT5 history_deals_get failed for ticket %d", ticket
            )
            return None

        if deals is None or len(deals) == 0:
            logger.warning(
                "No deals found in MT5 history for ticket %d", ticket
            )
            return None

        # The closing deal is typically the last one for this position
        closing_deal = deals[-1]

        exit_price: float = float(closing_deal.price)
        profit: float = float(closing_deal.profit)

        # Derive close reason from the deal comment
        comment: str = (closing_deal.comment or "").lower()
        if "sl" in comment:
            close_reason = "STOP_LOSS"
        elif "tp" in comment:
            close_reason = "TAKE_PROFIT"
        else:
            close_reason = "MANUAL_CLOSE"

        logger.info(
            "Ticket %d closed: exit_price=%.5f  pnl=%.2f  reason=%s",
            ticket,
            exit_price,
            profit,
            close_reason,
        )

        return {
            "exit_price": exit_price,
            "pnl": profit,
            "close_reason": close_reason,
        }

    @staticmethod
    def _update_trade_in_db(
        conn: sqlite3.Connection,
        trade_id: int,
        exit_price: float,
        pnl: float,
        close_reason: str,
    ) -> bool:
        """Write the closing details into ``trade_executions``.

        The database trigger ``trg_trade_closed_features`` will
        automatically propagate the relevant row into ``model_features``.

        Returns
        -------
        bool
            *True* when the UPDATE succeeds, *False* otherwise.
        """
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE trade_executions
                SET    exit_price   = ?,
                       pnl          = ?,
                       closed_at    = datetime('now'),
                       close_reason = ?
                WHERE  trade_id     = ?
                """,
                (exit_price, pnl, close_reason, trade_id),
            )
            conn.commit()
            logger.info(
                "DB updated: trade_id %d  exit=%.5f  pnl=%.2f  reason=%s",
                trade_id,
                exit_price,
                pnl,
                close_reason,
            )
            return True
        except sqlite3.Error:
            logger.exception(
                "Failed to update trade_id %d in database", trade_id
            )
            return False
