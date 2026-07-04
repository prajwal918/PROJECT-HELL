#!/usr/bin/env python3
"""
Standalone entry point for the Overseer UDP Hub Listener.
Receives bridge UDP data (TICK, DOM_SNAPSHOT, MBO_EVENT) from MotiveWave
on port 65001 and feeds it into the Overseer pipeline queues.

Note: This script receives and logs bridge data but doesn't run the full
Overseer pipeline (gates, ML, execution). For full pipeline integration,
run main.py instead.
"""
import asyncio
import os
import sys
import signal
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.hub_listener import start_udp_listener

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "hub_listener.log")


def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


async def drain_queue(q, name, stats, lock):
    """Drain a queue and track stats."""
    while True:
        try:
            item = await asyncio.wait_for(q.get(), timeout=1.0)
            async with lock:
                if isinstance(item, dict):
                    item_type = item.get("type", "unknown")
                    if "TICK" in item_type or "tick" in item_type:
                        stats["tick"] += 1
                    elif "DOM" in item_type or "dom" in item_type:
                        stats["dom"] += 1
                    elif "MBO" in item_type or "mbo" in item_type:
                        stats["mbo"] += 1
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break
        except Exception as e:
            log(f"Error draining {name}: {e}")


async def stats_reporter(stats, lock):
    """Periodically log stats."""
    while True:
        await asyncio.sleep(15)
        async with lock:
            t = stats["tick"]
            d = stats["dom"]
            m = stats["mbo"]
            log(f"STATS: TICK={t} DOM={d} MBO={m}")
            stats["tick"] = 0
            stats["dom"] = 0
            stats["mbo"] = 0


async def main():
    port = int(os.getenv("OVERSEER_UDP_PORT", "65001"))
    host = os.getenv("OVERSEER_UDP_HOST", "127.0.0.1")

    log(f"=== Starting Overseer Hub Listener ===")
    log(f"Listening on {host}:{port}")

    queue: asyncio.Queue = asyncio.Queue(maxsize=50000)
    l3_queue: asyncio.Queue = asyncio.Queue(maxsize=100000)
    event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

    transport, protocol, watchdog_task = await start_udp_listener(
        queue, host=host, port=port, event_queue=event_queue, l3_queue=l3_queue
    )

    log(f"UDP listener started on port {port}")

    stats = {"tick": 0, "dom": 0, "mbo": 0}
    lock = asyncio.Lock()

    tasks = [
        asyncio.create_task(drain_queue(queue, "queue", stats, lock)),
        asyncio.create_task(drain_queue(l3_queue, "l3_queue", stats, lock)),
        asyncio.create_task(stats_reporter(stats, lock)),
        watchdog_task,
    ]

    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        log("Shutting down...")
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        transport.close()
        log("Hub Listener stopped")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    main_task = asyncio.ensure_future(main(), loop=loop)

    # Handle signals by cancelling the main task
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: loop.call_soon_threadsafe(main_task.cancel))

    try:
        loop.run_until_complete(main_task)
    except (SystemExit, KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        loop.close()
