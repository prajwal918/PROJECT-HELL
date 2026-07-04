"""Fundamental Bias Calculator for OVERSEER v12.5.

Computes directional bias from macro fundamentals:
  - Interest rate differentials (Fed vs ECB vs BoE vs BoJ vs RBA vs BOC)
  - Yield curve spreads (2s10s, US vs EU)
  - CPI surprise / inflation momentum
  - News sentiment

Output: per-symbol fundamental bias in [-1.0, +1.0]
  - Positive = bullish for the pair (BUY favored)
  - Negative = bearish (SELL favored)

Used by:
  - gate_FUND (binary: fundamental direction aligns with trade direction)
  - FW19_fundamental framework score
  - Direct bias adjustment on adjusted_score
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("overseer.fundamental_bias")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

_FUNDAMENTAL_JSON = _PROJECT_ROOT / "config" / "fundamental_bias.json"

_CURRENCY_MAP = {
    "6EM6": ("EUR", "USD"),
    "6BM6": ("GBP", "USD"),
    "6JM6": ("USD", "JPY"),
    "6AM6": ("AUD", "USD"),
    "6CM6": ("USD", "CAD"),
    "6NM6": ("NZD", "USD"),
    "6SM6": ("USD", "CHF"),
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "USDJPY": ("USD", "JPY"),
    "AUDUSD": ("AUD", "USD"),
    "USDCAD": ("USD", "CAD"),
    "NZDUSD": ("NZD", "USD"),
    "USDCHF": ("USD", "CHF"),
}

_FUNDAMENTAL_BIAS_WEIGHT = float(os.getenv("FUNDAMENTAL_BIAS_WEIGHT", "0.05"))

_cached_bias: dict[str, float] = {}
_cache_time: float = 0.0
_CACHE_TTL = 3600.0


def _get_rates() -> dict[str, float]:
    rates: dict[str, float] = {}

    try:
        from tools.fred_scraper import get_fred_data
        fred = get_fred_data()
        if fred.get("us_10y_yield", {}).get("value") is not None:
            rates["us_10y"] = float(fred["us_10y_yield"]["value"])
        if fred.get("us_2y_yield", {}).get("value") is not None:
            rates["us_2y"] = float(fred["us_2y_yield"]["value"])
        if fred.get("us_30y_yield", {}).get("value") is not None:
            rates["us_30y"] = float(fred["us_30y_yield"]["value"])
        if fred.get("us_2s10s_spread", {}).get("value") is not None:
            rates["us_2s10s"] = float(fred["us_2s10s_spread"]["value"])
        if fred.get("fed_funds_rate", {}).get("value") is not None:
            rates["fed_funds"] = float(fred["fed_funds_rate"]["value"])
        if fred.get("boe_rate", {}).get("value") is not None:
            rates["boe_rate"] = float(fred["boe_rate"]["value"])
        if fred.get("boj_rate", {}).get("value") is not None:
            rates["boj_rate"] = float(fred["boj_rate"]["value"])
        if fred.get("rba_rate", {}).get("value") is not None:
            rates["rba_rate"] = float(fred["rba_rate"]["value"])
        if fred.get("boc_rate", {}).get("value") is not None:
            rates["boc_rate"] = float(fred["boc_rate"]["value"])
        if fred.get("rbnz_rate", {}).get("value") is not None:
            rates["rbnz_rate"] = float(fred["rbnz_rate"]["value"])
        if fred.get("snb_rate", {}).get("value") is not None:
            rates["snb_rate"] = float(fred["snb_rate"]["value"])
    except Exception as exc:
        LOGGER.debug("FRED data unavailable: %s", exc)

    try:
        from tools.ecb_scraper import get_ecb_data
        ecb = get_ecb_data()
        if ecb.get("ecb_ref_rate", {}).get("value") is not None:
            rates["ecb_ref"] = float(ecb["ecb_ref_rate"]["value"])
        if ecb.get("ecb_deposit_rate", {}).get("value") is not None:
            rates["ecb_deposit"] = float(ecb["ecb_deposit_rate"]["value"])
        if ecb.get("eur_3m_euribor", {}).get("value") is not None:
            rates["eur_3m_euribor"] = float(ecb["eur_3m_euribor"]["value"])
    except Exception as exc:
        LOGGER.debug("ECB data unavailable: %s", exc)

    try:
        from tools.finnhub_scraper import get_usd_sentiment
        rates["usd_sentiment"] = get_usd_sentiment()
    except Exception as exc:
        LOGGER.debug("Finnhub sentiment unavailable: %s", exc)

    return rates


def _get_base_currency_rate(currency: str, rates: dict[str, float]) -> float | None:
    mapping = {
        "USD": rates.get("fed_funds"),
        "EUR": rates.get("ecb_ref") or rates.get("eur_3m_euribor"),
        "GBP": rates.get("boe_rate"),
        "JPY": rates.get("boj_rate"),
        "AUD": rates.get("rba_rate"),
        "CAD": rates.get("boc_rate"),
        "NZD": rates.get("rbnz_rate"),
        "CHF": rates.get("snb_rate"),
    }
    val = mapping.get(currency)
    if val is not None:
        return float(val)
    return None


def compute_fundamental_bias(symbol: str) -> float:
    global _cached_bias, _cache_time

    import time
    now = time.time()
    if symbol in _cached_bias and (now - _cache_time) < _CACHE_TTL:
        return _cached_bias[symbol]

    rates = _get_rates()
    if not rates:
        LOGGER.debug("No fundamental data available — bias=0")
        return 0.0

    pair = _CURRENCY_MAP.get(symbol)
    if pair is None:
        for key in _CURRENCY_MAP:
            if symbol.startswith(key[:2]):
                pair = _CURRENCY_MAP[key]
                break
    if pair is None:
        return 0.0

    base_currency, quote_currency = pair
    base_rate = _get_base_currency_rate(base_currency, rates)
    quote_rate = _get_base_currency_rate(quote_currency, rates)

    rate_diff = 0.0
    if base_rate is not None and quote_rate is not None:
        rate_diff = base_rate - quote_rate

    yield_bias = 0.0
    us_10y = rates.get("us_10y")
    if us_10y is not None:
        if symbol in ("6EM6", "EURUSD"):
            ecb_deposit = rates.get("ecb_deposit")
            if ecb_deposit is not None:
                yield_bias = max(-1.0, min(1.0, (ecb_deposit - us_10y) / 3.0))
        elif symbol in ("6BM6", "GBPUSD"):
            boe = rates.get("boe_rate")
            if boe is not None:
                yield_bias = max(-1.0, min(1.0, (boe - us_10y) / 3.0))
        elif symbol in ("6JM6", "USDJPY"):
            boj = rates.get("boj_rate")
            if boj is not None:
                yield_bias = max(-1.0, min(1.0, (us_10y - boj) / 3.0))
        elif symbol in ("6AM6", "AUDUSD"):
            rba = rates.get("rba_rate")
            if rba is not None:
                yield_bias = max(-1.0, min(1.0, (rba - us_10y) / 3.0))
        elif symbol in ("6CM6", "USDCAD"):
            boc = rates.get("boc_rate")
            if boc is not None:
                yield_bias = max(-1.0, min(1.0, (us_10y - boc) / 3.0))
        elif symbol in ("6NM6", "NZDUSD"):
            rbnz = rates.get("rbnz_rate")
            if rbnz is not None:
                yield_bias = max(-1.0, min(1.0, (rbnz - us_10y) / 3.0))
        elif symbol in ("6SM6", "USDCHF"):
            snb = rates.get("snb_rate")
            if snb is not None:
                yield_bias = max(-1.0, min(1.0, (us_10y - snb) / 3.0))

    sentiment_bias = 0.0
    usd_sentiment = rates.get("usd_sentiment", 0.0)
    if base_currency == "USD":
        sentiment_bias = usd_sentiment
    elif quote_currency == "USD":
        sentiment_bias = -usd_sentiment

    rate_weight = 0.5
    yield_weight = 0.35
    sentiment_weight = 0.15

    combined = (
        rate_weight * max(-1.0, min(1.0, rate_diff / 3.0))
        + yield_weight * yield_bias
        + sentiment_weight * sentiment_bias
    )

    bias = max(-1.0, min(1.0, combined))

    _cached_bias[symbol] = bias
    _cache_time = now

    return bias


def compute_all_biases() -> dict[str, float]:
    global _cached_bias, _cache_time
    import time
    now = time.time()
    if _cached_bias and (now - _cache_time) < _CACHE_TTL:
        return dict(_cached_bias)

    rates = _get_rates()
    for symbol in _CURRENCY_MAP:
        _cached_bias[symbol] = compute_fundamental_bias(symbol)
    _cache_time = now

    _FUNDAMENTAL_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(_FUNDAMENTAL_JSON, "w") as f:
        json.dump(_cached_bias, f, indent=2)

    return dict(_cached_bias)


def get_fundamental_bias_adjustment(symbol: str, direction: str) -> float:
    bias = compute_fundamental_bias(symbol)
    if direction == "BUY":
        if bias > 0:
            return bias * _FUNDAMENTAL_BIAS_WEIGHT
        else:
            return bias * _FUNDAMENTAL_BIAS_WEIGHT * 2.0
    else:
        if bias < 0:
            return abs(bias) * _FUNDAMENTAL_BIAS_WEIGHT
        else:
            return -bias * _FUNDAMENTAL_BIAS_WEIGHT * 2.0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    biases = compute_all_biases()
    for sym, bias in sorted(biases.items()):
        print(f"  {sym}: {bias:+.3f}")
