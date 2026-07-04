from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

LOGGER = logging.getLogger("overseer.zmq_bridge")

ZMQ_HOST = os.getenv("ZMQ_BRIDGE_HOST", "127.0.0.1")
ZMQ_PORT = int(os.getenv("ZMQ_BRIDGE_PORT", "5555"))
ZMQ_TOPIC = os.getenv("ZMQ_BRIDGE_TOPIC", "OVERSEER_L3")
ZMQ_HEARTBEAT_INTERVAL = float(os.getenv("ZMQ_HEARTBEAT_INTERVAL", "5.0"))


class ZmqBridgeStats:
    def __init__(self) -> None:
        self.messages_received: int = 0
        self.mbo_events_received: int = 0
        self.dom_snapshots_received: int = 0
        self.parse_errors: int = 0
        self.disconnect_count: int = 0
        self.last_message_time: float = 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "messages_received": self.messages_received,
            "mbo_events_received": self.mbo_events_received,
            "dom_snapshots_received": self.dom_snapshots_received,
            "parse_errors": self.parse_errors,
            "disconnect_count": self.disconnect_count,
            "last_message_age_s": time.monotonic() - self.last_message_time if self.last_message_time > 0 else -1,
        }


async def start_zmq_subscriber(
    queue: asyncio.Queue,
    event_queue: asyncio.Queue | None = None,
    host: str = ZMQ_HOST,
    port: int = ZMQ_PORT,
    topic: str = ZMQ_TOPIC,
) -> Any:
    try:
        import zmq
        import zmq.asyncio
    except ImportError:
        LOGGER.warning("pyzmq not installed. ZMQ bridge disabled. Install with: pip install pyzmq")
        return None

    ctx = zmq.asyncio.Context()
    sock = ctx.socket(zmq.SUB)
    sock.connect(f"tcp://{host}:{port}")
    sock.setsockopt_string(zmq.SUBSCRIBE, topic)
    LOGGER.info("ZMQ subscriber connected to tcp://%s:%d topic=%s", host, port, topic)

    stats = ZmqBridgeStats()

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(ZMQ_HEARTBEAT_INTERVAL)
            if event_queue is not None:
                s = stats.summary()
                await event_queue.put({
                    "event_type": "ZMQ_HEARTBEAT",
                    "timestamp_ms": int(time.time() * 1000),
                    "stats": s,
                })

    async def _recv_loop() -> None:
        nonlocal sock
        last_msg_time = time.monotonic()
        disconnected = False
        while True:
            try:
                # Use a shorter timeout to allow checking for stale connection
                parts = await asyncio.wait_for(sock.recv_multipart(), timeout=5.0)
                
                last_msg_time = time.monotonic()
                if disconnected:
                    disconnected = False
                    LOGGER.info("ZMQ connection restored")
                    if event_queue is not None:
                        await event_queue.put({"event_type": "ZMQ_CONNECTED", "timestamp_ms": int(time.time() * 1000), "message": "ZMQ flow restored"})

                if len(parts) < 2:
                    continue
                
                raw_payload = parts[1].decode("utf-8", errors="replace")
                try:
                    payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    LOGGER.warning("ZMQ payload not valid JSON: %s", raw_payload[:200])
                    stats.parse_errors += 1
                    continue

                stats.messages_received += 1
                stats.last_message_time = time.monotonic()
                
                if "symbol" in payload and "bid" in payload and "ask" in payload:
                    payload["source"] = "zmq"
                    stats.dom_snapshots_received += 1
                    await queue.put(payload)
                elif "action" in payload or "order_id" in payload:
                    payload["source"] = "zmq_mbo"
                    stats.mbo_events_received += 1
                    await queue.put(payload)
                elif payload.get("type") == "heartbeat":
                    pass
                else:
                    LOGGER.debug("ZMQ message unrecognized format: %s", list(payload.keys()))

            except asyncio.TimeoutError:
                elapsed = time.monotonic() - last_msg_time
                if elapsed > 30.0:
                    LOGGER.warning("ZMQ Watchdog: No data for %.0fs. Recreating socket...", elapsed)
                    try:
                        sock.close(linger=0)
                        sock = ctx.socket(zmq.SUB)
                        sock.connect(f"tcp://{host}:{port}")
                        sock.setsockopt_string(zmq.SUBSCRIBE, topic)
                        stats.disconnect_count += 1
                        last_msg_time = time.monotonic() # Reset timer to avoid immediate loop
                    except Exception as e:
                        LOGGER.error("ZMQ Reconnect failed: %s", e)
                        await asyncio.sleep(2.0)
                elif elapsed > 5.0 and not disconnected:
                    disconnected = True
                    stats.disconnect_count += 1
                    LOGGER.warning("ZMQ: no messages for 5s. Possibly disconnected.")
                    if event_queue is not None:
                        await event_queue.put({"event_type": "ZMQ_DISCONNECTED", "timestamp_ms": int(time.time() * 1000), "message": "ZMQ no messages for 5s"})
                continue
            except Exception as e:
                LOGGER.error("ZMQ loop error: %s", e)
                await asyncio.sleep(2.0)

    asyncio.create_task(_heartbeat())
    task = asyncio.create_task(_recv_loop())
    return task
