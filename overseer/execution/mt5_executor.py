from __future__ import annotations

import logging
import math
import os
from typing import Any

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - Linux containers often cannot import MT5.
    mt5 = None  # type: ignore[assignment]

LOGGER = logging.getLogger("overseer.mt5_executor")

_SLIPPAGE_BUFFER_PIPS = float(os.getenv("SLIPPAGE_BUFFER_PIPS", "1.0"))
_MAX_SLIPPAGE_PIPS = float(os.getenv("MAX_SLIPPAGE_PIPS", "3.0"))
_SPREAD_MAX_PIPS = float(os.getenv("GLOBAL_SPREAD_MAX_PIPS", "5.0"))


def _require_mt5() -> Any:
    if mt5 is None:
        raise RuntimeError("MetaTrader5 package is not available in this environment.")
    return mt5


def connect_mt5(account: int | str, password: str, server: str) -> bool:
    client = _require_mt5()
    if not client.initialize():
        code, desc = client.last_error()
        raise RuntimeError(f"MT5 initialize failed: {code} {desc}")
    if not client.login(int(account), password=password, server=server):
        code, desc = client.last_error()
        client.shutdown()
        raise RuntimeError(f"MT5 login failed: {code} {desc}")
    LOGGER.info("Connected to MT5 account %s on %s", account, server)
    return True


def _pip_size(symbol: str) -> float:
    try:
        from config.instrument_config import InstrumentConfig
        profile = InstrumentConfig.get_instance().get_profile(symbol)
        return profile.pip_size
    except Exception:
        if "JPY" in symbol:
            return 0.01
        if symbol.upper().startswith("XAU"):
            return 0.01
        return 0.0001


def _estimate_slippage(tick: Any, pip: float) -> float:
    """Estimate expected slippage in price units from the current spread."""
    if tick is None:
        return _SLIPPAGE_BUFFER_PIPS * pip
    spread = float(tick.ask - tick.bid)
    return spread * 0.5 + _SLIPPAGE_BUFFER_PIPS * pip


def _check_spread(symbol: str, tick: Any, pip: float) -> bool:
    if tick is None:
        return False
    spread_pips = (float(tick.ask) - float(tick.bid)) / pip if pip > 0 else 999.0
    symbol_spread_key = f"SPREAD_MAX_{symbol.upper()}"
    env_val = os.getenv(symbol_spread_key, "")
    try:
        max_pips = float(env_val) if env_val else 0.0
    except (ValueError, TypeError):
        max_pips = 0.0
    if not max_pips:
        try:
            from config.instrument_config import InstrumentConfig
            profile = InstrumentConfig.get_instance().get_profile(symbol)
            max_pips = profile.spread_max_pips
        except Exception:
            max_pips = _SPREAD_MAX_PIPS
    if spread_pips > max_pips:
        LOGGER.error(
            "Spread too wide for %s: %.1f pips > max %.1f pips — trade rejected",
            symbol, spread_pips, max_pips,
        )
        return False
    return True


def execute_trade(symbol: str, direction: str, lot_size: float, sl_pips: float, tp_pips: float) -> dict[str, Any] | None:
    client = _require_mt5()
    direction = direction.upper()
    tick = client.symbol_info_tick(symbol)
    info = client.symbol_info(symbol)
    if tick is None or info is None:
        code, desc = client.last_error()
        LOGGER.error("MT5 symbol/tick lookup failed for %s: %s %s", symbol, code, desc)
        return None

    if not info.visible:
        client.symbol_select(symbol, True)

    pip = _pip_size(symbol)

    if not _check_spread(symbol, tick, pip):
        return None

    is_buy = direction == "BUY"
    order_type = client.ORDER_TYPE_BUY if is_buy else client.ORDER_TYPE_SELL
    price = float(tick.ask if is_buy else tick.bid)

    slippage = _estimate_slippage(tick, pip)
    estimated_fill = price + slippage if is_buy else price - slippage
    estimated_slippage_pips = abs(estimated_fill - price) / pip if pip > 0 else 0
    if estimated_slippage_pips > _MAX_SLIPPAGE_PIPS:
        LOGGER.error(
            "Slippage too high: %s %.1f pips > max %.1f pips — trade rejected",
            symbol, estimated_slippage_pips, _MAX_SLIPPAGE_PIPS,
        )
        return None

    # Use estimated fill for order SL/TP (MT5 will place these);
    # after fill, recompute actual SL/TP from the real fill price.
    est_sl = estimated_fill - sl_pips * pip if is_buy else estimated_fill + sl_pips * pip
    est_tp = estimated_fill + tp_pips * pip if is_buy else estimated_fill - tp_pips * pip

    request = {
        "action": client.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot_size),
        "type": order_type,
        "price": price,
        "sl": est_sl,
        "tp": est_tp,
        "deviation": 10,
        "magic": 12012012,
        "comment": "OVERSEER v12",
        "type_time": client.ORDER_TIME_GTC,
        "type_filling": client.ORDER_FILLING_IOC,
    }
    result = client.order_send(request)
    if result is None or result.retcode != client.TRADE_RETCODE_DONE:
        code, desc = client.last_error()
        retcode = getattr(result, "retcode", "NO_RESULT")
        LOGGER.error("MT5 order failed: retcode=%s last_error=%s %s", retcode, code, desc)
        return None

    fill_price = float(result.price) if hasattr(result, "price") and result.price else price

    sl = fill_price - sl_pips * pip if is_buy else fill_price + sl_pips * pip
    tp = fill_price + tp_pips * pip if is_buy else fill_price - tp_pips * pip

    sl_distance_pips = abs(fill_price - sl) / pip if pip > 0 else 0
    tp_distance_pips = abs(tp - fill_price) / pip if pip > 0 else 0
    actual_slippage_pips = abs(fill_price - price) / pip if pip > 0 else 0

    # If actual fill deviates significantly from the SL/TP sent to MT5,
    # modify the position to use correct levels.
    if abs(fill_price - estimated_fill) > pip * 0.5:
        LOGGER.info(
            "Fill price differs from estimate: ticket=%d fill=%.5f est=%.5f — "
            "modifying SL/TP to actual fill-based levels",
            result.order, fill_price, estimated_fill,
        )
        _modify_sltp_after_fill(int(result.order), symbol, sl, tp, position_tp=est_tp)

    return {
        "ticket": int(result.order),
        "price": fill_price,
        "requested_price": price,
        "sl": sl,
        "tp": tp,
        "slippage_pips": round(actual_slippage_pips, 2),
        "sl_pips": round(sl_distance_pips, 2),
        "tp_pips": round(tp_distance_pips, 2),
        "retcode": int(result.retcode),
    }


