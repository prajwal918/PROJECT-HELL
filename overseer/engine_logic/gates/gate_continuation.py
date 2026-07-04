"""Post-Release Continuation Filter — Framework 10 scoring.

Standalone filter (NOT a BaseGate subclass) that evaluates whether the
market reaction after a high-impact news release warrants a continuation
trade.  Called directly from main.py rather than via GateRegistry.

Scoring rubric (max 8 points):
  T+0 candle body > 12 pips   → +2
  Price closed beyond pre-range → +1
  Spread < 3 pips by T+1 open  → +1
  T+0 aligns with trend         → +2
  T+0 aligns with hist. lean    → +1
  Trimmed-mean surprise aligned  → +1 / -1

  >= 6  → HIGH  (full size, 1.0)
  4-5   → MOD   (75% size, 0.75)
  < 4   → SKIP  (no trade, 0.0)
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

LOGGER = logging.getLogger("overseer.gate_continuation")

# ── calendar location (same as gate_news.py) ──
_CALENDAR_PATH = Path(__file__).resolve().parents[2] / "config" / "economic_calendar.json"

# ── configurable thresholds ──
_NEWS_PROXIMITY_MINUTES = int(os.getenv("NEWS_WAIT_MINUTES", "30"))
_T0_BODY_THRESHOLD_PIPS = float(os.getenv("T0_BODY_THRESHOLD_PIPS", "12.0"))
_SPREAD_OK_PIPS = float(os.getenv("SPREAD_OK_PIPS", "3.0"))

# ── high-impact event names (mirrors gate_news.py) ──
_HIGH_IMPACT_EVENTS: set[str] = {
    "Nonfarm Payrolls", "NFP", "Unemployment Rate",
    "FOMC", "Fed Interest Rate", "Federal Funds Rate",
    "CPI", "Consumer Price Index", "Core CPI",
    "GDP", "Gross Domestic Product",
    "Retail Sales", "ISM Manufacturing", "ISM Non-Manufacturing",
    "ECB Interest Rate", "BOE Interest Rate", "BOJ Interest Rate",
}


def _pip_size(symbol: str) -> float:
    from config.instrument_config import InstrumentConfig
    profile = InstrumentConfig.get_instance().get_profile(symbol)
    return profile.pip_size


class PostReleaseContinuationFilter:
    """Evaluates post-news candle continuation using Framework 10 logic.

    Lifecycle
    ---------
    1. ``should_wait_for_news()`` – call *before* every trade decision.
       If True, defer the trade; a high-impact release is imminent.
    2. ``evaluate_continuation(...)`` – score the T+0 candle once
       it has closed.  Returns confidence level and size modifier.
    3. ``get_post_news_verdict()`` – convenience wrapper that packages
       all Framework 10 fields into a single dict.
    """

    def __init__(self, calendar_path: Path | str | None = None) -> None:
        self._calendar_path = Path(calendar_path) if calendar_path else _CALENDAR_PATH
        self._calendar: list[dict[str, Any]] = []
        self._last_load: float = 0.0
        self._last_verdict: dict[str, Any] = {}
        LOGGER.debug(
            "PostReleaseContinuationFilter initialised — calendar=%s",
            self._calendar_path,
        )

    # ── internal helpers ──

    def _refresh_calendar(self) -> None:
        """Reload the calendar file at most every 60 s."""
        now = time.time()
        if now - self._last_load < 60.0:
            return
        if not self._calendar_path.exists():
            self._calendar = []
            self._last_load = now
            LOGGER.debug("No calendar file at %s", self._calendar_path)
            return
        try:
            raw = self._calendar_path.read_text(encoding="utf-8")
            self._calendar = json.loads(raw) if raw.strip() else []
        except (json.JSONDecodeError, OSError) as exc:
            LOGGER.warning("Calendar load failed: %s", exc)
            self._calendar = []
        self._last_load = now

    def _upcoming_high_impact(self) -> Optional[dict[str, Any]]:
        """Return the next high-impact event within the proximity window, or None."""
        self._refresh_calendar()
        now_ms = int(time.time() * 1000)
        window_ms = _NEWS_PROXIMITY_MINUTES * 60 * 1000

        closest: Optional[dict[str, Any]] = None
        closest_delta = float("inf")

        for event in self._calendar:
            event_name = str(event.get("name", ""))
            event_time_ms = int(event.get("timestamp_ms", 0))
            if event_time_ms <= 0:
                continue
            is_high = (
                event.get("impact", "").lower() == "high"
                or event_name in _HIGH_IMPACT_EVENTS
            )
            if not is_high:
                continue
            delta = event_time_ms - now_ms
            # Event is in the future and within the window
            if 0 < delta <= window_ms and delta < closest_delta:
                closest = event
                closest_delta = delta

        return closest

    # ── public API ──

    def should_wait_for_news(self) -> bool:
        """Return True if a high-impact news event is within the proximity window.

        When True the main engine should defer new entries until the
        continuation filter can score the post-release candle.
        """
        upcoming = self._upcoming_high_impact()
        if upcoming:
            LOGGER.debug(
                "News proximity: '%s' in %.1f min — deferring trades",
                upcoming.get("name", "?"),
                (int(upcoming.get("timestamp_ms", 0)) - time.time() * 1000) / 60_000,
            )
            return True
        return False

    def evaluate_continuation(
        self,
        t0_candle: dict[str, float],
        pre_range_high: float,
        pre_range_low: float,
        trend_direction: str,
        historical_lean: str,
        spread_pips: float,
        symbol: str = "EURUSD",
        trimmed_mean_surprise_aligned: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Score a T+0 post-release candle using Framework 10 criteria.

        Parameters
        ----------
        t0_candle : dict
            Must contain keys ``open``, ``high``, ``low``, ``close``.
        pre_range_high / pre_range_low : float
            High / Low of the 30-minute pre-release range.
        trend_direction : str
            ``'BUY'`` or ``'SELL'`` — the prevailing higher-TF trend.
        historical_lean : str
            ``'BEAT'``, ``'MISS'``, or ``'NEUTRAL'`` from ``EventAnalyzer``.
        spread_pips : float
            Spread at T+1 candle open in pips.
        symbol : str
            Trading symbol (used for pip-size calculation).
        trimmed_mean_surprise_aligned : bool | None
            Whether the trimmed-mean surprise direction aligns with
            the T+0 move.  ``None`` → score 0.

        Returns
        -------
        dict
            ``score``         – int total
            ``confidence``    – ``'HIGH'`` | ``'MODERATE'`` | ``'NO_TRADE'``
            ``size_modifier`` – 1.0 | 0.75 | 0.0
            ``breakdown``     – dict of individual criterion scores
        """
        pip = _pip_size(symbol)
        t0_open = float(t0_candle.get("open", 0.0))
        t0_close = float(t0_candle.get("close", 0.0))
        t0_body = abs(t0_close - t0_open)
        t0_body_pips = t0_body / pip if pip > 0 else 0.0
        t0_direction = "BUY" if t0_close > t0_open else "SELL"

        breakdown: dict[str, int] = {}

        # 1. T+0 body > 12 pips  (+2)
        if t0_body_pips > _T0_BODY_THRESHOLD_PIPS:
            breakdown["t0_body_size"] = 2
        else:
            breakdown["t0_body_size"] = 0

        # 2. Close beyond pre-release range  (+1)
        if t0_direction == "BUY" and t0_close > pre_range_high:
            breakdown["beyond_range"] = 1
        elif t0_direction == "SELL" and t0_close < pre_range_low:
            breakdown["beyond_range"] = 1
        else:
            breakdown["beyond_range"] = 0

        # 3. Spread returned to < 3 pips by T+1 open  (+1)
        if spread_pips < _SPREAD_OK_PIPS:
            breakdown["spread_normalised"] = 1
        else:
            breakdown["spread_normalised"] = 0

        # 4. T+0 direction aligns with trend  (+2)
        if t0_direction == trend_direction.upper():
            breakdown["trend_aligned"] = 2
        else:
            breakdown["trend_aligned"] = 0

        # 5. T+0 direction aligns with historical lean  (+1)
        lean_up = t0_direction == "BUY" and historical_lean.upper() == "BEAT"
        lean_down = t0_direction == "SELL" and historical_lean.upper() == "MISS"
        if lean_up or lean_down:
            breakdown["lean_aligned"] = 1
        else:
            breakdown["lean_aligned"] = 0

        # 6. Trimmed-mean surprise aligned  (+1 / -1)
        if trimmed_mean_surprise_aligned is True:
            breakdown["trimmed_mean"] = 1
        elif trimmed_mean_surprise_aligned is False:
            breakdown["trimmed_mean"] = -1
        else:
            breakdown["trimmed_mean"] = 0

        total = sum(breakdown.values())

        if total >= 6:
            confidence = "HIGH"
            size_mod = 1.0
        elif total >= 4:
            confidence = "MODERATE"
            size_mod = 0.75
        else:
            confidence = "NO_TRADE"
            size_mod = 0.0

        result: dict[str, Any] = {
            "score": total,
            "confidence": confidence,
            "size_modifier": size_mod,
            "t0_direction": t0_direction,
            "t0_body_pips": round(t0_body_pips, 2),
            "breakdown": breakdown,
        }
        self._last_verdict = result

        LOGGER.debug(
            "Continuation score=%d confidence=%s size=%.2f | body=%.1f pips dir=%s breakdown=%s",
            total, confidence, size_mod, t0_body_pips, t0_direction, breakdown,
        )
        return result

    def get_post_news_verdict(self) -> dict[str, Any]:
        """Return the most recent ``evaluate_continuation`` result.

        Useful for downstream consumers (e.g., Telegram alerts) that need
        the full Framework 10 breakdown without re-evaluating.
        """
        if not self._last_verdict:
            LOGGER.debug("No continuation verdict available yet.")
            return {
                "score": 0,
                "confidence": "NONE",
                "size_modifier": 0.0,
                "t0_direction": "UNKNOWN",
                "t0_body_pips": 0.0,
                "breakdown": {},
            }
        return dict(self._last_verdict)
