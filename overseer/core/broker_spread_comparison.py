import os
import logging

log = logging.getLogger(__name__)

_ENABLED = os.getenv("BROKER_SPREAD_COMPARISON_ENABLED", "true").lower() == "true"
_SPREAD_PREMIUM_MULT = float(os.getenv("BROKER_SPREAD_PREMIUM_MULT", "2.0"))
_BROKER_WARNING_BONUS = float(os.getenv("BROKER_SPREAD_WARNING_BONUS", "0.05"))


class BrokerSpreadComparison:
    def __init__(self):
        self._market_spread = {}
        self._broker_spread = {}
        self._baseline_premium = {}
        self._warnings = {}

    def update_market_spread(self, symbol, spread_bps):
        self._market_spread[symbol] = spread_bps

    def update_broker_spread(self, symbol, spread_bps):
        self._broker_spread[symbol] = spread_bps

    def set_baseline_premium(self, symbol, premium_bps):
        self._baseline_premium[symbol] = premium_bps

    def check_warning(self, symbol):
        if not _ENABLED:
            return False, 0.0, None
        broker = self._broker_spread.get(symbol, 0)
        market = self._market_spread.get(symbol, 0)
        baseline = self._baseline_premium.get(symbol, 0.5)
        if market <= 0:
            return False, 0.0, None
        premium = broker - market
        if premium > baseline * _SPREAD_PREMIUM_MULT:
            self._warnings[symbol] = True
            if broker > self._broker_spread.get(symbol, broker) * 0.8:
                direction = "SELL" if broker > market else "BUY"
            else:
                direction = None
            return True, premium, direction
        self._warnings[symbol] = False
        return False, 0.0, None

    def get_directional_lean(self, symbol):
        if not _ENABLED:
            return None
        warning, _, direction = self.check_warning(symbol)
        if warning and direction:
            return direction
        return None


broker_spread_comparison = BrokerSpreadComparison()
