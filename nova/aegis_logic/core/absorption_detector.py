from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime

from nexus_bridge import NEXUSBridge, L3BookTracker, Tick
import numpy as np

@dataclass
class AbsorptionLevel:
    price: float
    side: str  # "bid" or "ask"
    initial_volume: float
    absorbed_volume: float
    aggressive_volume: float
    depth_retention_pct: float
    ticks_monitored: int
    is_active: bool

class AbsorptionDetector:
    """
    Gate 1: MBO Absorption Detection
    Identifies absorption zones where aggressive volume matches passive liquidity
    without significant depth depletion
    """

    def __init__(self, window_ticks: int = 1000, min_absorption_vol: float = 500.0):
        self.window_ticks = window_ticks
        self.min_absorption_vol = min_absorption_vol
        self.absorption_levels: Dict[float, AbsorptionLevel] = {}
        self.price_history = deque(maxlen=window_ticks)
        self.aggressive_volume_map: Dict[float, float] = {}
        self.book_tracker = L3BookTracker(max_depth=30)
        self.tick_count = 0

    def process_tick(self, tick: Tick) -> Optional[AbsorptionLevel]:
        """
        Processes each tick and detects absorption
        Returns AbsorptionLevel if absorption confirmed
        """
        self.book_tracker.process_tick(tick)
        self.price_history.append(tick.price)
        self.tick_count += 1

        side = "bid" if tick.side == 0 else "ask"

        if tick.action == 3 and tick.trade_size > 0:
            price_key = tick.price

            if price_key not in self.aggressive_volume_map:
                self.aggressive_volume_map[price_key] = 0.0

            self.aggressive_volume_map[price_key] += tick.trade_size

            book = self.book_tracker.bids if tick.side == 0 else self.book_tracker.asks

            if price_key in book:
                level_data = book[price_key]
                current_volume = level_data["size"]

                if price_key not in self.absorption_levels:
                    self.absorption_levels[price_key] = AbsorptionLevel(
                        price=price_key,
                        side=side,
                        initial_volume=current_volume,
                        absorbed_volume=0.0,
                        aggressive_volume=self.aggressive_volume_map[price_key],
                        depth_retention_pct=100.0,
                        ticks_monitored=0,
                        is_active=True
                    )

                absorption = self.absorption_levels[price_key]
                absorption.ticks_monitored += 1

                if current_volume > 0:
                    depth_retention = (current_volume / absorption.initial_volume) * 100
                    absorption.depth_retention_pct = depth_retention
                    absorption.absorbed_volume += tick.trade_size

                    if (absorption.absorbed_volume >= self.min_absorption_vol and
                        absorption.depth_retention_pct >= 50.0 and
                        absorption.ticks_monitored >= 50):

                        self.price_history.clear()
                        return absorption

        self._cleanup_old_levels()
        return None

    def _cleanup_old_levels(self):
        """Removes inactive absorption levels"""
        current_prices = set(self.book_tracker.bids.keys()) | set(self.book_tracker.asks.keys())

        for price in list(self.absorption_levels.keys()):
            level = self.absorption_levels[price]

            if price not in current_prices:
                level.is_active = False

            if not level.is_active or level.ticks_monitored > self.window_ticks:
                del self.absorption_levels[price]

    def get_active_absorption_levels(self) -> List[AbsorptionLevel]:
        """Returns currently active absorption levels"""
        return [level for level in self.absorption_levels.values() if level.is_active]

    def calculate_rejection_ratio(self, absorption_price: float) -> float:
        """
        Gate 3: Rejection Ratio
        Calculates ratio of wicks to body at absorption level
        """
        if len(self.price_history) < 100:
            return 0.0

        recent_prices = list(self.price_history)[-100:]
        prices_array = np.array(recent_prices)

        if len(prices_array) == 0:
            return 0.0

        high = np.max(prices_array)
        low = np.min(prices_array)
        open_price = prices_array[0]
        close_price = prices_array[-1]

        body = abs(close_price - open_price)

        if body == 0:
            return 0.0

        upper_wick = high - max(open_price, close_price)
        lower_wick = min(open_price, close_price) - low

        total_wick = upper_wick + lower_wick
        rejection_ratio = total_wick / body

        return rejection_ratio

    def detect_breakout(self, absorption_price: float, side: str) -> bool:
        """
        Gate 4: Breakout Confirmation
        Detects when price breaks through absorption level with momentum
        """
        if len(self.price_history) < 50:
            return False

        recent_prices = list(self.price_history)[-50:]

        if side == "bid":
            price_above = [p for p in recent_prices if p > absorption_price]
            if len(price_above) >= 10:
                return True
        else:
            price_below = [p for p in recent_prices if p < absorption_price]
            if len(price_below) >= 10:
                return True

        return False