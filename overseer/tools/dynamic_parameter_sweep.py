"""Dynamic parameter sweep for OVERSEER signal_log.

Finds per-symbol/direction filters from real signal outcomes using a
time-ordered train/validation split. This is for research and signal-only
calibration; do not treat in-sample 90% pockets as live guarantees.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.dynamic_pair_selector import (
    STATUS_BLOCK,
    STATUS_TRADE_CANDIDATE,
    STATUS_TRADE_CANDIDATE_SIGNAL_ONLY,
    STATUS_WATCHLIST,
    classify_filter,
)


DB_PATH = Path("database/overseer_trades.db")
REPORT_PATH = Path("reports/dynamic_parameter_sweep.md")
JSON_PATH = Path("config/dynamic_elite_params.json")


CORE_FEATURES = ["score", "adjusted_score", "spread_bps"]
FRAMEWORK_FEATURES = [
    "FW01_multi_tf_trend",
    "FW02_price_action",
    "FW03_volume",
    "FW04_liquidity_sweep",
    "FW05_weekly_levels",
    "FW06_session_kz",
    "FW07_econ_event",
    "FW08_asian_range",
    "FW09_cot_positioning",
    "FW10_post_news",
    "FW11_iv_skew",
    "FW12_dxy_isolation",
    "FW13_lag_arb",
    "FW14_risk_regime",
    "FW15_l3_flow",
    "FW16_directional_momentum",
    "FW17_volume_profile",
    "FW18_technical",
    "FW19_fundamental",
]
L3_FEATURES = [
    "l3_prediction",
    "l3_confidence",
    "l3_ready",
    "adverse_risk",
    "adverse_selection_ratio",
    "hft_signal",
    "hft_synchronized_volume",
    "iceberg_signal",
    "iceberg_hidden_depth",
    "queue_position_ratio",
    "queue_signal",
    "spoof_signal",
    "vacuum_signal",
]
BIAS_FEATURES = [
    "clamped_bias",
    "raw_bias",
    "l3_bias",
    "fundamental_bias",
    "adverse_bias",
    "hft_bias",
    "queue_bias",
    "spoof_bias",
    "vacuum_bias",
]


@dataclass(frozen=True)
class Rule:
    feature: str
    op: str
    threshold: float

    def passes(self, rec: dict[str, Any]) -> bool:
        value = rec.get(self.feature)
        if value is None:
            return False
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(value):
            return False
        if self.op == ">=":
            return value >= self.threshold
        return value <= self.threshold

    def as_dict(self) -> dict[str, Any]:
        return {"feature": self.feature, "op": self.op, "threshold": round(self.threshold, 6)}

    def __str__(self) -> str:
        return f"{self.feature} {self.op} {self.threshold:.6g}"


def _loads(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def load_records(db_path: Path, valid_spread_only: bool = True, min_id: int = 0) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, symbol, direction, score, adjusted_score, spread_bps, session,
               risk_regime, framework_scores_json, l3_features_json,
               bias_breakdown_json, outcome_200ticks, timestamp
        FROM signal_log
        WHERE outcome_200ticks IN ('WIN', 'LOSS', 'FLAT')
          AND id >= ?
        ORDER BY id
        """
        ,
        (min_id,),
    ).fetchall()
    conn.close()

    records: list[dict[str, Any]] = []
    for row in rows:
        rec: dict[str, Any] = {
            "id": int(row["id"]),
            "symbol": row["symbol"],
            "direction": row["direction"],
            "score": _float(row["score"]),
            "adjusted_score": _float(row["adjusted_score"]),
            "spread_bps": _float(row["spread_bps"]),
            "session": row["session"] or "",
            "risk_regime": row["risk_regime"] or "",
            "outcome": row["outcome_200ticks"],
            "timestamp": row["timestamp"],
        }
        fw = _loads(row["framework_scores_json"])
        l3 = _loads(row["l3_features_json"])
        bias = _loads(row["bias_breakdown_json"])
        for key in FRAMEWORK_FEATURES:
            rec[f"fw.{key}"] = _float(fw.get(key))
        for key in L3_FEATURES:
            rec[f"l3.{key}"] = _float(l3.get(key))
        for key in BIAS_FEATURES:
            rec[f"bias.{key}"] = _float(bias.get(key))
        if valid_spread_only and rec["spread_bps"] < 0:
            continue
        records.append(rec)
    return records


def metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for r in records if r["outcome"] == "WIN")
    losses = sum(1 for r in records if r["outcome"] == "LOSS")
    flats = sum(1 for r in records if r["outcome"] == "FLAT")
    nonflat = wins + losses
    return {
        "total": len(records),
        "nonflat": nonflat,
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "wr_ex_flat": wins / nonflat if nonflat else 0.0,
        "wr_all": wins / len(records) if records else 0.0,
    }


def apply_rules(records: list[dict[str, Any]], rules: tuple[Rule, ...]) -> list[dict[str, Any]]:
    if not rules:
        return records
    return [r for r in records if all(rule.passes(r) for rule in rules)]


def quantiles(values: list[float]) -> list[float]:
    if not values:
        return []
    vals = sorted(v for v in values if math.isfinite(v))
    if not vals:
        return []
    qs = [0.05, 0.10, 0.20, 0.25, 0.33, 0.50, 0.67, 0.75, 0.80, 0.90, 0.95]
    out = [vals[min(len(vals) - 1, max(0, int((len(vals) - 1) * q)))] for q in qs]
    out.extend([0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0])
    return sorted(set(round(v, 6) for v in out))


def score_candidate(train_m: dict[str, Any], val_m: dict[str, Any]) -> float:
    """Prefer high validation WR, enough samples, and low overfit gap."""
    sample_bonus = min(0.08, math.log1p(val_m["nonflat"]) / 100.0)
    flat_penalty = 0.0
    if val_m["total"]:
        flat_penalty = min(0.08, (val_m["flats"] / val_m["total"]) * 0.08)
    overfit_gap = max(0.0, train_m["wr_ex_flat"] - val_m["wr_ex_flat"])
    return val_m["wr_ex_flat"] + sample_bonus - flat_penalty - overfit_gap * 0.25


