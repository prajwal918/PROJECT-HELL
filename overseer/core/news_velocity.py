import os
import logging
from collections import deque

log = logging.getLogger(__name__)

_ENABLED = os.getenv("NEWS_VELOCITY_ENABLED", "true").lower() == "true"
_ACCELERATION_THRESHOLD = float(os.getenv("NEWS_VELOCITY_THRESHOLD", "3.0"))
_RISK_OFF_BONUS = float(os.getenv("NEWS_VELOCITY_RISK_OFF_BONUS", "0.06"))
_RISK_ON_BONUS = float(os.getenv("NEWS_VELOCITY_RISK_ON_BONUS", "0.04"))


class NewsVelocity:
    def __init__(self):
        self._headlines = {}
        self._last_velocity = {}

    def add_headline(self, category, sentiment, timestamp):
        if category not in self._headlines:
            self._headlines[category] = deque(maxlen=500)
        self._headlines[category].append({"sentiment": sentiment, "ts": timestamp})

    def compute_velocity(self, category, current_time, lookback_short_min=15, lookback_long_min=60):
        if not _ENABLED:
            return 0.0, "NEUTRAL"
        headlines = self._headlines.get(category, deque())
        if len(headlines) < 5:
            return 0.0, "NEUTRAL"
        short_cutoff = current_time - lookback_short_min * 60
        long_cutoff = current_time - lookback_long_min * 60
        short_negative = sum(1 for h in headlines if h["ts"] > short_cutoff and h["sentiment"] < -0.3)
        long_negative = sum(1 for h in headlines if h["ts"] > long_cutoff and h["sentiment"] < -0.3)
        short_rate = short_negative * (60 / lookback_short_min)
        velocity = short_rate - long_negative
        self._last_velocity[category] = velocity
        if velocity > _ACCELERATION_THRESHOLD:
            return velocity, "RISK_OFF"
        elif velocity < -_ACCELERATION_THRESHOLD:
            return velocity, "RISK_ON"
        return velocity, "NEUTRAL"

    def get_bonus(self, category, symbol, direction, current_time):
        if not _ENABLED:
            return 0.0
        velocity, sentiment = self.compute_velocity(category, current_time)
        if sentiment == "RISK_OFF":
            safe_haven_pairs = {"6JM6": "BUY", "6SM6": "BUY"}
            risk_pairs = {"6AM6": "SELL", "6NM6": "SELL", "6BM6": "SELL"}
            if safe_haven_pairs.get(symbol) == direction:
                return _RISK_OFF_BONUS
            if risk_pairs.get(symbol) == direction:
                return _RISK_OFF_BONUS
        elif sentiment == "RISK_ON":
            risk_pairs_buy = {"6AM6": "BUY", "6NM6": "BUY"}
            if risk_pairs_buy.get(symbol) == direction:
                return _RISK_ON_BONUS
        return 0.0


news_velocity = NewsVelocity()
