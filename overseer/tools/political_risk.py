from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

POLITICAL_RISK_ENABLED = os.getenv("POLITICAL_RISK_ENABLED", "true").lower() == "true"
POLITICAL_RISK_VELOCITY_THRESHOLD = float(os.getenv("POLITICAL_RISK_VELOCITY_THRESHOLD", "2.0"))
POLITICAL_RISK_CACHE_TTL_S = float(os.getenv("POLITICAL_RISK_CACHE_TTL_S", "43200"))
POLITICAL_RISK_BIAS_MAX = float(os.getenv("POLITICAL_RISK_BIAS_MAX", "0.10"))

_GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

_CURRENCY_COUNTRY = {
    "USD": "US", "EUR": "EU", "GBP": "UK", "JPY": "JP",
    "AUD": "AU", "CAD": "CA", "NZD": "NZ", "CHF": "CH",
}

_PAIR_BASE = {
    "6E": "EUR", "6B": "GBP", "6J": "JPY", "6A": "AUD",
    "6C": "CAD", "6N": "NZD", "6S": "CHF",
    "EURUSD": "EUR", "GBPUSD": "GBP", "USDJPY": "JPY",
    "AUDUSD": "AUD", "USDCAD": "CAD", "NZDUSD": "NZD", "USDCHF": "CHF",
}

_PAIR_QUOTE = {
    "6E": "USD", "6B": "USD", "6J": "USD", "6A": "USD",
    "6C": "USD", "6N": "USD", "6S": "USD",
    "EURUSD": "USD", "GBPUSD": "USD", "USDJPY": "JPY",
    "AUDUSD": "USD", "USDCAD": "CAD", "NZDUSD": "NZD", "USDCHF": "CHF",
}


def _safe_get(url, params=None, timeout=15):
    try:
        import urllib.request
        import urllib.parse
        if params:
            query = urllib.parse.urlencode(params)
            url = "{}?{}".format(url, query)
        req = urllib.request.Request(url, headers={"User-Agent": "OVERSEER/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("PoliticalRisk fetch failed: %s", exc)
        return None


class PoliticalRisk:
    def __init__(self):
        self._enabled = POLITICAL_RISK_ENABLED
        self._velocity_threshold = POLITICAL_RISK_VELOCITY_THRESHOLD
        self._cache_ttl = POLITICAL_RISK_CACHE_TTL_S
        self._bias_max = POLITICAL_RISK_BIAS_MAX
        self._risk_current = {}  # type: Dict[str, float]
        self._risk_prev = {}  # type: Dict[str, float]
        self._risk_fetch_time = {}  # type: Dict[str, float]
        if not self._enabled:
            logger.info("PoliticalRisk disabled via POLITICAL_RISK_ENABLED=false")

    def fetch_risk(self, country):
        if not self._enabled:
            return 0.0
        now = time.time()
        cached_time = self._risk_fetch_time.get(country, 0.0)
        if now - cached_time < self._cache_ttl and country in self._risk_current:
            return self._risk_current[country]
        try:
            params = {
                "query": "sourcecountry:{}".format(country),
                "mode": "ArtVolInfo",
                "format": "json",
                "maxrecords": "250",
                "timespan": "7d",
            }
            raw = _safe_get(_GDELT_API_URL, params=params)
            if raw is None:
                logger.warning("PoliticalRisk: no data for %s, using previous", country)
                return self._risk_current.get(country, 0.0)
            data = json.loads(raw)
            articles = data.get("articles", [])
            conflict_count = 0
            protest_count = 0
            total = len(articles)
            for art in articles:
                themes = art.get("themes", "") or ""
                if "CONFLICT" in themes.upper() or "WAR" in themes.upper():
                    conflict_count += 1
                if "PROTEST" in themes.upper() or "UNREST" in themes.upper():
                    protest_count += 1
            risk_score = (conflict_count * 3.0 + protest_count * 1.0) / max(total, 1) * 10.0
            prev = self._risk_current.get(country, 0.0)
            self._risk_prev[country] = prev
            self._risk_current[country] = risk_score
            self._risk_fetch_time[country] = now
            logger.debug("PoliticalRisk: %s risk=%.2f (prev=%.2f, articles=%d)", country, risk_score, prev, total)
            return risk_score
        except Exception as exc:
            logger.error("PoliticalRisk fetch_risk(%s) error: %s", country, exc)
            return self._risk_current.get(country, 0.0)

    def get_risk_velocity(self, currency):
        if not self._enabled:
            return 0.0
        country = _CURRENCY_COUNTRY.get(currency, "")
        if not country:
            return 0.0
        self.fetch_risk(country)
        current = self._risk_current.get(country, 0.0)
        previous = self._risk_prev.get(country, 0.0)
        if previous == 0.0:
            return 0.0
        velocity = (current - previous) / max(previous, 0.01)
        return float(velocity)

    def get_bias_modifier(self, symbol):
        if not self._enabled:
            return 0.0
        base_ccy = _PAIR_BASE.get(symbol, "")
        quote_ccy = _PAIR_QUOTE.get(symbol, "")
        if not base_ccy or not quote_ccy:
            return 0.0
        base_velocity = self.get_risk_velocity(base_ccy)
        quote_velocity = self.get_risk_velocity(quote_ccy)
        net_velocity = quote_velocity - base_velocity
        if abs(net_velocity) < self._velocity_threshold:
            return 0.0
        if net_velocity > 0:
            modifier = -min(net_velocity / 10.0, self._bias_max)
        else:
            modifier = min(abs(net_velocity) / 10.0, self._bias_max)
        return float(modifier)


political_risk = PoliticalRisk()
