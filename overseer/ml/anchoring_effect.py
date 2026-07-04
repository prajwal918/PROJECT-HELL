import os
import logging

log = logging.getLogger(__name__)

_ENABLED = os.getenv("ANCHORING_EFFECT_ENABLED", "true").lower() == "true"
_BREAKOUT_BONUS = float(os.getenv("ANCHORING_BREAKOUT_BONUS", "0.04"))
_RESISTANCE_PENALTY = float(os.getenv("ANCHORING_RESISTANCE_PENALTY", "0.03"))
_PROXIMITY_PIPS = float(os.getenv("ANCHORING_PROXIMITY_PIPS", "5.0"))


class AnchoringEffect:
    def __init__(self):
        self._anchors = {}

    def set_anchors(self, symbol, yearly_open=None, monthly_open=None, weekly_open=None,
                    prior_close=None, round_figures=None):
        anchors = []
        if yearly_open:
            anchors.append(("yearly_open", yearly_open))
        if monthly_open:
            anchors.append(("monthly_open", monthly_open))
        if weekly_open:
            anchors.append(("weekly_open", weekly_open))
        if prior_close:
            anchors.append(("prior_close", prior_close))
        if round_figures:
            for rf in round_figures:
                anchors.append(("round_figure", rf))
        self._anchors[symbol] = anchors

    def get_bonus(self, symbol, direction, current_price, pip_size):
        if not _ENABLED:
            return 0.0
        anchors = self._anchors.get(symbol, [])
        if not anchors:
            return 0.0
        bonus = 0.0
        for anchor_name, anchor_price in anchors:
            distance = current_price - anchor_price
            abs_dist_pips = abs(distance) / pip_size
            if abs_dist_pips > _PROXIMITY_PIPS:
                continue
            if direction == "BUY":
                if distance > 0:
                    bonus += _BREAKOUT_BONUS
                elif distance < 0:
                    bonus -= _RESISTANCE_PENALTY
            elif direction == "SELL":
                if distance < 0:
                    bonus += _BREAKOUT_BONUS
                elif distance > 0:
                    bonus -= _RESISTANCE_PENALTY
        return bonus


anchoring_effect = AnchoringEffect()
