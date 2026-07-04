#!/usr/bin/env python3
"""CQG WebAPI bridge for OVERSEER.

Streams real-time market data (L2 / detailed DOM) from a CQG WebAPI demo or
production endpoint and forwards normalized ticks to OVERSEER's ZMQ subscriber
topic (default OVERSEER_L3_*).

Required environment variables (loaded from overseer/.env):
    CQG_USERNAME
    CQG_PASSWORD

Optional environment variables:
    CQG_ENABLED             default: false
    CQG_HOST                default: wss://demoapi.cqg.com:443
    CQG_CLIENT_APP_ID       default: WebAPITest
    CQG_CLIENT_VERSION      default: python-client-test-2-230
    CQG_PROTOCOL_VERSION_MAJOR  default: 2
    CQG_PROTOCOL_VERSION_MINOR  default: 230
    CQG_SYMBOLS             default: 6E,6B,6J,ES,NQ,CL,GC
    CQG_REALTIME_LEVEL      default: 7 (LEVEL_TRADES_BBA_DETAILED_DOM)
    CQG_RECONNECT_MIN       default: 1.0
    CQG_RECONNECT_MAX       default: 60.0
    CQG_ZMQ_PUBLISH_HOST    default: *
    CQG_ZMQ_PUBLISH_PORT    default: 5555

Run:
    cd overseer
    .venv/Scripts/python tools/cqg_mbo_bridge.py

Or let OVERSEER start it automatically when CQG_ENABLED=true.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import signal
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# Make the bundled CQG WebAPI protobuf bindings importable as top-level packages.
ROOT = Path(__file__).resolve().parents[1]
CQG_WEBAPI_ROOT = ROOT / "core" / "cqg_webapi"
if str(CQG_WEBAPI_ROOT) not in sys.path:
    sys.path.insert(0, str(CQG_WEBAPI_ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

# Import after sys.path manipulation
from WebAPI.webapi_2_pb2 import ClientMsg, ServerMsg  # noqa: E402
from WebAPI.user_session_2_pb2 import LogonResult  # noqa: E402
from WebAPI import webapi_client  # noqa: E402
from WebAPI import market_data_2_pb2 as md  # noqa: E402

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "cqg_mbo_bridge.log", encoding="utf-8"),
    ],
)
LOGGER = logging.getLogger("cqg_mbo_bridge")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CQG_ENABLED = os.getenv("CQG_ENABLED", "false").lower() == "true"
CQG_HOST = os.getenv("CQG_HOST", "wss://demoapi.cqg.com:443")
CQG_USERNAME = os.getenv("CQG_USERNAME", "")
CQG_PASSWORD = os.getenv("CQG_PASSWORD", "")
CQG_CLIENT_APP_ID = os.getenv("CQG_CLIENT_APP_ID", "WebAPITest")
CQG_CLIENT_VERSION = os.getenv("CQG_CLIENT_VERSION", "python-client-test-2-230")
CQG_PROTOCOL_VERSION_MAJOR = int(os.getenv("CQG_PROTOCOL_VERSION_MAJOR", "2"))
CQG_PROTOCOL_VERSION_MINOR = int(os.getenv("CQG_PROTOCOL_VERSION_MINOR", "230"))
CQG_SYMBOLS = [s.strip() for s in os.getenv("CQG_SYMBOLS", "6E,6B,6J,ES,NQ,CL,GC").split(",") if s.strip()]
CQG_REALTIME_LEVEL = int(os.getenv("CQG_REALTIME_LEVEL", "7"))
RECONNECT_MIN = float(os.getenv("CQG_RECONNECT_MIN", "1.0"))
RECONNECT_MAX = float(os.getenv("CQG_RECONNECT_MAX", "60.0"))

ZMQ_PUBLISH_HOST = os.getenv("CQG_ZMQ_PUBLISH_HOST", "*")
ZMQ_PUBLISH_PORT = int(os.getenv("CQG_ZMQ_PUBLISH_PORT", "5555"))

SHUTDOWN_EVENT = threading.Event()


def redact(text: str) -> str:
    if not text:
        return ""
    return f"{text[:2]}***{text[-2:]}" if len(text) > 4 else "***"


def require_env(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise ValueError(f"Missing required environment variable: {name}")
    return val


def scaled_to_float(scaled: int, scale: float) -> float:
    """Convert CQG scaled integer price to float using contract price scale."""
    if scaled == 0 or scale == 0:
        return 0.0
    return round(float(scaled) * float(scale), 12)


def scale_from_metadata(metadata: Any) -> float:
    """Return the price scale factor for a contract."""
    scale = getattr(metadata, "correct_price_scale", 0.0)
    if scale and scale > 0:
        return float(scale)
    tick_size = getattr(metadata, "tick_size", 0.0)
    if tick_size and tick_size > 0:
        # Infer scale from tick size: e.g. 0.25 -> 0.01, 0.0001 -> 0.0001
        return float(tick_size)
    return 0.01


class CQGBridge:
    """Synchronous CQG WebAPI client that publishes normalized ticks via ZMQ."""

    def __init__(self) -> None:
        self.username = require_env("CQG_USERNAME")
        self.password = require_env("CQG_PASSWORD")
        self.host = CQG_HOST
        self.symbols = CQG_SYMBOLS
        self.level = CQG_REALTIME_LEVEL
        self.contract_metadata: dict[int, Any] = {}
        self.price_scales: dict[int, float] = {}
        self.latest_bbo: dict[str, dict[str, Any]] = defaultdict(dict)
        self.msg_id = 1

        self.zmq_ctx: Any = None
        self.zmq_pub: Any = None
        self._init_zmq()

    def _init_zmq(self) -> None:
        try:
            import zmq
        except ImportError:
            LOGGER.error("pyzmq is required. Install with: pip install pyzmq")
            raise
        self.zmq_ctx = zmq.Context()
        self.zmq_pub = self.zmq_ctx.socket(zmq.PUB)
        self.zmq_pub.bind(f"tcp://{ZMQ_PUBLISH_HOST}:{ZMQ_PUBLISH_PORT}")
        LOGGER.info("ZMQ PUB bound to tcp://%s:%s", ZMQ_PUBLISH_HOST, ZMQ_PUBLISH_PORT)

    def _next_msg_id(self) -> int:
        self.msg_id += 1
        return self.msg_id

    def _logon(self, client: webapi_client.WebApiClient) -> None:
        client_msg = ClientMsg()
        logon = client_msg.logon
        logon.user_name = self.username
        logon.password = self.password
        logon.client_app_id = CQG_CLIENT_APP_ID
        logon.client_version = CQG_CLIENT_VERSION
        logon.protocol_version_major = CQG_PROTOCOL_VERSION_MAJOR
        logon.protocol_version_minor = CQG_PROTOCOL_VERSION_MINOR
        client.send_client_message(client_msg)

        server_msg = client.receive_server_message()
        result = server_msg.logon_result
        if result.result_code != LogonResult.ResultCode.RESULT_CODE_SUCCESS:
            raise Exception(f"CQG logon failed: {result.text_message} (code={result.result_code})")
        LOGGER.info("CQG logon successful. base_time=%s", result.base_time)

    def _resolve_symbol(self, client: webapi_client.WebApiClient, symbol: str) -> Any:
        req_id = self._next_msg_id()
        client_msg = ClientMsg()
        info_req = client_msg.information_requests.add()
        info_req.id = req_id
        info_req.symbol_resolution_request.symbol = symbol
        client.send_client_message(client_msg)

        while True:
            server_msg = client.receive_server_message()
            if server_msg.information_reports:
                report = server_msg.information_reports[0]
                if report.HasField("symbol_resolution_report"):
                    meta = report.symbol_resolution_report.contract_metadata
                    self.contract_metadata[meta.contract_id] = meta
                    self.price_scales[meta.contract_id] = scale_from_metadata(meta)
                    LOGGER.info("Resolved %s -> contract_id=%s scale=%s", symbol, meta.contract_id, self.price_scales[meta.contract_id])
                    return meta
            # Drain unrelated messages (logon_result, heartbeats, etc.)
            if server_msg.logon_result.result_code:
                continue

    def _subscribe_realtime(self, client: webapi_client.WebApiClient, contract_id: int) -> None:
        req_id = self._next_msg_id()
        client_msg = ClientMsg()
        sub = client_msg.market_data_subscriptions.add()
        sub.contract_id = contract_id
        sub.request_id = req_id
        sub.level = self.level
        client.send_client_message(client_msg)
        LOGGER.info("Subscribed contract_id=%s level=%s", contract_id, self.level)

    def _publish(self, symbol: str, payload: dict[str, Any]) -> None:
        topic = f"OVERSEER_L3_{symbol}".encode("utf-8")
        data = json.dumps(payload).encode("utf-8")
        try:
            self.zmq_pub.send_multipart([topic, data])
        except Exception as exc:
            LOGGER.debug("ZMQ publish failed: %s", exc)

    def _build_tick_payload(self, contract_id: int, best_bid: float, best_bid_size: float, best_ask: float, best_ask_size: float, timestamp_ms: int) -> dict[str, Any]:
        meta = self.contract_metadata.get(contract_id)
        symbol = meta.contract_symbol if meta else str(contract_id)
        dom = {
            "bids": [{"price": best_bid, "size": best_bid_size}],
            "asks": [{"price": best_ask, "size": best_ask_size}],
            "source": "cqg",
        }
        return {
            "symbol": symbol,
            "bid": best_bid,
            "bid_size": best_bid_size,
            "ask": best_ask,
            "ask_size": best_ask_size,
            "dom": dom,
            "dom_json": json.dumps(dom),
            "delta": 0.0,
            "timestamp": timestamp_ms,
            "source": "zmq",
            "contract_id": contract_id,
        }

    def _publish_detailed_dom(self, contract_id: int, detailed_dom: md.DetailedDOM, timestamp_ms: int) -> None:
        scale = self.price_scales.get(contract_id, 0.01)
        symbol = self.contract_metadata.get(contract_id, type("M", (), {"contract_symbol": str(contract_id)})()).contract_symbol

        bids = []
        asks = []
        for level in detailed_dom.price_levels:
            price = scaled_to_float(getattr(level, "scaled_price", 0), scale)
            side = getattr(level, "side", 0)
            size = 0.0
            for order in level.orders:
                vol = getattr(order, "volume", 0) or getattr(order, "scaled_volume", 0)
                size += float(vol)
            entry = {"price": price, "size": size}
            if side == 0:  # bid side in CQG DetailedDOMOrder; confirm enum values
                bids.append(entry)
            else:
                asks.append(entry)

        bids.sort(key=lambda x: x["price"], reverse=True)
        asks.sort(key=lambda x: x["price"])

        best_bid = bids[0]["price"] if bids else 0.0
        best_ask = asks[0]["price"] if asks else 0.0
        best_bid_size = bids[0]["size"] if bids else 0.0
        best_ask_size = asks[0]["size"] if asks else 0.0

        dom = {
            "bids": bids,
            "asks": asks,
            "source": "cqg",
            "is_detailed_dom_complete": getattr(detailed_dom, "is_detailed_dom_complete", False),
            "is_snapshot": getattr(detailed_dom, "is_snapshot", False),
        }
        payload = {
            "symbol": symbol,
            "bid": best_bid,
            "bid_size": best_bid_size,
            "ask": best_ask,
            "ask_size": best_ask_size,
            "dom": dom,
            "dom_json": json.dumps(dom),
            "delta": 0.0,
            "timestamp": timestamp_ms,
            "source": "zmq",
            "contract_id": contract_id,
        }
        self._publish(symbol, payload)
        self.latest_bbo[symbol].update({"bid": best_bid, "ask": best_ask, "timestamp_ms": timestamp_ms})

    def _publish_quotes(self, contract_id: int, quotes: list[Any], timestamp_ms: int) -> None:
        scale = self.price_scales.get(contract_id, 0.01)
        meta = self.contract_metadata.get(contract_id)
        symbol = meta.contract_symbol if meta else str(contract_id)

        best_bid = 0.0
        best_ask = 0.0
        best_bid_size = 0.0
        best_ask_size = 0.0
        last_trade_price = 0.0
        last_trade_size = 0.0

        for quote in quotes:
            qtype = quote.type
            price = scaled_to_float(getattr(quote, "scaled_price", 0), scale)
            volume = float(getattr(quote, "volume", 0) or 0)
            if qtype == md.Quote.Type.TYPE_BESTBID:
                best_bid = price
            elif qtype == md.Quote.Type.TYPE_BESTASK:
                best_ask = price
            elif qtype == md.Quote.Type.TYPE_BID:
                if price >= best_bid:
                    best_bid = price
                    best_bid_size = volume
            elif qtype == md.Quote.Type.TYPE_ASK:
                if best_ask == 0 or price <= best_ask:
                    best_ask = price
                    best_ask_size = volume
            elif qtype == md.Quote.Type.TYPE_TRADE:
                last_trade_price = price
                last_trade_size = volume

        if best_bid <= 0 and best_ask <= 0 and last_trade_price <= 0:
            return

        # Use last trade if no BBO
        if best_bid <= 0 and last_trade_price > 0:
            best_bid = last_trade_price
        if best_ask <= 0 and last_trade_price > 0:
            best_ask = last_trade_price
        if best_bid > 0 and best_ask > 0 and best_bid > best_ask:
            best_bid, best_ask = best_ask, best_bid

        payload = self._build_tick_payload(contract_id, best_bid, best_bid_size, best_ask, best_ask_size, timestamp_ms)
        if last_trade_price > 0:
            payload["last_trade_price"] = last_trade_price
            payload["last_trade_size"] = last_trade_size
        self._publish(symbol, payload)
        self.latest_bbo[symbol].update({"bid": best_bid, "ask": best_ask, "timestamp_ms": timestamp_ms})

    def _handle_server_message(self, server_msg: ServerMsg) -> None:
        if server_msg.real_time_market_data:
            rt = server_msg.real_time_market_data
            contract_id = rt.contract_id
            timestamp_ms = int(time.time() * 1000)
            if rt.quotes:
                self._publish_quotes(contract_id, rt.quotes, timestamp_ms)
            if rt.detailed_dom:
                self._publish_detailed_dom(contract_id, rt.detailed_dom, timestamp_ms)

    def _run_once(self) -> None:
        client = webapi_client.WebApiClient(need_to_log=False)
        try:
            LOGGER.info("Connecting to CQG %s user=%s", self.host, redact(self.username))
            client.connect(self.host)
            self._logon(client)

            for symbol in self.symbols:
                self._resolve_symbol(client, symbol)

            for contract_id in self.contract_metadata:
                self._subscribe_realtime(client, contract_id)

            LOGGER.info("CQG bridge streaming. symbols=%s level=%s", self.symbols, self.level)
            while not SHUTDOWN_EVENT.is_set():
                server_msg = client.receive_server_message()
                self._handle_server_message(server_msg)
        finally:
            try:
                client.disconnect()
            except Exception:
                pass

    def run(self) -> None:
        reconnect_delay = RECONNECT_MIN
        while not SHUTDOWN_EVENT.is_set():
            try:
                self._run_once()
                reconnect_delay = RECONNECT_MIN
            except Exception as exc:
                LOGGER.error("CQG bridge error: %s. Reconnecting in %.1fs...", exc, reconnect_delay)
                SHUTDOWN_EVENT.wait(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX)

    def close(self) -> None:
        SHUTDOWN_EVENT.set()
        if self.zmq_pub:
            self.zmq_pub.close(linger=0)
        if self.zmq_ctx:
            self.zmq_ctx.term()


def _signal_handler(signum: int, frame: Any) -> None:
    LOGGER.info("Received signal %s, shutting down CQG bridge...", signum)
    SHUTDOWN_EVENT.set()


def main() -> None:
    if not CQG_ENABLED:
        LOGGER.warning("CQG bridge is disabled. Set CQG_ENABLED=true in .env to start.")
        return

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, _signal_handler)

    bridge = CQGBridge()
    try:
        bridge.run()
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
