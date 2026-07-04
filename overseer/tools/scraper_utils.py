"""Shared scraper utilities for OVERSEER v12.

Provides retry logic, health-check helpers, and stale-data detection
used by all data-source scrapers (calendar, COT, IV).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

LOGGER = logging.getLogger("overseer.scraper_utils")

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2.0
_RETRY_BACKOFF_MAX = 60.0


def fetch_with_retry(
    fetch_fn: Callable[[], Any],
    max_retries: int = _MAX_RETRIES,
    label: str = "scraper",
) -> Any:
    """Call *fetch_fn* with exponential-backoff retries (synchronous).

    .. note::
        This function uses ``time.sleep()`` which blocks the asyncio
        event loop.  From async code, use :func:`fetch_with_retry_async`
        instead, or wrap this call with ``asyncio.to_thread()``.
    """
    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            result = fetch_fn()
            if result is not None:
                return result
        except Exception as exc:
            last_exception = exc
            LOGGER.warning(
                "[%s] attempt %d/%d failed: %s",
                label, attempt, max_retries, exc,
            )

        if attempt < max_retries:
            delay = min(_RETRY_BACKOFF_BASE ** attempt, _RETRY_BACKOFF_MAX)
            LOGGER.info("[%s] retrying in %.1fs ...", label, delay)
            time.sleep(delay)

    LOGGER.error(
        "[%s] all %d attempts failed — last error: %s",
        label, max_retries, last_exception,
    )
    return []


async def fetch_with_retry_async(
    fetch_fn: Callable[[], Any],
    max_retries: int = _MAX_RETRIES,
    label: str = "scraper",
) -> Any:
    """Async variant of :func:`fetch_with_retry`.

    Runs *fetch_fn* in a thread (to avoid blocking) and uses
    ``asyncio.sleep()`` for backoff so the event loop stays responsive.
    """
    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            result = await asyncio.to_thread(fetch_fn)
            if result is not None:
                return result
        except Exception as exc:
            last_exception = exc
            LOGGER.warning(
                "[%s] attempt %d/%d failed: %s",
                label, attempt, max_retries, exc,
            )

        if attempt < max_retries:
            delay = min(_RETRY_BACKOFF_BASE ** attempt, _RETRY_BACKOFF_MAX)
            LOGGER.info("[%s] retrying in %.1fs ...", label, delay)
            await asyncio.sleep(delay)

    LOGGER.error(
        "[%s] all %d attempts failed — last error: %s",
        label, max_retries, last_exception,
    )
    return []


def is_data_stale(
    scraped_at_iso: str | None,
    max_age_hours: float = 8.0,
) -> bool:
    """Return True if *scraped_at_iso* is older than *max_age_hours*.

    Parameters
    ----------
    scraped_at_iso : str or None
        ISO-format datetime string from the database, or None.
    max_age_hours : float
        Maximum acceptable age in hours.

    Returns
    -------
    bool
        True when data is stale or missing.
    """
    if scraped_at_iso is None:
        return True

    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(scraped_at_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(tz=timezone.utc) - dt).total_seconds() / 3600.0
        return age_hours > max_age_hours
    except (ValueError, TypeError):
        return True


class ScraperHealth:
    """Track the health status of a scraper over time.

    Usage
    -----
    >>> health = ScraperHealth("calendar")
    >>> health.record_success(count=42)
    >>> health.record_failure()
    >>> health.is_healthy()
    True
    """

    def __init__(self, name: str, window: int = 10) -> None:
        self.name = name
        self.window = window
        self._outcomes: list[bool] = []
        self._last_success_time: float = 0.0
        self._last_failure_time: float = 0.0
        self._consecutive_failures: int = 0

    def record_success(self, count: int = 0) -> None:
        self._outcomes.append(True)
        if len(self._outcomes) > self.window:
            self._outcomes = self._outcomes[-self.window:]
        self._last_success_time = time.time()
        self._consecutive_failures = 0
        if count > 0:
            LOGGER.info("[%s] scrape OK — %d records", self.name, count)
        else:
            LOGGER.info("[%s] scrape OK", self.name)

    def record_failure(self) -> None:
        self._outcomes.append(False)
        if len(self._outcomes) > self.window:
            self._outcomes = self._outcomes[-self.window:]
        self._last_failure_time = time.time()
        self._consecutive_failures += 1
        LOGGER.warning(
            "[%s] scrape FAILED (consecutive=%d)",
            self.name, self._consecutive_failures,
        )

    def is_healthy(self) -> bool:
        """Return True if the scraper is functioning acceptably.

        A scraper is unhealthy when >70% of recent attempts failed
        or there are 5+ consecutive failures.
        """
        if self._consecutive_failures >= 5:
            return False
        if len(self._outcomes) < 3:
            return True
        failure_rate = sum(1 for o in self._outcomes if not o) / len(self._outcomes)
        return failure_rate < 0.7

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def seconds_since_last_success(self) -> float:
        if self._last_success_time == 0:
            return float("inf")
        return time.time() - self._last_success_time

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "healthy": self.is_healthy(),
            "consecutive_failures": self._consecutive_failures,
            "recent_outcomes": self._outcomes,
            "seconds_since_last_success": round(self.seconds_since_last_success, 1),
        }
