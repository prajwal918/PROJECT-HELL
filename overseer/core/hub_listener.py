from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger("overseer.hub_listener")
MAX_CLOCK_DRIFT_MS = int(os.getenv("MAX_CLOCK_DRIFT_MS", "60000"))
_DISCONNECT_TIMEOUT = float(os.getenv("UDP_DISCONNECT_TIMEOUT", "30.0"))

_JPY_FUTURES_PREFIXES = ("6J",)


def _invert_jpy_price(symbol: str, price: float) -> float:
    if price <= 0:
        return price
    for prefix in _JPY_FUTURES_PREFIXES:
        if symbol.startswith(prefix):
            return round(1.0 / price, 5)
    return price


class ParseError(ValueError):
    """Raised when a UDP bridge packet is malformed."""


@dataclass(frozen=True)
class ConnectionEvent:
    event_type: str
    timestamp_ms: int
    message: str


def _parse_float(value: str, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ParseError(f"{field} must be numeric: {value!r}") from exc
    if not math.isfinite(parsed):
        raise ParseError(f"{field} must be finite: {value!r}")
    return parsed


def _parse_int(value: str, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ParseError(f"{field} must be integer: {value!r}") from exc


def _parse_json_l3(text: str) -> dict[str, Any] | None:
    """Try to parse a raw JSON L3/MBO event from Quantower or MotiveWave bridge."""
    if not text.startswith("{"):
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if "source" in obj:
        return obj
    if "type" in obj and obj["type"] in ("BRIDGE_HEARTBEAT", "BRIDGE_SHUTDOWN", "BRIDGE_STARTUP"):
        obj["source"] = "motivewave"
        return obj
    return None


def _classify_json_packet(obj: dict[str, Any]) -> str:
    """Classify a JSON UDP packet by bridge source and message type.

    Returns one of: 'motivewave_tick', 'motivewave_dom', 'motivewave_mbo',
    'motivewave_heartbeat', 'quantower_l2', 'unknown_json'
    """
    source = obj.get("source", "")
    msg_type = obj.get("type", "")

    if source == "motivewave":
        if msg_type == "TICK":
            return "motivewave_tick"
        if msg_type == "DOM_SNAPSHOT":
            return "motivewave_dom"
        if msg_type == "MBO_EVENT":
            return "motivewave_mbo"
        if msg_type in ("BRIDGE_STARTUP", "BRIDGE_SHUTDOWN", "BRIDGE_HEARTBEAT"):
            return "motivewave_heartbeat"
        return "motivewave_other"

    if source == "quantower":
        return "quantower_l2"

    if source == "FXCM":
        if msg_type == "TICK":
            return "fxcm_tick"
        if msg_type == "DOM_SNAPSHOT":
            return "fxcm_dom"
        if msg_type == "HEARTBEAT":
            return "fxcm_heartbeat"
        return "fxcm_other"

    if msg_type == "overseer_bridge_startup":
        return "quantower_heartbeat"

    return "unknown_json"


def _motivewave_tick_to_standard(obj: dict[str, Any], cached_dom: dict | None = None) -> dict[str, Any]:
    """Convert MotiveWave TICK message to OVERSEER standard tick format."""
    symbol = obj.get("symbol", "")
    is_jpy = any(symbol.startswith(p) for p in _JPY_FUTURES_PREFIXES)

    raw_bid = float(obj.get("bid_price", 0))
    raw_ask = float(obj.get("ask_price", 0))

    if cached_dom and (raw_bid <= 0 or raw_ask <= 0):
        cb = cached_dom.get("bids", [])
        ca = cached_dom.get("asks", [])
        if raw_bid <= 0 and cb:
            raw_bid = float(cb[0].get("price", 0))
        if raw_ask <= 0 and ca:
            raw_ask = float(ca[0].get("price", 0))

    tick_price = float(obj.get("price", 0))
    if raw_bid <= 0 and tick_price > 0:
        raw_bid = tick_price
    if raw_ask <= 0 and tick_price > 0:
        raw_ask = tick_price

    bid = _invert_jpy_price(symbol, raw_bid)
    ask = _invert_jpy_price(symbol, raw_ask)
    if bid > ask and ask > 0:
        bid, ask = ask, bid

    dom = cached_dom if cached_dom else {"bids": [], "asks": [], "source": "motivewave"}
    if is_jpy and dom.get("bids"):
        dom = {**dom, "bids": [{**b, "price": _invert_jpy_price(symbol, float(b["price"]))} for b in dom.get("bids", [])],
                           "asks": [{**a, "price": _invert_jpy_price(symbol, float(a["price"]))} for a in dom.get("asks", [])]}

    return {
        "symbol": obj.get("symbol", ""),
        "bid": bid,
        "bid_size": float(obj.get("bid_size", 0)),
        "ask": ask,
        "ask_size": float(obj.get("ask_size", 0)),
        "dom": dom,
        "dom_json": json.dumps(dom) if dom.get("bids") or dom.get("asks") else "{}",
        "delta": 0.0,
        "timestamp": int(obj.get("timestamp", 0)),
        "source": "motivewave",
        "mw_tick_price": tick_price,
        "mw_tick_volume": int(obj.get("volume", 0)),
        "mw_is_ask_tick": bool(obj.get("is_ask_tick", False)),
        "mw_exch_order_id": int(obj.get("exch_order_id", 0)),
        "open_interest": int(obj.get("open_interest", 0)),
    }


def _motivewave_dom_to_standard(obj: dict[str, Any]) -> dict[str, Any]:
    """Convert MotiveWave DOM_SNAPSHOT to OVERSEER standard tick + DOM format."""
    symbol = obj.get("symbol", "")
    bids = obj.get("bids", [])
    asks = obj.get("asks", [])

    best_bid = float(bids[0]["price"]) if bids else 0.0
    best_bid_size = float(bids[0]["size"]) if bids else 0.0
    best_ask = float(asks[0]["price"]) if asks else 0.0
    best_ask_size = float(asks[0]["size"]) if asks else 0.0

    best_bid = _invert_jpy_price(symbol, best_bid)
    best_ask = _invert_jpy_price(symbol, best_ask)

    inv_bids = [{**b, "price": _invert_jpy_price(symbol, float(b["price"]))} for b in bids] if any(symbol.startswith(p) for p in _JPY_FUTURES_PREFIXES) else bids
    inv_asks = [{**a, "price": _invert_jpy_price(symbol, float(a["price"]))} for a in asks] if any(symbol.startswith(p) for p in _JPY_FUTURES_PREFIXES) else asks

    dom = {
        "bids": inv_bids,
        "asks": inv_asks,
        "source": "motivewave",
    }

    tick = {
        "symbol": symbol,
        "bid": best_bid,
        "bid_size": best_bid_size,
        "ask": best_ask,
        "ask_size": best_ask_size,
        "dom": dom,
        "dom_json": json.dumps(dom),
        "delta": 0.0,
        "timestamp": int(obj.get("timestamp", 0)),
        "source": "motivewave",
        "_mw_dom_snapshot": True,
    }

    if best_ask > best_bid and best_bid > 0:
        pass
    elif best_bid > 0 or best_ask > 0:
        pass

    return tick



def _motivewave_mbo_to_standard(obj: dict[str, Any]) -> dict[str, Any]:
    """Convert a MotiveWave MBO_EVENT to OVERSEER standard L3 format.
    Output matches what _drain_l3_queue and _process_motivewave_mbo expect:
    - type: "MBO_EVENT" (not the mapped action)
    - side: "BID" / "ASK" (uppercase)
    - action: "ADD" / "MODIFY" / "CANCEL" (uppercase, for _process_motivewave_mbo)
    """
    ts = obj.get("timestamp", 0)
    symbol = obj.get("symbol", "")
    side_raw = obj.get("side", "BID")
    action_raw = obj.get("action", "ADD")
    price = _parse_float(str(obj.get("price", 0)), "price")
    size = _parse_int(str(obj.get("size", 0)), "size")
    prev_count = _parse_int(str(obj.get("prev_order_count", 0)), "prev_order_count")
    cur_count = _parse_int(str(obj.get("cur_order_count", 0)), "cur_order_count")
    
    # Normalize side to uppercase BID/ASK
    side = side_raw.upper()
    if side not in ("BID", "ASK"):
        side = "BID"
    
    # Normalize action to uppercase ADD/MODIFY/CANCEL
    action = action_raw.upper()
    if action not in ("ADD", "MODIFY", "CANCEL"):
        action = "ADD"
    
    result = {
        "type": "MBO_EVENT",
        "symbol": symbol,
        "side": side,
        "action": action,
        "price": price,
        "size": size,
        "prev_order_count": prev_count,
        "cur_order_count": cur_count,
        "timestamp": ts,
        "source": "motivewave",
        "version": 2,
    }
    
    # JPY price inversion
    if any(symbol.startswith(p) for p in _JPY_FUTURES_PREFIXES):
        result["price"] = _invert_jpy_price(symbol, price)
    
    return result


def _fxcm_dom_to_standard(obj: dict[str, Any]) -> dict[str, Any]:
    dom_levels = obj.get("dom", [])
    bids = [l for l in dom_levels if l.get("side") == "bid"]
    asks = [l for l in dom_levels if l.get("side") == "ask"]
    best_bid = float(bids[0]["price"]) if bids else 0.0
    best_bid_size = float(bids[0]["size"]) if bids else 0.0
    best_ask = float(asks[0]["price"]) if asks else 0.0
    best_ask_size = float(asks[0]["size"]) if asks else 0.0
    dom = {"bids": bids, "asks": asks, "source": "FXCM"}
    return {
        "symbol": obj.get("symbol", ""),
        "bid": best_bid,
        "bid_size": best_bid_size,
        "ask": best_ask,
        "ask_size": best_ask_size,
        "dom": dom,
        "dom_json": json.dumps(dom),
        "delta": 0.0,
        "timestamp": int(obj.get("timestamp", 0)),
        "source": "FXCM",
        "_fxcm_dom_snapshot": True,
    }


def _fxcm_tick_to_standard(obj: dict[str, Any], cached_dom: dict | None = None) -> dict[str, Any]:
    dom = cached_dom if cached_dom else {"bids": [], "asks": [], "source": "FXCM"}
    return {
        "symbol": obj.get("symbol", ""),
        "bid": float(obj.get("bid", 0)),
        "bid_size": float(obj.get("bid_size", 0)),
        "ask": float(obj.get("ask", 0)),
        "ask_size": float(obj.get("ask_size", 0)),
        "dom": dom,
        "dom_json": json.dumps(dom) if dom.get("bids") or dom.get("asks") else "{}",
        "delta": 0.0,
        "timestamp": int(obj.get("timestamp", 0)),
        "source": "FXCM",
    }


def parse_payload(payload: bytes) -> dict[str, Any]:
    text = payload.decode("utf-8", errors="strict")

    json_l3 = _parse_json_l3(text)
    if json_l3 is not None:
        json_l3["_raw_l3"] = True
        return json_l3

    parts = text.split("|", 7)
    if len(parts) != 8:
        raise ParseError(f"Expected 8 pipe-delimited fields or JSON L3 object, received {len(parts)} pipe fields")

    symbol, bid, bid_size, ask, ask_size, dom_json, delta, timestamp = parts
    if not symbol:
        raise ParseError("symbol is required")

    try:
        dom = json.loads(dom_json)
    except json.JSONDecodeError as exc:
        raise ParseError("DOM_JSON is not valid JSON") from exc

    if not isinstance(dom, dict) or "bids" not in dom or "asks" not in dom:
        raise ParseError("DOM_JSON must contain bids and asks arrays")

    tick = {
        "symbol": symbol,
        "bid": _parse_float(bid, "bid"),
        "bid_size": _parse_float(bid_size, "bid_size"),
        "ask": _parse_float(ask, "ask"),
        "ask_size": _parse_float(ask_size, "ask_size"),
        "dom": dom,
        "dom_json": dom_json,
        "delta": _parse_float(delta, "delta"),
        "timestamp": _parse_int(timestamp, "timestamp"),
    }
    if tick["ask"] <= tick["bid"]:
        raise ParseError("ask must be greater than bid")
    return tick


class OverseerUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, queue: asyncio.Queue, event_queue: asyncio.Queue | None = None, l3_queue: asyncio.Queue | None = None) -> None:
        self.queue = queue
        self.event_queue = event_queue
        self.l3_queue = l3_queue
        self.transport: asyncio.DatagramTransport | None = None
        self.last_packet_monotonic = time.monotonic()
        self._dom_cache: dict[str, dict] = {}
        self._last_heartbeat_log: float = 0.0
        self._last_drift_log: float = 0.0
        self._last_malformed_log: float = 0.0
        self._malformed_count: int = 0
        self._rebind_count: int = 0

    def _forward_to_prophet(self, tick: dict[str, Any]) -> None:
        if not self.transport:
            return
        try:
            payload = {
                "symbol": tick.get("symbol", ""),
                "bid": tick.get("bid", 0),
                "bid_size": tick.get("bid_size", 0),
                "ask": tick.get("ask", 0),
                "ask_size": tick.get("ask_size", 0),
                "dom": tick.get("dom", {}),
                "delta": tick.get("delta", 0),
                "mw_tick_volume": tick.get("mw_tick_volume", 0),
                "mw_is_ask_tick": tick.get("mw_is_ask_tick", False),
                "mw_exch_order_id": tick.get("mw_exch_order_id", 0),
                "source": tick.get("source", ""),
                "time": int(tick.get("timestamp", 0)) / 1000.0,
            }
            data = json.dumps(payload).encode("utf-8")
            self.transport.sendto(data, ("127.0.0.1", 12346)) # PROPHET
            self.transport.sendto(data, ("127.0.0.1", 12347)) # NEXUS
        except Exception as exc:
            LOGGER.debug("Failed to forward tick to PROPHET: %s", exc)

    def _forward_l3_to_prophet(self, event: dict[str, Any]) -> None:
        if not self.transport:
            return
        try:
            payload = dict(event)
            payload["time"] = int(payload.get("timestamp", 0)) / 1000.0
            data = json.dumps(payload).encode("utf-8")
            self.transport.sendto(data, ("127.0.0.1", 12346)) # PROPHET
            self.transport.sendto(data, ("127.0.0.1", 12347)) # NEXUS
        except Exception as exc:
            LOGGER.debug("Failed to forward L3 event to PROPHET: %s", exc)

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport # type: ignore[assignment]
        
        # --- PERMANENT HFT FIX: Force huge UDP buffer ---
        try:
            sock = transport.get_extra_info('socket')
            if sock:
                import socket
                # Set socket buffer to 32MB (32 * 1024 * 1024)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 33554432)
                actual = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
                LOGGER.info("UDP Socket Buffer configured: %d bytes (Requested 32MB)", actual)
        except Exception as e:
            LOGGER.error("Failed to set large UDP buffer: %s", e)

        self._rebind_count += 1
        LOGGER.info("UDP listener bound and ready (Drift Tolerance: %sms, Rebinds: %d).", MAX_CLOCK_DRIFT_MS, self._rebind_count)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.last_packet_monotonic = time.monotonic()
        try:
            parsed = parse_payload(data)
            if parsed.get("_raw_l3"):
                parsed.pop("_raw_l3", None)
                category = _classify_json_packet(parsed)
            else:
                category = ""

            if category == "motivewave_tick":
                symbol = parsed.get("symbol", "")
                cached_dom = self._dom_cache.get(symbol)
                tick = _motivewave_tick_to_standard(parsed, cached_dom)
                self._forward_to_prophet(tick)
                local_ms = int(time.time() * 1000)
                drift_ms = abs(local_ms - tick["timestamp"])
                if drift_ms > MAX_CLOCK_DRIFT_MS:
                    now = time.monotonic()
                    if now - self._last_drift_log > 60.0:
                        self._last_drift_log = now
                        LOGGER.warning("Clock drift from %s: %sms. Check system clocks! (Throttled)", addr, drift_ms)
                    if drift_ms > 300000: return # Hard limit 5m
                try:
                    self.queue.put_nowait(tick)
                except asyncio.QueueFull:
                    LOGGER.debug("Tick queue full. Dropping MW tick for %s.", tick.get("symbol"))
                if self.l3_queue is not None:
                    try:
                        self.l3_queue.put_nowait(parsed)
                    except asyncio.QueueFull:
                        pass
                return

            if category == "motivewave_dom":
                tick = _motivewave_dom_to_standard(parsed)
                self._forward_to_prophet(tick)
                raw_bids = parsed.get("bids", [])
                raw_asks = parsed.get("asks", [])
                if raw_bids or raw_asks:
                    self._dom_cache[tick.get("symbol", "")] = {"bids": raw_bids, "asks": raw_asks, "source": "motivewave"}
                local_ms = int(time.time() * 1000)
                drift_ms = abs(local_ms - tick["timestamp"])
                if drift_ms > MAX_CLOCK_DRIFT_MS:
                    now = time.monotonic()
                    if now - self._last_drift_log > 60.0:
                        self._last_drift_log = now
                        LOGGER.warning("Clock drift from %s: %sms. Check system clocks! (Throttled)", addr, drift_ms)
                    if drift_ms > 300000: return # Hard limit 5m
                try:
                    self.queue.put_nowait(tick)
                except asyncio.QueueFull:
                    LOGGER.debug("Tick queue full. Dropping MW DOM for %s.", tick.get("symbol"))
                if self.l3_queue is not None:
                    try:
                        self.l3_queue.put_nowait(parsed)
                    except asyncio.QueueFull:
                        pass
                return

            if category == "motivewave_mbo":
                mbo_std = _motivewave_mbo_to_standard(parsed)
                self._forward_l3_to_prophet(mbo_std)
                if self.l3_queue is not None:
                    try:
                        self.l3_queue.put_nowait(mbo_std)
                    except asyncio.QueueFull:
                        LOGGER.debug("L3 queue full. Dropping MW MBO for %s.", mbo_std.get("symbol"))
                return

            if category == "motivewave_heartbeat":
                now = time.monotonic()
                msg_type = parsed.get("type", "unknown")
                version = parsed.get("version", "unknown")
                
                # Always log startups immediately
                if msg_type == "BRIDGE_STARTUP":
                    LOGGER.info("MotiveWave Bridge STARTUP: v%s", version)
                
                # Throttle normal heartbeats to 60s
                if now - self._last_heartbeat_log > 60.0:
                    self._last_heartbeat_log = now
                    pkts = parsed.get("packets", 0)
                    errs = parsed.get("errors", 0)
                    recs = parsed.get("reconnects", 0)
                    LOGGER.info("MotiveWave Heartbeat: v%s | type:%s | pkts:%d errs:%d recs:%d", 
                                version, msg_type, pkts, errs, recs)
                return

            if category == "fxcm_dom":
                tick = _fxcm_dom_to_standard(parsed)
                self._forward_to_prophet(tick)
                dom = tick.get("dom", {})
                if dom.get("bids") or dom.get("asks"):
                    self._dom_cache[tick.get("symbol", "")] = dom
                try:
                    self.queue.put_nowait(tick)
                except asyncio.QueueFull:
                    LOGGER.debug("Tick queue full. Dropping FXCM DOM for %s.", tick.get("symbol"))
                return

            if category == "fxcm_tick":
                symbol = parsed.get("symbol", "")
                cached_dom = self._dom_cache.get(symbol)
                tick = _fxcm_tick_to_standard(parsed, cached_dom)
                self._forward_to_prophet(tick)
                local_ms = int(time.time() * 1000)
                drift_ms = abs(local_ms - tick["timestamp"])
                if drift_ms > MAX_CLOCK_DRIFT_MS:
                    now = time.monotonic()
                    if now - self._last_drift_log > 60.0:
                        self._last_drift_log = now
                        LOGGER.warning("Clock drift from %s: %sms. Check system clocks! (Throttled)", addr, drift_ms)
                    if drift_ms > 300000: return # Hard limit 5m
                try:
                    self.queue.put_nowait(tick)
                except asyncio.QueueFull:
                    LOGGER.debug("Tick queue full. Dropping FXCM tick for %s.", symbol)
                return

            if category == "fxcm_heartbeat":
                LOGGER.debug("FXCM bridge heartbeat v%s", parsed.get("version"))
                return

            if self.l3_queue is not None:
                try:
                    self.l3_queue.put_nowait(parsed)
                except asyncio.QueueFull:
                    LOGGER.debug("L3 queue full. Dropping raw L3 packet from %s.", addr)
                return

            local_ms = int(time.time() * 1000)
            drift_ms = abs(local_ms - parsed.get("timestamp", local_ms))
            if drift_ms > MAX_CLOCK_DRIFT_MS:
                now = time.monotonic()
                if now - self._last_drift_log > 60.0:
                    self._last_drift_log = now
                    LOGGER.warning("Clock drift from %s: %sms. Check system clocks! (Throttled)", addr, drift_ms)
            if drift_ms > 300000: return  # Hard limit 5m
            try:
                self.queue.put_nowait(parsed)
            except asyncio.QueueFull:
                LOGGER.debug("Tick queue full. Dropping raw L3 packet from %s.", addr)
        except ParseError as exc:
            self._malformed_count += 1
            now = time.monotonic()
            if now - self._last_malformed_log > 60.0:
                self._last_malformed_log = now
                LOGGER.warning("Malformed UDP packets from %s: %s (total: %d in last 60s)", addr, exc, self._malformed_count)
                self._malformed_count = 0
        except asyncio.QueueFull:
            LOGGER.error("Tick queue full. Dropping packet from %s.", addr)

    def error_received(self, exc: Exception) -> None:
        LOGGER.error("UDP error received: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        LOGGER.warning("UDP listener connection lost: %s", exc)


async def watchdog(
    protocol_wrapper: list[OverseerUdpProtocol],
    queue: asyncio.Queue,
    host: str,
    port: int,
    event_queue: asyncio.Queue | None = None,
    l3_queue: asyncio.Queue | None = None
) -> None:
    """Watchdog that NEVER STOPS re-binding the UDP socket.
    HARDCODED: always reconnect, never give up, never crash.
    Exponential backoff capped at 30s."""
    disconnected = False
    consecutive_failures = 0
    loop = asyncio.get_running_loop()

    while True:
        await asyncio.sleep(5.0)
        protocol = protocol_wrapper[0]
        elapsed = time.monotonic() - protocol.last_packet_monotonic

        is_transport_closed = protocol.transport is None or protocol.transport.is_closing()

        if (elapsed > _DISCONNECT_TIMEOUT or is_transport_closed):
            if not disconnected or is_transport_closed:
                disconnected = True
                msg = f"UDP timeout ({elapsed:.0f}s)" if not is_transport_closed else "UDP transport closed"
                LOGGER.warning("Watchdog: %s. Rebinding %s:%s (attempt %d) — NEVER STOP...", msg, host, port, consecutive_failures + 1)

            try:
                if protocol.transport:
                    try:
                        protocol.transport.close()
                    except Exception:
                        pass

                new_protocol = OverseerUdpProtocol(queue, event_queue, l3_queue)
                await asyncio.sleep(1.0)

                try:
                    new_transport, _ = await loop.create_datagram_endpoint(
                        lambda: new_protocol,
                        local_addr=(host, port),
                        reuse_port=(os.name != "nt")
                    )
                except OSError as bind_err:
                    backoff = min(consecutive_failures * 2, 30)
                    LOGGER.error("Watchdog: Port bind failed: %s. Retry in %ds — NEVER STOP...", bind_err, backoff)
                    consecutive_failures += 1
                    await asyncio.sleep(backoff)
                    continue

                protocol_wrapper[0] = new_protocol
                consecutive_failures = 0
                LOGGER.info("Watchdog: UDP listener rebound OK (rebind #%d).", new_protocol._rebind_count)

                if event_queue:
                    await event_queue.put(ConnectionEvent("RECONNECTED", int(time.time() * 1000), "UDP listener restarted by watchdog"))

                disconnected = False
            except Exception as e:
                consecutive_failures += 1
                backoff = min(consecutive_failures * 2, 30)
                LOGGER.error("Watchdog: Rebind failed: %s (attempt %d). Retry in %ds — NEVER STOP...", e, consecutive_failures, backoff)
                await asyncio.sleep(backoff)
        else:
            if disconnected:
                disconnected = False
                consecutive_failures = 0
                LOGGER.info("Watchdog: UDP packet flow restored.")
            elif consecutive_failures > 0:
                consecutive_failures = 0


async def start_udp_listener(
    queue: asyncio.Queue,
    host: str = "0.0.0.0",
    port: int = int(os.getenv("OVERSEER_UDP_PORT", "65001")),
    event_queue: asyncio.Queue | None = None,
    l3_queue: asyncio.Queue | None = None,
) -> tuple[asyncio.DatagramTransport, OverseerUdpProtocol, asyncio.Task]:
    loop = asyncio.get_running_loop()
    protocol = OverseerUdpProtocol(queue, event_queue, l3_queue)
    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol, 
        local_addr=(host, port),
        reuse_port=(os.name != "nt")
    )
    
    # We use a list as a wrapper so the watchdog can replace the protocol instance
    protocol_wrapper = [protocol]
    watch_task = asyncio.create_task(watchdog(protocol_wrapper, queue, host, port, event_queue, l3_queue))
    
    return transport, protocol, watch_task