def _modify_sltp_after_fill(
    ticket: int, symbol: str, new_sl: float, new_tp: float, position_tp: float,
) -> None:
    """Modify SL/TP on a just-opened position after fill price is known."""
    client = _require_mt5()
    positions = client.positions_get(ticket=ticket)
    if positions is None or not positions:
        LOGGER.warning("Cannot modify SL/TP after fill: ticket=%d not found", ticket)
        return
    position = positions[0]
    request = {
        "action": client.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "volume": position.volume,
        "position": ticket,
        "sl": new_sl,
        "tp": new_tp,
    }
    result = client.order_send(request)
    if result is None or result.retcode != client.TRADE_RETCODE_DONE:
        code, desc = client.last_error()
        LOGGER.error(
            "SL/TP modify after fill failed: ticket=%d retcode=%s error=%s %s",
            ticket, getattr(result, "retcode", None), code, desc,
        )
    else:
        LOGGER.info("SL/TP corrected after fill: ticket=%d sl=%.5f tp=%.5f", ticket, new_sl, new_tp)


def close_trade_partial(ticket: int, lots_to_close: float) -> bool:
    """Partially close a position by reducing its volume.

    Parameters
    ----------
    ticket : int
        The MT5 position ticket.
    lots_to_close : float
        Number of lots to close (must be < current volume).

    Returns
    -------
    bool
        True on success.
    """
    client = _require_mt5()
    positions = client.positions_get(ticket=ticket)
    if positions is None:
        LOGGER.error("MT5 positions_get() error for ticket %s (connection issue?)", ticket)
        return False
    if not positions:
        LOGGER.error("No open position found for ticket %s", ticket)
        return False

    position = positions[0]
    if lots_to_close <= 0 or lots_to_close >= position.volume:
        LOGGER.error(
            "Invalid partial close volume: ticket=%d volume=%.2f requested=%.2f",
            ticket, position.volume, lots_to_close,
        )
        return False

    tick = client.symbol_info_tick(position.symbol)
    if tick is None:
        LOGGER.error("No tick available for %s", position.symbol)
        return False

    is_buy = position.type == client.POSITION_TYPE_BUY
    request = {
        "action": client.TRADE_ACTION_DEAL,
        "position": ticket,
        "symbol": position.symbol,
        "volume": float(lots_to_close),
        "type": client.ORDER_TYPE_SELL if is_buy else client.ORDER_TYPE_BUY,
        "price": tick.bid if is_buy else tick.ask,
        "deviation": 10,
        "magic": 12012012,
        "comment": "OVERSEER partial close",
        "type_time": client.ORDER_TIME_GTC,
        "type_filling": client.ORDER_FILLING_IOC,
    }
    result = client.order_send(request)
    if result is None or result.retcode != client.TRADE_RETCODE_DONE:
        code, desc = client.last_error()
        LOGGER.error(
            "Partial close failed: ticket=%d retcode=%s error=%s %s",
            ticket, getattr(result, "retcode", None), code, desc,
        )
        return False
    LOGGER.info("Partial close OK: ticket=%d closed=%.2f lots", ticket, lots_to_close)
    return True


