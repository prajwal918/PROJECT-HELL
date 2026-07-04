"""
FXCM ForexConnect Bridge - sends FXCM spot tick data to UDP:65000
Runs under Python 3.7 (forexconnect SDK only supports 3.5-3.7).

Two modes:
  1. Callback mode: TableListener fires on price changes (requires status=T)
  2. Poll mode: Periodically reads offers table (works even with status=D, but slower)

Usage:
    C:\\Users\\jogip\\AppData\\Local\\Programs\\Python\\Python37\\python.exe tools\\fxcm_bridge.py
"""

import json
import os
import socket
import sys
import time
import logging
import signal as sig
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s fxcm_bridge %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/fxcm_bridge.log", mode="a"),
    ],
)
LOGGER = logging.getLogger(__name__)

UDP_HOST = os.getenv("FXCM_UDP_HOST", "127.0.0.1")
UDP_PORT = int(os.getenv("FXCM_UDP_PORT", "65000"))
VERSION = "2026-06-02.3"

FXCM_SYMBOLS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
    "USD/CAD", "NZD/USD", "USD/CHF", "XAU/USD", "XAG/USD",
]

SYMBOL_MAP = {
    "EUR/USD": "EURUSD", "GBP/USD": "GBPUSD", "USD/JPY": "USDJPY",
    "AUD/USD": "AUDUSD", "USD/CAD": "USDCAD", "NZD/USD": "NZDUSD",
    "USD/CHF": "USDCHF", "XAU/USD": "XAUUSD", "XAG/USD": "XAGUSD",
}

POLL_INTERVAL = 0.25

_running = True
_tick_count = 0


def _signal_handler(signum, frame):
    global _running
    _running = False
    LOGGER.info("Shutdown signal received")


sig.signal(sig.SIGINT, _signal_handler)
sig.signal(sig.SIGTERM, _signal_handler)


def _send_udp(sock, data):
    payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
    try:
        sock.sendto(payload, (UDP_HOST, UDP_PORT))
    except Exception as e:
        LOGGER.error("UDP send failed: %s", e)


def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _send_offer(udp_sock, instrument, bid, ask, bid_size, ask_size, high, low):
    global _tick_count
    mapped = SYMBOL_MAP.get(instrument, instrument.replace("/", ""))
    spread = ask - bid

    tick = {
        "type": "TICK",
        "source": "FXCM",
        "version": VERSION,
        "symbol": mapped,
        "bid": bid,
        "ask": ask,
        "bid_size": bid_size,
        "ask_size": ask_size,
        "spread": spread,
        "high": high,
        "low": low,
        "timestamp": int(time.time() * 1000),
    }

    dom_levels = [
        {"price": bid, "size": bid_size, "side": "bid", "level": 0},
        {"price": ask, "size": ask_size, "side": "ask", "level": 0},
    ]
    dom_msg = {
        "type": "DOM_SNAPSHOT",
        "source": "FXCM",
        "version": VERSION,
        "symbol": mapped,
        "dom": dom_levels,
        "timestamp": int(time.time() * 1000),
    }
    _send_udp(udp_sock, dom_msg)
    _send_udp(udp_sock, tick)
    _tick_count += 1


