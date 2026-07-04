from __future__ import annotations

import argparse
import asyncio
import json
import socket
import time
from collections import defaultdict

import websockets


def build_payload(symbol: str, bid: float, bid_size: float, ask: float, ask_size: float, cumulative_delta: float) -> str:
    dom_json = json.dumps(
        {
            "bids": [{"price": bid, "size": bid_size}],
            "asks": [{"price": ask, "size": ask_size}],
            "source": "binance_bookticker",
        },
        separators=(",", ":"),
    )
    timestamp_ms = int(time.time() * 1000)
    return "|".join(
        [
            symbol.upper(),
            f"{bid:.10f}",
            f"{bid_size:.10f}",
            f"{ask:.10f}",
            f"{ask_size:.10f}",
            dom_json,
            f"{cumulative_delta:.10f}",
            str(timestamp_ms),
        ]
    )


async def run(symbols: list[str], udp_host: str, udp_port: int) -> None:
    streams = "/".join(f"{symbol.lower()}@bookTicker" for symbol in symbols)
    url = f"wss://stream.binance.com:9443/stream?streams={streams}"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    counts = defaultdict(int)
    cumulative_delta: dict[str, float] = defaultdict(float)
    prev_sizes: dict[str, dict[str, float]] = {}

    while True:
        try:
            print(f"Connecting Binance WebSocket: {url}")
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                print(f"Connected. Forwarding to udp://{udp_host}:{udp_port}")
                async for raw in ws:
                    message = json.loads(raw)
                    data = message.get("data", message)
                    symbol = str(data["s"])
                    bid = float(data["b"])
                    bid_size = float(data["B"])
                    ask = float(data["a"])
                    ask_size = float(data["A"])
                    prev = prev_sizes.get(symbol, {})
                    delta_increment = (ask_size - prev.get("ask", 0)) - (bid_size - prev.get("bid", 0))
                    cumulative_delta[symbol] += delta_increment
                    prev_sizes[symbol] = {"bid": bid_size, "ask": ask_size}
                    payload = build_payload(symbol, bid, bid_size, ask, ask_size, cumulative_delta[symbol])
                    sock.sendto(payload.encode("utf-8"), (udp_host, udp_port))
                    counts[symbol] += 1
                    total = sum(counts.values())
                    if total % 100 == 0:
                        summary = ", ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
                        print(f"sent={total} {summary}")
        except Exception as exc:
            print(f"Binance bridge error: {exc}. Reconnecting in 3s...")
            await asyncio.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Forward public Binance bookTicker data to OVERSEER UDP.")
    parser.add_argument(
        "--symbols",
        default="btcusdt,ethusdt,bnbusdt,xrpusdt,solusdt",
        help="Comma-separated Binance spot symbols.",
    )
    parser.add_argument("--udp-host", default="127.0.0.1")
    parser.add_argument("--udp-port", type=int, default=65000)
    args = parser.parse_args()
    symbols = [item.strip().lower() for item in args.symbols.split(",") if item.strip()]
    asyncio.run(run(symbols, args.udp_host, args.udp_port))


if __name__ == "__main__":
    main()
