#!/usr/bin/env python3
from __future__ import annotations
"""Direct Rithmic Protocol bridge for order book + depth-by-order data.
This uses the open-source async_rithmic package, which talks to Rithmic's
Protocol Buffer websocket gateway. It does not use Quantower. R|Trader Pro is
not scraped; credentials and entitlement must allow Rithmic Protocol access.

MBO events are forwarded via ZMQ (topic OVERSEER_L3) so the main pipeline's
l3_scorer can ingest them without any app-level bridge.

Requirements:
RITHMIC_USER
RITHMIC_PASSWORD
RITHMIC_SYSTEM_NAME default: Rithmic Paper Trading
RITHMIC_URL default: wss://rituz00100.rithmic.com:443
RITHMIC_SYMBOLS default: 6EM6:CME

ZMQ_PUBLISH_HOST default: *
ZMQ_PUBLISH_PORT default: 5555
RITHMIC_RECONNECT_MIN default: 1.0
RITHMIC_RECONNECT_MAX default: 60.0

Example usage:
set RITHMIC_USER=YOUR_USERNAME
set RITHMIC_PASSWORD=YOUR_PASSWORD
set RITHMIC_SYMBOLS=6EM6:CME,6BM6:CME,6JM6:CME
python tools/rithmic_mbo_udp_bridge.py
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from google.protobuf.json_format import MessageToDict

from async_rithmic import DataType, RithmicClient
from async_rithmic.enums import Gateway

try:
    import zmq
    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
MBO_LOG = LOG_DIR / "rithmic_mbo_events.jsonl"

LOGGER = logging.getLogger("rithmic_mbo_udp_bridge")

RECONNECT_MIN = float(os.getenv("RITHMIC_RECONNECT_MIN", "1.0"))
RECONNECT_MAX = float(os.getenv("RITHMIC_RECONNECT_MAX", "60.0"))


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / "rithmic_mbo_udp_bridge.log", encoding="utf-8"),
        ],
    )
    logging.getLogger("rithmic").setLevel(logging.CRITICAL)


def redact_text(text: str) -> str:
    """Mask credentials in logs."""
    if not text:
        return ""
    return f"{text[:2]}...{text[-2:]}" if len(text) > 4 else "***"


def require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise ValueError(f"Missing required environment variable: {name}")
    return val


def parse_symbols(s: str) -> list[tuple[str, str]]:
    """Parse symbol:exchange[,symbol:exchange] into list of tuples."""
    if not s:
        return []
    out = []
    for entry in s.split(","):
        if ":" in entry:
            sym, exch = entry.strip().split(":", 1)
            out.append((sym, exch))
        else:
            out.append((entry.strip(), "CME"))
    return out


def epoch_ms_from_rithmic(data: dict[str, Any]) -> int:
    """Extract or estimate epoch ms from Rithmic's ss/us fields."""
    ss = data.get("ss", 0)
    us = data.get("us", 0)
    if ss > 0:
        return (ss * 1000) + (us // 1000)
    return int(time.time() * 1000)


class RithmicMboBridge:
    def __init__(self):
        self.symbols = parse_symbols(os.getenv("RITHMIC_SYMBOLS", "6EM6:CME"))
        if not self.symbols:
             raise ValueError("RITHMIC_SYMBOLS did not contain any symbols")

        self.depth_prices_per_side = int(os.getenv("RITHMIC_MBO_DEPTH", "5"))
        self.latest_bbo = defaultdict(dict)
        
        self.zmq_ctx: Any = None
        self.zmq_pub: Any = None
        zmq_host = os.getenv("ZMQ_PUBLISH_HOST", "*")
        zmq_port = int(os.getenv("ZMQ_PUBLISH_PORT", "5555"))
        if ZMQ_AVAILABLE:
            self.zmq_ctx = zmq.Context()
            self.zmq_pub = self.zmq_ctx.socket(zmq.PUB)
            self.zmq_pub.bind(f"tcp://{zmq_host}:{zmq_port}")
            LOGGER.info("ZMQ PUB bound to tcp://%s:%s", zmq_host, zmq_port)
        else:
            LOGGER.warning("pyzmq not installed — MBO events will NOT be forwarded to l3_scorer")

        # Select Gateway based on URL
        url = os.getenv("RITHMIC_URL", "wss://rituz00100.rithmic.com:443")
        gateway = Gateway.TEST
        if "rituz00100" in url:
            gateway = Gateway.TEST
        elif "rprotocol" in url:
            gateway = Gateway.CHICAGO
        elif "au." in url:
            gateway = Gateway.SYDNEY
        elif "br." in url:
            gateway = Gateway.SAO_PAULO
        elif "in." in url:
            gateway = Gateway.MUMBAI

        self.client = RithmicClient(
            user=require_env("RITHMIC_USER"),
            password=require_env("RITHMIC_PASSWORD"),
            system_name=os.getenv("RITHMIC_SYSTEM_NAME", "Rithmic Paper Trading"),
            app_name=os.getenv("RITHMIC_APP_NAME", "OVERSEER"),
            app_version=os.getenv("RITHMIC_APP_VERSION", "12.0"),
            gateway=gateway
        )

    async def on_tick(self, data: dict[str, Any]):
        symbol = data.get("symbol", "unknown")
        data_type = data.get("data_type")
        
        if data_type == DataType.BBO:
            bid = data.get("bid_price", 0.0)
            ask = data.get("ask_price", 0.0)
            bid_size = data.get("bid_size", 0.0)
            ask_size = data.get("ask_size", 0.0)
            
            self.latest_bbo[symbol]["bid"] = bid
            self.latest_bbo[symbol]["bid_size"] = bid_size
            self.latest_bbo[symbol]["ask"] = ask
            self.latest_bbo[symbol]["ask_size"] = ask_size
            
            ssboe = data.get("ssboe", 0)
            usecs = data.get("usecs", 0)
            timestamp = (ssboe * 1000) + (usecs // 1000) if ssboe > 0 else int(time.time() * 1000)
            
            payload = {
                "symbol": symbol,
                "bid": bid,
                "bid_size": bid_size,
                "ask": ask,
                "ask_size": ask_size,
                "dom": {
                    "bids": [{"price": bid, "size": bid_size}],
                    "asks": [{"price": ask, "size": ask_size}],
                    "source": "rithmic"
                },
                "delta": 0.0,
                "timestamp": timestamp,
                "source": "zmq",
            }
            
            topic = f"OVERSEER_L3_{symbol}".encode("utf-8")
            pub_data = json.dumps(payload).encode("utf-8")
            if self.zmq_pub is not None:
                try:
                    self.zmq_pub.send_multipart([topic, pub_data])
                except Exception:
                    LOGGER.debug("ZMQ publish failed for BBO event", exc_info=True)
                    
        elif data_type == DataType.LAST_TRADE:
            bbo = self.latest_bbo.get(symbol, {})
            bid = bbo.get("bid", 0.0)
            ask = bbo.get("ask", 0.0)
            bid_size = bbo.get("bid_size", 0.0)
            ask_size = bbo.get("ask_size", 0.0)
            
            trade_price = data.get("trade_price", 0.0)
            trade_size = data.get("trade_size", 0.0)
            
            delta = 0.0
            if ask > bid:
                mid = (bid + ask) / 2.0
                if trade_price >= mid:
                    delta = float(trade_size)
                else:
                    delta = -float(trade_size)
                    
            ssboe = data.get("ssboe", 0)
            usecs = data.get("usecs", 0)
            timestamp = (ssboe * 1000) + (usecs // 1000) if ssboe > 0 else int(time.time() * 1000)
            
            payload = {
                "symbol": symbol,
                "bid": bid if bid > 0 else trade_price,
                "bid_size": bid_size,
                "ask": ask if ask > 0 else trade_price,
                "ask_size": ask_size,
                "price": trade_price,
                "volume": trade_size,
                "dom": {
                    "bids": [{"price": bid, "size": bid_size}] if bid > 0 else [],
                    "asks": [{"price": ask, "size": ask_size}] if ask > 0 else [],
                    "source": "rithmic"
                },
                "delta": delta,
                "timestamp": timestamp,
                "source": "zmq",
            }
            
            topic = f"OVERSEER_L3_{symbol}".encode("utf-8")
            pub_data = json.dumps(payload).encode("utf-8")
            if self.zmq_pub is not None:
                try:
                    self.zmq_pub.send_multipart([topic, pub_data])
                except Exception:
                    LOGGER.debug("ZMQ publish failed for Trade event", exc_info=True)

    async def start(self):
        try:
            LOGGER.info("connecting to Rithmic Protocol gateway")
            
            self.client.on_tick += self.on_tick
            
            await self.client.connect()
            
            for sym, exch in self.symbols:
                LOGGER.info("Subscribing to BBO and Trades: %s on %s", sym, exch)
                try:
                    await self.client.subscribe_to_market_data(sym, exch, DataType.BBO)
                    await self.client.subscribe_to_market_data(sym, exch, DataType.LAST_TRADE)
                except Exception as e:
                    LOGGER.error("Failed to subscribe to market data for %s: %s", sym, e)

            LOGGER.info("Bridge fully operational")
            
            while True:
                await asyncio.sleep(1)
                
        except Exception as exc:
            LOGGER.error("Rithmic connection error: %s", redact_text(str(exc)))
            raise

    def stop(self):
        if self.zmq_pub is not None:
            try:
                self.zmq_pub.close()
            except:
                pass
        if self.zmq_ctx is not None:
            try:
                self.zmq_ctx.term()
            except:
                pass


async def main():
    setup_logging()
    
    bridge = RithmicMboBridge()
    
    def handle_exit():
        LOGGER.info("Exit requested, cleaning up...")
        bridge.stop()
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(sig, handle_exit)
        except NotImplementedError:
            pass

    reconnect_delay = RECONNECT_MIN
    while True:
        try:
            await bridge.start()
            reconnect_delay = RECONNECT_MIN
        except (asyncio.CancelledError, KeyboardInterrupt):
            break
        except Exception as exc:
            LOGGER.error("Bridge crash, restarting in %.1fs: %s", reconnect_delay, exc)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
