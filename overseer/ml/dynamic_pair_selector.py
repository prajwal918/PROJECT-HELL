"""Dynamic pair/direction selector backed by real signal_log validation data.

The selector is intentionally conservative:
- It never enables live execution.
- It ignores legacy negative-spread research rows via the sweep tool.
- It requires pair/direction validation proof and live rule matches before a
  signal can be treated as a candidate.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PARAMS_PATH = Path("config/dynamic_elite_params_rare_min5.json")

STATUS_TRADE_CANDIDATE = "TRADE_CANDIDATE"
STATUS_TRADE_CANDIDATE_SIGNAL_ONLY = "TRADE_CANDIDATE_SIGNAL_ONLY"
STATUS_WATCHLIST = "WATCHLIST"
STATUS_BLOCK = "BLOCK"


@dataclass(frozen=True)
class DynamicRule:
    feature: str
    op: str
    threshold: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DynamicRule":
        return cls(
            feature=str(data.get("feature", "")),
            op=str(data.get("op", ">=")),
            threshold=float(data.get("threshold", 0.0)),
        )

    def passes(self, features: dict[str, Any]) -> bool:
        value = features.get(self.feature)
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(value):
            return False
        if self.op == ">=":
            return value >= self.threshold
        if self.op == "<=":
            return value <= self.threshold
        return False

    def __str__(self) -> str:
        return f"{self.feature} {self.op} {self.threshold:.6g}"


@dataclass(frozen=True)
class SelectorEntry:
    symbol: str
    direction: str
    status: str
    rules: tuple[DynamicRule, ...]
    validation: dict[str, Any]
    baseline_validation: dict[str, Any]
    reason: str

    @property
    def key(self) -> tuple[str, str]:
        return self.symbol.upper(), self.direction.upper()

    @property
    def rules_text(self) -> str:
        return "; ".join(str(rule) for rule in self.rules) or "no extra filter"


@dataclass(frozen=True)
class SelectorDecision:
    status: str
    symbol: str
    direction: str
    rule_match: bool
    reason: str
    entry: SelectorEntry | None = None

    @property
    def is_block(self) -> bool:
        return self.status == STATUS_BLOCK

    @property
    def is_watchlist(self) -> bool:
        return self.status == STATUS_WATCHLIST

    @property
    def is_signal_only_candidate(self) -> bool:
        return self.status in {STATUS_TRADE_CANDIDATE, STATUS_TRADE_CANDIDATE_SIGNAL_ONLY}


def _metric(stats: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = float(stats.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _count(stats: dict[str, Any], key: str) -> int:
    try:
        return int(stats.get(key, 0))
    except (TypeError, ValueError):
        return 0


def classify_filter(item: dict[str, Any]) -> tuple[str, str]:
    symbol = str(item.get("symbol", "")).upper()
    direction = str(item.get("direction", "")).upper()
    validation = item.get("validation") or {}
    baseline_validation = item.get("baseline_validation") or {}

    val_wr = _metric(validation, "wr_ex_flat")
    val_nonflat = _count(validation, "nonflat")
    base_wr = _metric(baseline_validation, "wr_ex_flat")
    base_nonflat = _count(baseline_validation, "nonflat")

    if val_wr >= 0.90 and val_nonflat >= 30:
        return (
            STATUS_TRADE_CANDIDATE,
            f"validation WR ex-FLAT {val_wr:.2%} with nonflat={val_nonflat}",
        )

    if (
        symbol == "6CM6"
        and direction == "SELL"
        and base_wr >= 0.90
        and base_nonflat >= 30
        and val_wr >= 0.90
        and val_nonflat >= 5
    ):
        return (
            STATUS_TRADE_CANDIDATE_SIGNAL_ONLY,
            (
                f"baseline validation WR ex-FLAT {base_wr:.2%} with nonflat={base_nonflat}; "
                f"elite validation WR ex-FLAT {val_wr:.2%} with nonflat={val_nonflat}"
            ),
        )

    if val_wr >= 0.90 and 5 <= val_nonflat < 30:
        return (
            STATUS_WATCHLIST,
            f"validation WR ex-FLAT {val_wr:.2%} but nonflat={val_nonflat}<30",
        )

    return (
        STATUS_BLOCK,
        f"validation WR ex-FLAT {val_wr:.2%} with nonflat={val_nonflat}",
    )


def load_selector_entries(path: Path = PARAMS_PATH) -> dict[tuple[str, str], SelectorEntry]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    
    # Robustly handle both list and dict formats
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("filters", [])
    else:
        LOGGER.error("Dynamic selector path %s contains unknown format (not list or dict).", path)
        return {}

    entries: dict[tuple[str, str], SelectorEntry] = {}
    for item in items:
        symbol = str(item.get("symbol", "")).upper()
        direction = str(item.get("direction", "")).upper()
        if not symbol or not direction:
            continue
        status, reason = classify_filter(item)
        entry = SelectorEntry(
            symbol=symbol,
            direction=direction,
            status=status,
            rules=tuple(DynamicRule.from_dict(rule) for rule in item.get("rules", [])),
            validation=item.get("validation") or {},
            baseline_validation=item.get("baseline_validation") or {},
            reason=reason,
        )
        entries[entry.key] = entry
    return entries


def _flatten_features(
    tick: dict[str, Any],
    score: float,
    adjusted_score: float,
    framework_scores: dict[str, Any] | None,
    l3_features: dict[str, Any] | None,
    bias_breakdown: dict[str, Any] | None,
) -> dict[str, Any]:
    features: dict[str, Any] = {
        "score": score,
        "adjusted_score": adjusted_score,
        "spread_bps": tick.get("spread_bps"),
    }
    for key, value in (framework_scores or {}).items():
        features[f"fw.{key}"] = value
    for key, value in (l3_features or {}).items():
        features[f"l3.{key}"] = value
    for key, value in (bias_breakdown or {}).items():
        features[f"bias.{key}"] = value
    return features


class DynamicPairSelector:
    def __init__(self, path: Path = PARAMS_PATH) -> None:
        self.path = path
        self._mtime: float | None = None
        self._entries: dict[tuple[str, str], SelectorEntry] = {}
        self.reload(force=True)

    @property
    def entries(self) -> dict[tuple[str, str], SelectorEntry]:
        self.reload(force=False)
        return self._entries

    def reload(self, force: bool = False) -> None:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            mtime = None
        if not force and mtime == self._mtime:
            return
        self._entries = load_selector_entries(self.path)
        self._mtime = mtime

    def decide(
        self,
        symbol: str,
        direction: str,
        tick: dict[str, Any],
        score: float,
        adjusted_score: float,
        framework_scores: dict[str, Any] | None,
        l3_features: dict[str, Any] | None,
        bias_breakdown: dict[str, Any] | None,
    ) -> SelectorDecision:
        key = (symbol.upper(), direction.upper())
        entry = self.entries.get(key)
        if entry is None:
            return SelectorDecision(
                status=STATUS_BLOCK,
                symbol=key[0],
                direction=key[1],
                rule_match=False,
                reason="pair/direction has no dynamic validation filter",
            )

        features = _flatten_features(tick, score, adjusted_score, framework_scores, l3_features, bias_breakdown)
        rule_match = all(rule.passes(features) for rule in entry.rules)
        if not rule_match:
            return SelectorDecision(
                status=STATUS_BLOCK,
                symbol=key[0],
                direction=key[1],
                rule_match=False,
                reason=f"dynamic elite rules not matched: {entry.rules_text}",
                entry=entry,
            )

        return SelectorDecision(
            status=entry.status,
            symbol=key[0],
            direction=key[1],
            rule_match=True,
            reason=entry.reason,
            entry=entry,
        )


def classify_entries(path: Path = PARAMS_PATH) -> dict[str, list[SelectorEntry]]:
    grouped = {
        STATUS_TRADE_CANDIDATE: [],
        STATUS_TRADE_CANDIDATE_SIGNAL_ONLY: [],
        STATUS_WATCHLIST: [],
        STATUS_BLOCK: [],
    }
    for entry in load_selector_entries(path).values():
        grouped.setdefault(entry.status, []).append(entry)
    for values in grouped.values():
        values.sort(key=lambda e: (e.symbol, e.direction))
    return grouped
