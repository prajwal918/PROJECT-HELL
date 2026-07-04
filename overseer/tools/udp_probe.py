from __future__ import annotations

import argparse
import socket
import time


def main() -> None:
    parser = argparse.ArgumentParser(description="Listen for OVERSEER UDP bridge packets.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=65000)
    parser.add_argument("--seconds", type=float, default=15.0)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
    sock.bind((args.host, args.port))

    deadline = time.time() + args.seconds
    count = 0
    print(f"Listening for UDP packets on {args.host}:{args.port} for {args.seconds:.1f}s...")
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(65535)
        except TimeoutError:
            continue
        except socket.timeout:
            continue
        count += 1
        text = data.decode("utf-8", errors="replace")
        print(f"[{count}] {addr[0]}:{addr[1]} {text[:500]}")

    sock.close()
    print(f"Packets received: {count}")


if __name__ == "__main__":
    main()