def optimize_group(
    records: list[dict[str, Any]],
    train_fraction: float,
    min_train_nonflat: int,
    min_val_nonflat: int,
    max_rules: int,
) -> dict[str, Any] | None:
    if not records:
        return None
    split = max(1, int(len(records) * train_fraction))
    train = records[:split]
    val = records[split:]
    if metrics(train)["nonflat"] < min_train_nonflat or metrics(val)["nonflat"] < min_val_nonflat:
        return None

    feature_names = (
        CORE_FEATURES
        + [f"fw.{x}" for x in FRAMEWORK_FEATURES]
        + [f"l3.{x}" for x in L3_FEATURES]
        + [f"bias.{x}" for x in BIAS_FEATURES]
    )

    single: list[tuple[float, tuple[Rule, ...], dict[str, Any], dict[str, Any]]] = []
    base_train_m = metrics(train)
    base_val_m = metrics(val)
    single.append((score_candidate(base_train_m, base_val_m), tuple(), base_train_m, base_val_m))

    for feature in feature_names:
        thresholds = quantiles([_float(r.get(feature), float("nan")) for r in train])
        for threshold in thresholds:
            for op in (">=", "<="):
                rules = (Rule(feature, op, threshold),)
                train_sub = apply_rules(train, rules)
                val_sub = apply_rules(val, rules)
                train_m = metrics(train_sub)
                val_m = metrics(val_sub)
                if train_m["nonflat"] >= min_train_nonflat and val_m["nonflat"] >= min_val_nonflat:
                    single.append((score_candidate(train_m, val_m), rules, train_m, val_m))

    single = sorted(single, key=lambda x: (x[0], x[3]["wr_ex_flat"], x[3]["nonflat"]), reverse=True)
    pool = single[:40]
    candidates = single[:]

    if max_rules >= 2:
        for _, rules_a, _, _ in pool:
            for _, rules_b, _, _ in pool:
                merged = tuple(dict.fromkeys([*rules_a, *rules_b]))
                if not merged or len(merged) > max_rules:
                    continue
                train_sub = apply_rules(train, merged)
                val_sub = apply_rules(val, merged)
                train_m = metrics(train_sub)
                val_m = metrics(val_sub)
                if train_m["nonflat"] >= min_train_nonflat and val_m["nonflat"] >= min_val_nonflat:
                    candidates.append((score_candidate(train_m, val_m), merged, train_m, val_m))

    if max_rules >= 3:
        pool2 = sorted(candidates, key=lambda x: x[0], reverse=True)[:25]
        for _, rules_a, _, _ in pool2:
            for _, rules_b, _, _ in pool:
                merged = tuple(dict.fromkeys([*rules_a, *rules_b]))
                if not merged or len(merged) > max_rules:
                    continue
                train_sub = apply_rules(train, merged)
                val_sub = apply_rules(val, merged)
                train_m = metrics(train_sub)
                val_m = metrics(val_sub)
                if train_m["nonflat"] >= min_train_nonflat and val_m["nonflat"] >= min_val_nonflat:
                    candidates.append((score_candidate(train_m, val_m), merged, train_m, val_m))

    candidates = sorted(
        candidates,
        key=lambda x: (x[0], x[3]["wr_ex_flat"], x[3]["nonflat"], x[2]["wr_ex_flat"]),
        reverse=True,
    )
    best = candidates[0]
    return {
        "score": best[0],
        "rules": best[1],
        "train": best[2],
        "validation": best[3],
        "baseline_train": base_train_m,
        "baseline_validation": base_val_m,
    }


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def make_report(results: list[dict[str, Any]], records: list[dict[str, Any]]) -> str:
    overall = metrics(records)
    lines = [
        "# Dynamic Parameter Sweep",
        "",
        "This report uses a time-ordered train/validation split from `signal_log`.",
        "It is a research filter report, not a live-trading guarantee.",
        "",
        "## Overall Signal Journal",
        "",
        f"- Total labeled signals: {overall['total']}",
        f"- Non-flat outcomes: {overall['nonflat']}",
        f"- WIN/LOSS/FLAT: {overall['wins']}/{overall['losses']}/{overall['flats']}",
        f"- WR excluding FLAT: {pct(overall['wr_ex_flat'])}",
        f"- WR including FLAT: {pct(overall['wr_all'])}",
        "",
        "## Best Dynamic Filters By Symbol/Direction",
        "",
        "| Symbol | Direction | Val WR ex-FLAT | Val W/L/F | Val total | Train WR ex-FLAT | Rules |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for result in results:
        rules = "; ".join(str(r) for r in result["rules"]) or "no extra filter"
        val = result["validation"]
        train = result["train"]
        lines.append(
            f"| {result['symbol']} | {result['direction']} | {pct(val['wr_ex_flat'])} | "
            f"{val['wins']}/{val['losses']}/{val['flats']} | {val['total']} | "
            f"{pct(train['wr_ex_flat'])} | `{rules}` |"
        )

    lines.extend(
        [
            "",
            "## Dynamic 90% Selector Classification",
            "",
            "Runtime policy: all classifications are signal-only. Live execution remains disabled; promotion requires fresh forward validation.",
            "",
            "| Status | Symbol | Direction | Val WR ex-FLAT | Val W/L/F | Baseline Val W/L/F | Rules | Reason |",
            "|---|---|---:|---:|---:|---:|---|---|",
        ]
    )
    status_order = {
        STATUS_TRADE_CANDIDATE: 0,
        STATUS_TRADE_CANDIDATE_SIGNAL_ONLY: 1,
        STATUS_WATCHLIST: 2,
        STATUS_BLOCK: 3,
    }
    classified = []
    for result in results:
        status, reason = classify_filter(result)
        classified.append((status_order.get(status, 99), status, reason, result))
    for _, status, reason, result in sorted(classified, key=lambda x: (x[0], x[3]["symbol"], x[3]["direction"])):
        rules = "; ".join(str(r) for r in result["rules"]) or "no extra filter"
        val = result["validation"]
        base_val = result["baseline_validation"]
        lines.append(
            f"| {status} | {result['symbol']} | {result['direction']} | {pct(val['wr_ex_flat'])} | "
            f"{val['wins']}/{val['losses']}/{val['flats']} | "
            f"{base_val['wins']}/{base_val['losses']}/{base_val['flats']} | `{rules}` | {reason} |"
        )

    lines.extend(
        [
            "",
            "## Recommended Use",
            "",
            "1. Keep `AUTO_EXECUTE=false` while testing these parameters.",
            "2. Only promote filters that stay strong on fresh forward data.",
            "3. Prefer filters with at least 30 validation non-flat outcomes.",
            "4. If validation WR is high but total count is tiny, treat it as fragile.",
            "5. Do not use raw model score alone; current live data shows score drift.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Find dynamic high-WR filters from signal_log.")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--min-train-nonflat", type=int, default=30)
    parser.add_argument("--min-val-nonflat", type=int, default=10)
    parser.add_argument("--max-rules", type=int, default=3)
    parser.add_argument("--report", default=str(REPORT_PATH))
    parser.add_argument("--json", default=str(JSON_PATH))
    parser.add_argument("--min-id", type=int, default=0, help="Only use signal_log rows with id >= this value.")
    parser.add_argument(
        "--allow-negative-spread",
        action="store_true",
        help="Include legacy rows with negative spread_bps. Not recommended after DOM normalization fix.",
    )
    args = parser.parse_args()

    records = load_records(Path(args.db), valid_spread_only=not args.allow_negative_spread, min_id=args.min_id)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rec in records:
        groups.setdefault((rec["symbol"], rec["direction"]), []).append(rec)

    results: list[dict[str, Any]] = []
    for (symbol, direction), group in sorted(groups.items()):
        result = optimize_group(
            group,
            train_fraction=args.train_fraction,
            min_train_nonflat=args.min_train_nonflat,
            min_val_nonflat=args.min_val_nonflat,
            max_rules=args.max_rules,
        )
        if result is None:
            continue
        result["symbol"] = symbol
        result["direction"] = direction
        results.append(result)

    results.sort(
        key=lambda r: (
            r["validation"]["wr_ex_flat"],
            r["validation"]["nonflat"],
            r["train"]["wr_ex_flat"],
        ),
        reverse=True,
    )

    report_path = Path(args.report)
    json_path = Path(args.json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    report_path.write_text(make_report(results, records), encoding="utf-8")
    json_payload = {
        "train_fraction": args.train_fraction,
        "min_train_nonflat": args.min_train_nonflat,
        "min_val_nonflat": args.min_val_nonflat,
        "max_rules": args.max_rules,
        "filters": [
            {
                "symbol": r["symbol"],
                "direction": r["direction"],
                "rules": [rule.as_dict() for rule in r["rules"]],
                "train": r["train"],
                "validation": r["validation"],
                "baseline_train": r["baseline_train"],
                "baseline_validation": r["baseline_validation"],
            }
            for r in results
        ],
    }
    json_path.write_text(json.dumps(json_payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote {report_path}")
    print(f"Wrote {json_path}")
    print()
    for r in results[:12]:
        val = r["validation"]
        rules = "; ".join(str(rule) for rule in r["rules"]) or "no extra filter"
        print(
            f"{r['symbol']} {r['direction']}: "
            f"val WR={pct(val['wr_ex_flat'])} W/L/F={val['wins']}/{val['losses']}/{val['flats']} "
            f"rules={rules}"
        )


if __name__ == "__main__":
    main()