def close_trade(ticket: int) -> bool:
    client = _require_mt5()
    positions = client.positions_get(ticket=ticket)
    if positions is None:
        LOGGER.error("MT5 positions_get() error for ticket %s (connection issue?)", ticket)
        return False
    if not positions:
        LOGGER.error("No open position found for ticket %s", ticket)
        return False

    position = positions[0]
    tick = client.symbol_info_tick(position.symbol)
    if tick is None:
        LOGGER.error("No tick available for %s", position.symbol)
        return False

    is_buy = position.type == client.POSITION_TYPE_BUY
    request = {
        "action": client.TRADE_ACTION_DEAL,
        "position": ticket,
        "symbol": position.symbol,
        "volume": position.volume,
        "type": client.ORDER_TYPE_SELL if is_buy else client.ORDER_TYPE_BUY,
        "price": tick.bid if is_buy else tick.ask,
        "deviation": 10,
        "magic": 12012012,
        "comment": "OVERSEER close",
        "type_time": client.ORDER_TIME_GTC,
        "type_filling": client.ORDER_FILLING_IOC,
    }
    result = client.order_send(request)
    return bool(result and result.retcode == client.TRADE_RETCODE_DONE)


def get_open_positions() -> list[dict[str, Any]] | None:
    """Return currently open MT5 positions.

    Returns
    -------
    list[dict] | None
        List of position dicts on success, or *None* when MT5 returns
        an error (e.g. connection lost).  An empty list means "no open
        positions"; *None* means "could not determine".
    """
    client = _require_mt5()
    positions = client.positions_get()
    if positions is None:
        return None
    return [position._asdict() for position in positions]


def kelly_lot_size(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    account_balance: float,
    kelly_fraction: float = 0.25,
) -> float:
    if avg_loss == 0 or account_balance <= 0:
        return 0.01

    payoff = abs(avg_win / avg_loss)
    if payoff <= 0 or not math.isfinite(payoff):
        return 0.01

    edge = win_rate - ((1.0 - win_rate) / payoff)
    risk_fraction = max(0.0, edge) * kelly_fraction
    notional_risk = account_balance * risk_fraction
    lot_size = notional_risk / 1000.0
    return round(min(0.10, max(0.01, lot_size)), 2)


def modify_sl(ticket: int, new_sl: float) -> bool:
    client = _require_mt5()
    positions = client.positions_get(ticket=ticket)
    if positions is None:
        LOGGER.error("MT5 positions_get() error for ticket %s (connection issue?)", ticket)
        return False
    if not positions:
        LOGGER.error("No open position for ticket %s to modify SL", ticket)
        return False
    position = positions[0]
    request = {
        "action": client.TRADE_ACTION_SLTP,
        "symbol": position.symbol,
        "volume": position.volume,
        "position": ticket,
        "sl": new_sl,
        "tp": position.tp,
    }
    result = client.order_send(request)
    if result is None or result.retcode != client.TRADE_RETCODE_DONE:
        code, desc = client.last_error()
        LOGGER.error("SL modify failed: ticket=%s retcode=%s error=%s %s", ticket, getattr(result, "retcode", None), code, desc)
        return False
    LOGGER.info("SL modified: ticket=%d new_sl=%.5f", ticket, new_sl)
    return True


def shutdown_mt5() -> None:
    if mt5 is not None:
        mt5.shutdown()


class MT5ConnectionManager:
    _RECONNECT_MIN = float(os.getenv("MT5_RECONNECT_MIN", "2.0"))
    _RECONNECT_MAX = float(os.getenv("MT5_RECONNECT_MAX", "60.0"))
    _HEARTBEAT_INTERVAL = float(os.getenv("MT5_HEARTBEAT_INTERVAL", "30.0"))

    def __init__(self, account: int | str, password: str, server: str) -> None:
        self.account = int(account)
        self.password = password
        self.server = server
        self.connected = False
        self._reconnect_delay = self._RECONNECT_MIN

    def connect(self) -> bool:
        try:
            result = connect_mt5(self.account, self.password, self.server)
            self.connected = result
            if result:
                self._reconnect_delay = self._RECONNECT_MIN
            return result
        except Exception as exc:
            LOGGER.error("MT5 connect failed: %s", exc)
            self.connected = False
            return False

    def is_alive(self) -> bool:
        if mt5 is None:
            return False
        try:
            info = mt5.account_info()
            if info is not None:
                self.connected = True
                return True
        except Exception:
            pass
        self.connected = False
        return False

    def try_reconnect(self) -> bool:
        LOGGER.warning("MT5 connection lost — attempting reconnect (delay=%.1fs)", self._reconnect_delay)
        shutdown_mt5()
        import time
        time.sleep(self._reconnect_delay)
        success = self.connect()
        if success:
            LOGGER.info("MT5 reconnected successfully")
            self._reconnect_delay = self._RECONNECT_MIN
        else:
            self._reconnect_delay = min(self._reconnect_delay * 2, self._RECONNECT_MAX)
            LOGGER.error("MT5 reconnect failed — next attempt in %.1fs", self._reconnect_delay)
        return success

    async def heartbeat_loop(self) -> None:
        import asyncio
        while True:
            await asyncio.sleep(self._HEARTBEAT_INTERVAL)
            if not self.is_alive():
                LOGGER.warning("MT5 heartbeat: connection dead")
                self.try_reconnect()
