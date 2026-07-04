from __future__ import annotations

import logging
import os
import re
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DOT_PLOT_ENABLED = os.getenv("DOT_PLOT_ENABLED", "true").lower() == "true"
DOT_PLOT_SHIFT_THRESHOLD = float(os.getenv("DOT_PLOT_SHIFT_THRESHOLD", "0.25"))
DOT_PLOT_EFFECT_DAYS = int(os.getenv("DOT_PLOT_EFFECT_DAYS", "5"))
DOT_PLOT_BONUS = float(os.getenv("DOT_PLOT_BONUS", "0.08"))

_HAWKISH_KEYWORDS = [
    "higher for longer", "restrictive policy", "inflation remains elevated",
    "further tightening", "need for additional rate increases", "premature to ease",
    "not yet at target", "upside risks to inflation", "labor market tight",
    "wage growth elevated", "consider additional policy firming",
    "maintain restrictive stance", "less confident inflation returning",
    "pause does not mean end", "prepared to raise further",
]

_DOVISH_KEYWORDS = [
    "begin to ease", "rate cuts appropriate", "inflation moving toward",
    "balanced risks", "employment concerns", "economic slowdown",
    "pivot", "easing cycle", "sufficiently restrictive",
    "achieving dual mandate", "disinflationary process", "need to calibrate",
    "confidence inflation returning", "progress toward target",
    "reduce restraint", "gradual normalization",
]


class DotPlotAnalyzer:
    def __init__(self):
        self._enabled = DOT_PLOT_ENABLED
        self._shift_threshold = DOT_PLOT_SHIFT_THRESHOLD
        self._effect_days = DOT_PLOT_EFFECT_DAYS
        self._bonus = DOT_PLOT_BONUS
        self._last_statement = None  # type: Optional[str]
        self._current_shift = 0.0
        self._shift_direction = None  # type: Optional[str]
        self._shift_time = 0.0
        self._hawkish_score = 0.0
        self._dovish_score = 0.0
        if not self._enabled:
            logger.info("DotPlotAnalyzer disabled via DOT_PLOT_ENABLED=false")

    def _score_text(self, text):
        text_lower = text.lower()
        hawk_count = 0
        dove_count = 0
        for kw in _HAWKISH_KEYWORDS:
            if kw in text_lower:
                hawk_count += 1
        for kw in _DOVISH_KEYWORDS:
            if kw in text_lower:
                dove_count += 1
        rate_refs = re.findall(r"(\d+\.\d+)\s*%", text)
        rate_values = [float(r) for r in rate_refs if 0.0 < float(r) < 10.0]
        avg_rate = sum(rate_values) / len(rate_values) if rate_values else 0.0
        hawk_score = hawk_count * 0.15 + min(avg_rate / 5.0, 0.3)
        dove_score = dove_count * 0.15
        return hawk_score, dove_score

    def analyze_statement(self, text, prev_text=None):
        if not self._enabled:
            return 0.0, None
        hawk, dove = self._score_text(text)
        self._hawkish_score = hawk
        self._dovish_score = dove
        current_net = hawk - dove
        if prev_text:
            prev_hawk, prev_dove = self._score_text(prev_text)
            prev_net = prev_hawk - prev_dove
        elif self._last_statement:
            prev_hawk, prev_dove = self._score_text(self._last_statement)
            prev_net = prev_hawk - prev_dove
        else:
            prev_net = 0.0
        shift = current_net - prev_net
        self._current_shift = shift
        if abs(shift) >= self._shift_threshold:
            self._shift_direction = "BUY" if shift > 0 else "SELL"
            self._shift_time = time.time()
            logger.info(
                "DotPlotAnalyzer: FOMC shift detected: %.3f (direction=%s, hawk=%.2f dove=%.2f)",
                shift, self._shift_direction, hawk, dove,
            )
        else:
            self._shift_direction = None
            logger.debug("DotPlotAnalyzer: no significant shift (%.3f)", shift)
        self._last_statement = text
        return shift, self._shift_direction

    def get_usd_signal(self):
        if not self._enabled:
            return None, 0.0, 0
        if self._shift_direction is None:
            return None, 0.0, 0
        elapsed_days = (time.time() - self._shift_time) / 86400.0
        remaining = max(0, self._effect_days - int(elapsed_days))
        if remaining <= 0:
            self._shift_direction = None
            return None, 0.0, 0
        magnitude = min(abs(self._current_shift), 1.0)
        return self._shift_direction, magnitude, remaining

    def get_bonus(self, symbol, direction):
        if not self._enabled:
            return 0.0
        usd_dir, magnitude, remaining = self.get_usd_signal()
        if usd_dir is None or remaining <= 0:
            return 0.0
        is_usd_base = symbol.endswith("USD") or "6C" in symbol or "6J" in symbol or "6S" in symbol
        if is_usd_base:
            trade_aligns = (direction == "BUY" and usd_dir == "BUY") or (direction == "SELL" and usd_dir == "SELL")
        else:
            trade_aligns = (direction == "BUY" and usd_dir == "SELL") or (direction == "SELL" and usd_dir == "BUY")
        if trade_aligns:
            decay = remaining / self._effect_days
            return self._bonus * magnitude * decay
        return 0.0


dot_plot_analyzer = DotPlotAnalyzer()
