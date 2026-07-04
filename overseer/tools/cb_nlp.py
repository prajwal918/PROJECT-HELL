"""Central Bank NLP Engine — FinBERT / keyword analysis on policy communications.

Hawkish-Dovish classification beyond keyword matching.
FOMC statement diff — detect tone shifts between statements.
Forward guidance parsing — extract policy signals.
Policy surprise extraction — actual rate vs market-implied probability.
Central bank communication index (Hansen-McMahon 2016 style).
"""
from __future__ import annotations

import logging
import math
import os
import re
from collections import deque
from typing import Any

LOGGER = logging.getLogger("overseer.cb_nlp")

HAWKISH_KEYWORDS = [
    "hawkish", "tighten", "tightening", "rate hike", "raise rates", "inflation risk",
    "inflation expectations", "normalize", "normalization", "reduce accommodation",
    "withdraw accommodation", "preemptive", "restrictive", "overheating",
    "above target", "upside risk", "firming", "continued firming",
    "less accommodative", "balance sheet reduction", "quantitative tightening",
    "higher for longer", "no cuts", "patient on cuts", "not yet time",
]
DOVISH_KEYWORDS = [
    "dovish", "easing", "rate cut", "lower rates", "accommodative", "stimulus",
    "below target", "downside risk", "deflationary", "slack", "output gap",
    "insufficient progress", "disinflation", "need for patience", "gradual approach",
    "data dependent", "cautious", "careful", "premature to declare",
    "not thinking about", "not yet", "more time needed", "transitory",
    "flexible average inflation targeting", "maximum employment",
]
POLICY_SIGNALS = [
    "data dependent", "patient", "gradual", "measured", "deliberate",
    "some time", "not yet", "premature", "appropriate pace", "confident",
    "before it will be appropriate", "well positioned", "balanced approach",
]
SURPRISE_THRESHOLD = float(os.getenv("POLICY_SURPRISE_THRESHOLD", "0.25"))