def main():
    _load_env()

    user_id = os.getenv("FXCM_USER", "")
    password = os.getenv("FXCM_PASSWORD", "")
    connection = os.getenv("FXCM_CONNECTION", "Real")
    url = os.getenv("FXCM_URL", "www.fxcorporate.com/Hosts.jsp")

    if not user_id or not password:
        LOGGER.error("FXCM_USER and FXCM_PASSWORD must be set in .env")
        sys.exit(1)

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    from forexconnect import ForexConnect, TableListener

    LOGGER.info("FXCM Bridge v%s starting", VERSION)
    LOGGER.info("UDP target: %s:%d", UDP_HOST, UDP_PORT)
    LOGGER.info("Connecting to FXCM: user=%s conn=%s", user_id, connection)

    fc = ForexConnect()
    last_heartbeat = time.time()
    last_prices = {}
    callback_fired = threading.Event()

    def on_changed(listener, row_id, row_data):
        instrument = getattr(row_data, "Instrument", "")
        if instrument not in FXCM_SYMBOLS:
            return
        bid = float(getattr(row_data, "Bid", 0) or 0)
        ask = float(getattr(row_data, "Ask", 0) or 0)
        if bid <= 0 or ask <= 0:
            return
        callback_fired.set()
        key = instrument
        prev = last_prices.get(key)
        if prev and prev[0] == bid and prev[1] == ask:
            return
        last_prices[key] = (bid, ask)
        bid_size = float(getattr(row_data, "BidSize", 0) or 0)
        ask_size = float(getattr(row_data, "AskSize", 0) or 0)
        high = float(getattr(row_data, "High", 0) or 0)
        low = float(getattr(row_data, "Low", 0) or 0)
        _send_offer(udp_sock, instrument, bid, ask, bid_size, ask_size, high, low)
        if _tick_count % 100 == 0:
            LOGGER.info("FXCM %s bid=%.5f ask=%.5f ticks=%d (callback)",
                        SYMBOL_MAP.get(instrument, instrument), bid, ask, _tick_count)

    def on_added(listener, row_id, row_data):
        on_changed(listener, row_id, row_data)

    listener = TableListener(on_changed_callback=on_changed, on_added_callback=on_added)

    heartbeat_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    heartbeat_msg = json.dumps({
        "type": "HEARTBEAT",
        "source": "FXCM",
        "version": VERSION,
        "timestamp": int(time.time() * 1000),
    }).encode("utf-8")

    try:
        session = fc.login(
            user_id=user_id,
            password=password,
            url=url,
            connection=connection,
        )
        LOGGER.info("FXCM login successful")

        offers_table = fc.get_table(fc.OFFERS)
        LOGGER.info("Offers table loaded (%d instruments)", len(offers_table) if offers_table else 0)

        listener.subscribe(offers_table)
        LOGGER.info("Subscribed to OFFERS table.")

        # Wait briefly for callback mode to activate
        LOGGER.info("Waiting 15s for callback activation...")
        deadline = time.time() + 15
        while _running and time.time() < deadline:
            if callback_fired.is_set():
                break
            time.sleep(0.5)

        if callback_fired.is_set():
            LOGGER.info("Callback mode ACTIVE - streaming via TableListener")
        else:
            LOGGER.info("Callback mode not firing - switching to POLL mode")

        poll_mode = not callback_fired.is_set()

        LOGGER.info("Streaming... (poll_mode=%s)", poll_mode)

        while _running:
            now = time.time()

            if poll_mode:
                try:
                    offers = fc.get_table(fc.OFFERS)
                    for row in offers:
                        instrument = getattr(row, "Instrument", "")
                        if instrument not in FXCM_SYMBOLS:
                            continue
                        bid = float(getattr(row, "Bid", 0) or 0)
                        ask = float(getattr(row, "Ask", 0) or 0)
                        if bid <= 0 or ask <= 0:
                            continue
                        key = instrument
                        prev = last_prices.get(key)
                        if prev and prev[0] == bid and prev[1] == ask:
                            continue
                        last_prices[key] = (bid, ask)
                        bid_size = float(getattr(row, "BidSize", 0) or 0)
                        ask_size = float(getattr(row, "AskSize", 0) or 0)
                        high = float(getattr(row, "High", 0) or 0)
                        low = float(getattr(row, "Low", 0) or 0)
                        _send_offer(udp_sock, instrument, bid, ask, bid_size, ask_size, high, low)
                        if _tick_count % 100 == 0:
                            LOGGER.info("FXCM %s bid=%.5f ask=%.5f ticks=%d (poll)",
                                        SYMBOL_MAP.get(instrument, instrument), bid, ask, _tick_count)
                except Exception as e:
                    LOGGER.error("Poll error: %s", e)
                time.sleep(POLL_INTERVAL)
            else:
                # Callback mode - just send heartbeats
                if now - last_heartbeat >= 10:
                    try:
                        heartbeat_sock.sendto(heartbeat_msg, (UDP_HOST, UDP_PORT))
                    except Exception:
                        pass
                    last_heartbeat = now
                    LOGGER.info("Heartbeat. Total ticks: %d", _tick_count)
                time.sleep(1)

        # Heartbeat in poll mode too
        if poll_mode and now - last_heartbeat >= 30:
            try:
                heartbeat_sock.sendto(heartbeat_msg, (UDP_HOST, UDP_PORT))
            except Exception:
                pass
            last_heartbeat = now

    except Exception as e:
        LOGGER.exception("FXCM connection error: %s", e)
    finally:
        LOGGER.info("Shutting down FXCM bridge (ticks sent: %d)", _tick_count)
        try:
            listener.unsubscribe()
        except Exception:
            pass
        try:
            fc.logout()
        except Exception:
            pass
        udp_sock.close()
        heartbeat_sock.close()


if __name__ == "__main__":
    main()
