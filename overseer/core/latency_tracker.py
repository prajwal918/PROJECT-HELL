from __future__ import annotations

import logging
import os
import time
from collections import deque
from typing import Any

LOGGER = logging.getLogger("overseer.latency_tracker")

_MAX_HISTORY = int(os.getenv("LATENCY_HISTORY_SIZE", "1000"))
_ALERT_P95_MS = float(os.getenv("LATENCY_ALERT_P95_MS", "500.0"))
_ALERT_FILL_MS = float(os.getenv("LATENCY_ALERT_FILL_MS", "1000.0"))


class LatencyTracker:
    def __init__(self) -> None:
        self._enrich_ms: deque[float] = deque(maxlen=_MAX_HISTORY)
        self._gates_ms: deque[float] = deque(maxlen=_MAX_HISTORY)
        self._score_ms: deque[float] = deque(maxlen=_MAX_HISTORY)
        self._decision_ms: deque[float] = deque(maxlen=_MAX_HISTORY)
        self._fill_ms: deque[float] = deque(maxlen=_MAX_HISTORY)
        self._total_ms: deque[float] = deque(maxlen=_MAX_HISTORY)
        self._t_start: float = 0.0
        self._t_enriched: float = 0.0
        self._t_gates_done: float = 0.0
        self._t_scored: float = 0.0
        self._t_decision: float = 0.0
        self._t_fill: float = 0.0

    def start_tick(self) -> None:
        self._t_start = time.perf_counter()

    def mark_enriched(self) -> None:
        self._t_enriched = time.perf_counter()
        self._enrich_ms.append((self._t_enriched - self._t_start) * 1000)

    def mark_gates_done(self) -> None:
        self._t_gates_done = time.perf_counter()
        self._gates_ms.append((self._t_gates_done - self._t_enriched) * 1000)

    def mark_scored(self) -> None:
        self._t_scored = time.perf_counter()
        self._score_ms.append((self._t_scored - self._t_gates_done) * 1000)

    def mark_decision(self) -> None:
        self._t_decision = time.perf_counter()
        self._decision_ms.append((self._t_decision - self._t_scored) * 1000)

    def mark_fill(self) -> None:
        self._t_fill = time.perf_counter()
        fill_lat = (self._t_fill - self._t_decision) * 1000
        self._fill_ms.append(fill_lat)
        self._total_ms.append((self._t_fill - self._t_start) * 1000)
        if fill_lat > _ALERT_FILL_MS:
            LOGGER.warning("Fill latency %.0fms > alert threshold %.0fms", fill_lat, _ALERT_FILL_MS)

    def get_pipeline_latencies(self) -> dict[str, float]:
        now = time.perf_counter()
        return {
            "enrich_ms": (now - self._t_start) * 1000 if self._t_enriched > 0 else 0,
            "gates_ms": (now - self._t_enriched) * 1000 if self._t_gates_done > 0 and self._t_enriched > 0 else 0,
            "score_ms": (now - self._t_gates_done) * 1000 if self._t_scored > 0 and self._t_gates_done > 0 else 0,
        }

    def get_percentiles(self, series: str = "total") -> dict[str, float]:
        data = {
            "enrich": self._enrich_ms,
            "gates": self._gates_ms,
            "score": self._score_ms,
            "decision": self._decision_ms,
            "fill": self._fill_ms,
            "total": self._total_ms,
        }.get(series, self._total_ms)

        if not data:
            return {"p50": 0, "p95": 0, "p99": 0, "avg": 0}

        sorted_data = sorted(data)
        n = len(sorted_data)
        p50 = sorted_data[int(n * 0.50)] if n > 0 else 0
        p95 = sorted_data[int(n * 0.95)] if n > 0 else 0
        p99 = sorted_data[int(n * 0.99)] if n > 0 else 0
        avg = sum(sorted_data) / n

        if p95 > _ALERT_P95_MS and series == "total":
            LOGGER.warning("Pipeline P95 latency %.0fms > alert threshold %.0fms", p95, _ALERT_P95_MS)

        return {"p50": round(p50, 1), "p95": round(p95, 1), "p99": round(p99, 1), "avg": round(avg, 1)}

    def get_all_percentiles(self) -> dict[str, dict[str, float]]:
        result = {}
        for series in ("enrich", "gates", "score", "decision", "fill", "total"):
            result[series] = self.get_percentiles(series)
        return result

    def get_tick_timestamps(self) -> dict[str, float]:
        return {
            "t_tick_received": self._t_start,
            "t_enriched": self._t_enriched,
            "t_gates_done": self._t_gates_done,
            "t_scored": self._t_scored,
            "t_decision": self._t_decision,
            "t_fill": self._t_fill,
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "percentiles": self.get_all_percentiles(),
            "sample_count": len(self._total_ms),
        }