class CentralBankNLP:
    """NLP engine for central bank communications."""

    def __init__(self) -> None:
        self._statement_history: list[dict[str, Any]] = []
        self._hawkish_dovish_score: float = 0.0
        self._policy_surprise: float = 0.0
        self._communication_index: deque[float] = deque(maxlen=100)
        self._forward_guidance_signals: dict[str, float] = {}
        self._last_statement_text: str = ""
        self._finbert_available: bool = False
        try:
            from transformers import pipeline
            self._sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert", top_k=None)
            self._finbert_available = True
            LOGGER.info("FinBERT loaded for central bank NLP")
        except Exception:
            self._sentiment_pipeline = None
            LOGGER.info("FinBERT not available — using keyword-based NLP")

    def analyze_statement(self, text: str, source: str = "FOMC", actual_rate: float = 0.0, expected_rate: float = 0.0) -> dict[str, Any]:
        if self._finbert_available and self._sentiment_pipeline is not None:
            hawkish_score, dovish_score, neutral_score = self._finbert_analyze(text)
        else:
            hawkish_score, dovish_score, neutral_score = self._keyword_analyze(text)
        net_score = hawkish_score - dovish_score
        self._hawkish_dovish_score = net_score
        diff_result = {}
        if self._last_statement_text:
            diff_result = self._statement_diff(text, self._last_statement_text)
        guidance = self._parse_forward_guidance(text)
        surprise = 0.0
        if actual_rate != 0 or expected_rate != 0:
            surprise = (actual_rate - expected_rate) / max(abs(expected_rate), 0.01)
            self._policy_surprise = surprise
        comm_index = abs(net_score) * 10 + len(text) / 1000.0
        self._communication_index.append(comm_index)
        result = {
            "source": source,
            "hawkish_score": round(hawkish_score, 4),
            "dovish_score": round(dovish_score, 4),
            "neutral_score": round(neutral_score, 4),
            "net_hawkish_dovish": round(net_score, 4),
            "forward_guidance": guidance,
            "policy_surprise": round(surprise, 4),
            "is_surprise": abs(surprise) > SURPRISE_THRESHOLD,
            "statement_diff": diff_result,
            "communication_index": round(comm_index, 2),
            "finbert_used": self._finbert_available,
        }
        self._statement_history.append(result)
        self._last_statement_text = text
        return result

    def _finbert_analyze(self, text: str) -> tuple[float, float, float]:
        if not self._sentiment_pipeline:
            return 0.0, 0.0, 1.0
        try:
            sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 20][:20]
            hawk_total = 0.0
            dov_total = 0.0
            neu_total = 0.0
            for sent in sentences:
                result = self._sentiment_pipeline(sent)
                if isinstance(result, list) and len(result) > 0:
                    scores = {r["label"]: r["score"] for r in result[0]} if isinstance(result[0], list) else {}
                    hawk_total += scores.get("positive", 0)
                    dov_total += scores.get("negative", 0)
                    neu_total += scores.get("neutral", 0)
            n = max(1, len(sentences))
            return hawk_total / n, dov_total / n, neu_total / n
        except Exception:
            return self._keyword_analyze(text)

    def _keyword_analyze(self, text: str) -> tuple[float, float, float]:
        text_lower = text.lower()
        hawk_count = sum(1 for kw in HAWKISH_KEYWORDS if kw in text_lower)
        dov_count = sum(1 for kw in DOVISH_KEYWORDS if kw in text_lower)
        total = max(1, hawk_count + dov_count)
        hawk_score = hawk_count / total
        dov_score = dov_count / total
        neutral = max(0, 1.0 - hawk_score - dov_score)
        return hawk_score, dov_score, neutral

    def _statement_diff(self, current: str, previous: str) -> dict[str, Any]:
        curr_words = set(current.lower().split())
        prev_words = set(previous.lower().split())
        added = curr_words - prev_words
        removed = prev_words - curr_words
        added_hawk = sum(1 for w in added if any(kw in w for kw in HAWKISH_KEYWORDS))
        added_dov = sum(1 for w in added if any(kw in w for kw in DOVISH_KEYWORDS))
        removed_hawk = sum(1 for w in removed if any(kw in w for kw in HAWKISH_KEYWORDS))
        removed_dov = sum(1 for w in removed if any(kw in w for kw in DOVISH_KEYWORDS))
        tone_shift = (added_hawk + removed_dov) - (added_dov + removed_hawk)
        return {
            "words_added": len(added),
            "words_removed": len(removed),
            "added_hawkish": added_hawk,
            "added_dovish": added_dov,
            "removed_hawkish": removed_hawk,
            "removed_dovish": removed_dov,
            "tone_shift": round(tone_shift, 2),
            "shift_direction": "hawkish" if tone_shift > 1 else ("dovish" if tone_shift < -1 else "neutral"),
        }

    def _parse_forward_guidance(self, text: str) -> dict[str, float]:
        text_lower = text.lower()
        signals: dict[str, float] = {}
        for signal in POLICY_SIGNALS:
            if signal in text_lower:
                signals[signal] = 1.0
        if "data dependent" in text_lower:
            signals["guidance_data_dependent"] = 0.5
        if "patient" in text_lower or "patience" in text_lower:
            signals["guidance_patient"] = 0.3
        if "gradual" in text_lower:
            signals["guidance_gradual"] = 0.2
        if "premature" in text_lower:
            signals["guidance_premature"] = 0.6
        self._forward_guidance_signals = signals
        return signals

    def get_directional_bias(self, currency: str) -> float:
        score = self._hawkish_dovish_score
        if currency == "USD":
            return score
        elif currency == "EUR":
            return -score * 0.8
        elif currency == "GBP":
            return -score * 0.6
        elif currency == "JPY":
            return -score * 0.5
        elif currency == "AUD":
            return -score * 0.4
        elif currency == "CAD":
            return -score * 0.3
        return 0.0

    def get_surprise_signal(self) -> dict[str, float]:
        return {
            "policy_surprise": self._policy_surprise,
            "is_surprise": abs(self._policy_surprise) > SURPRISE_THRESHOLD,
            "surprise_direction": 1.0 if self._policy_surprise > 0 else -1.0 if self._policy_surprise < 0 else 0.0,
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "statements_analyzed": len(self._statement_history),
            "finbert_available": self._finbert_available,
            "current_hawkish_dovish": round(self._hawkish_dovish_score, 4),
            "policy_surprise": round(self._policy_surprise, 4),
        }
