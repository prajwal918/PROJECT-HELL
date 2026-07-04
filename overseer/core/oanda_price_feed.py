"""OANDA Price Feed for OVERSEER v14.

Polls OANDA REST API for live bid/ask prices when no UDP tick data
is available (e.g. MotiveWave bridge not sending tick data).

Generates standard tick dicts compatible with the gate pipeline.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional

from execution.oanda_executor import connect, get_pricing, map_symbol, is_connected

LOGGER = logging.getLogger("overseer.oanda_feed")

_ENABLED = os.getenv("OANDA_FEED_ENABLED", "true").lower() == "true"
_POLL_INTERVAL = float(os.getenv("OANDA_FEED_POLL_INTERVAL", "1.0"))

_OANDA_INSTRUMENTS = [
    "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD",
    "USD_CAD", "NZD_USD", "USD_CHF", "XAU_USD",
]

_CME_TO_OANDA = {
    "6EM6": "EUR_USD",
    "6BM6": "GBP_USD",
    "6JM6": "USD_JPY",
    "6AM6": "AUD_USD",
    "6CM6": "USD_CAD",
    "6NM6": "NZD_USD",
    "6SM6": "USD_CHF",
    "GCM6": "XAU_USD",
}

_OANDA_TO_CME = {v: k for k, v in _CME_TO_OANDA.items()}

_PIP_SIZES = {
    "EUR_USD": 0.0001, "GBP_USD": 0.0001, "USD_JPY": 0.01,
    "AUD_USD": 0.0001, "USD_CAD": 0.0001, "NZD_USD": 0.0001,
    "USD_CHF": 0.0001, "XAU_USD": 0.1,
}

_last_poll: float = 0.0
_connected: bool = False


def poll_oanda_prices() -> List[Dict]:
    """Poll OANDA for current prices and return list of tick dicts."""
    global _connected

    if not _ENABLED:
        return []

    if not _connected:
        _connected = connect()
        if not _connected:
            LOGGER.debug("OANDA feed: not connected")
            return []

    ticks = []
    for instrument in _OANDA_INSTRUMENTS:
        try:
            pricing = get_pricing(instrument)
            if not pricing or "bid" not in pricing or "ask" not in pricing:
                continue

            bid = float(pricing["bid"])
            ask = float(pricing["ask"])
            if bid <= 0 or ask <= 0 or bid > ask:
                continue

            cme_symbol = _OANDA_TO_CME.get(instrument, instrument.replace("_", ""))

            mid = (bid + ask) / 2.0
            spread = ask - bid
            pip_size = _PIP_SIZES.get(instrument, 0.0001)
            spread_bps = (spread / pip_size) * 10 if pip_size > 0 else 0

            direction = "BUY"
            if pricing.get("tradeable") is False:
                continue

            tick = {
                "symbol": cme_symbol,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "spread": spread,
                "spread_bps": spread_bps,
                "delta": 0,
                "volume": 0,
                "direction": direction,
                "timestamp": str(int(time.time() * 1000)),
                "source": "oanda_rest",
                "session": "london",
                "risk_regime": "risk_on",
                "bid_size": 0,
                "ask_size": 0,
                "dom_json": "[]",
            }
            ticks.append(tick)

        except Exception as exc:
            LOGGER.debug("OANDA pricing error for %s: %s", instrument, exc)

    if ticks:
        LOGGER.info("OANDA feed: %d prices fetched", len(ticks))
    return ticks


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ticks = poll_oanda_prices()
    for t in ticks:
        print(f"  {t['symbol']}: bid={t['bid']:.5f} ask={t['ask']:.5f} spread={t['spread_bps']:.1f}bps")
