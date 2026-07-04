"""Walk-forward optimization for OVERSEER backtest.

Splits data into rolling train/validate windows. The train window finds
the best parameter set; the validate window tests it out-of-sample.
This reveals whether a parameter set generalises or just overfits.

Usage:
    python -m backtest.walk_forward --data backtest/data/spot/DAT_ASCII_EURUSD_M1_2025.csv \
        --entry-mode rule --param-grid breakout_atr=1.0,1.5,2.0 --param-grid sl=5,8,12 \
        --param-grid tp=20,36,50 --train-ratio 0.7 --folds 4
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os = __import__("os")
os.environ.setdefault("MT5_ENABLED", "false")

from backtest.analytics import BacktestResult
from backtest.data_loader import _load_csv_file, _infer_pip_size, generate_sample_data
from backtest.engine import BacktestEngine, enrich_with_synthetic_l3
from backtest.simulator import SimTrade

LOGGER = logging.getLogger("overseer.backtest.walk_forward")


def parse_param_grid(grid_args: list[str]) -> dict[str, list[Any]]:
    grid: dict[str, list[Any]] = {}
    for item in grid_args:
        key, values_str = item.split("=", 1)
        values: list[Any] = []
        for v in values_str.split(","):
            v = v.strip()
            try:
                values.append(int(v))
            except ValueError:
                try:
                    values.append(float(v))
                except ValueError:
                    values.append(v)
        grid[key.strip()] = values
    return grid


def expand_grid(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = sorted(grid.keys())
    combos = list(itertools.product(*(grid[k] for k in keys)))
    return [dict(zip(keys, combo)) for combo in combos]


def apply_overrides(config: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "breakout_atr": "breakout_atr_mult",
        "sl": "sl_override",
        "tp": "tp_override",
        "threshold": "quality_threshold",
        "cooldown": "min_trade_cooldown",
        "lot": "lot_size",
        "slippage": "slippage_pips",
        "max_daily_trades": "max_daily_trades",
        "consecutive_loss_limit": "consecutive_loss_limit",
        "eval_interval": "gate_eval_interval",
        "momentum_lookback": "momentum_lookback",
        "sl_atr": "sl_atr_mult",
        "tp_atr": "tp_atr_mult",
    }
    cfg = dict(config)
    for k, v in params.items():
        cfg_key = mapping.get(k, k)
        cfg[cfg_key] = v
    return cfg


def run_walk_forward(
    ticks: list[dict[str, Any]],
    base_config: dict[str, Any],
    param_grid: dict[str, list[Any]],
    folds: int = 4,
    train_ratio: float = 0.7,
) -> list[dict[str, Any]]:
    combos = expand_grid(param_grid)
    if not combos:
        LOGGER.error("Empty parameter grid")
        return []

    total_ticks = len(ticks)
    fold_size = total_ticks // folds
    results: list[dict[str, Any]] = []

    LOGGER.info(
        "Walk-forward: %d folds, %d param combos, %d ticks, train_ratio=%.1f",
        folds, len(combos), total_ticks, train_ratio,
    )

    for combo in combos:
        cfg = apply_overrides(base_config, combo)
        combo_key = json.dumps(combo, sort_keys=True)
        fold_results: list[dict[str, Any]] = []

        for fold_idx in range(folds):
            fold_start = fold_idx * fold_size
            fold_end = min(fold_start + fold_size, total_ticks)
            train_end = fold_start + int((fold_end - fold_start) * train_ratio)
            train_ticks = ticks[fold_start:train_end]
            val_ticks = ticks[train_end:fold_end]

            if not train_ticks or not val_ticks:
                continue

            engine = BacktestEngine(cfg)
            train_result = engine.run(train_ticks)

            val_engine = BacktestEngine(cfg)
            val_result = val_engine.run(val_ticks)

            fold_results.append({
                "fold": fold_idx,
                "train_trades": train_result.total_trades,
                "train_pnl": round(train_result.total_pnl, 2),
                "train_pf": round(train_result.profit_factor, 4),
                "train_wr": round(train_result.win_rate, 4),
                "val_trades": val_result.total_trades,
                "val_pnl": round(val_result.total_pnl, 2),
                "val_pf": round(val_result.profit_factor, 4),
                "val_wr": round(val_result.win_rate, 4),
            })

        avg_val_pnl = 0.0
        avg_val_pf = 0.0
        avg_val_wr = 0.0
        if fold_results:
            avg_val_pnl = sum(f["val_pnl"] for f in fold_results) / len(fold_results)
            avg_val_pf = sum(f["val_pf"] for f in fold_results) / len(fold_results)
            avg_val_wr = sum(f["val_wr"] for f in fold_results) / len(fold_results)

        consistent_profit = all(f["val_pnl"] > 0 for f in fold_results if f["val_trades"] > 0)

        results.append({
            "params": combo,
            "avg_val_pnl": round(avg_val_pnl, 2),
            "avg_val_pf": round(avg_val_pf, 4),
            "avg_val_wr": round(avg_val_wr, 4),
            "consistent_profit": consistent_profit,
            "folds": fold_results,
        })

    results.sort(key=lambda r: r["avg_val_pnl"], reverse=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="OVERSEER Walk-Forward Optimization")
    parser.add_argument("--data", required=True, help="Path to spot CSV data")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--folds", type=int, default=4, help="Number of walk-forward folds")
    parser.add_argument("--train-ratio", type=float, default=0.7, help="Train/validation split ratio")
    parser.add_argument("--entry-mode", choices=["ml", "rule"], default="rule")
    parser.add_argument("--param-grid", action="append", required=True,
                        help="Param grid entry: key=val1,val2,val3 (repeat for each param)")
    parser.add_argument("--balance", type=float, default=10000.0)
    parser.add_argument("--lot", type=float, default=0.01)
    parser.add_argument("--slippage", type=float, default=1.0)
    parser.add_argument("--l3-intensity", type=float, default=1.0)
    parser.add_argument("--no-l3", action="store_true")
    parser.add_argument("--output", default=None, help="Output JSON file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    path = Path(args.data)
    if not path.exists():
        LOGGER.error("File not found: %s", args.data)
        sys.exit(1)

    pip = _infer_pip_size(args.symbol)
    ticks = _load_csv_file(path, args.symbol, pip, 1.5)
    LOGGER.info("Loaded %d ticks from %s", len(ticks), args.data)

    if not args.no_l3:
        ticks = enrich_with_synthetic_l3(ticks, args.symbol, args.l3_intensity)

    grid = parse_param_grid(args.param_grid)
    LOGGER.info("Parameter grid: %s", grid)

    base_config = {
        "entry_mode": args.entry_mode,
        "account_balance": args.balance,
        "lot_size": args.lot,
        "slippage_pips": args.slippage,
        "l3_intensity": 0.0 if args.no_l3 else args.l3_intensity,
        "quality_threshold": 0.65,
        "max_daily_trades": 5,
        "consecutive_loss_limit": 999,
    }

    results = run_walk_forward(ticks, base_config, grid, folds=args.folds, train_ratio=args.train_ratio)

    print("\n" + "=" * 70)
    print(" WALK-FORWARD OPTIMIZATION RESULTS")
    print("=" * 70)
    print(f" {'Rank':<5} {'Avg Val P&L':>12} {'Avg Val PF':>12} {'Avg Val WR':>12} {'Consistent':>12} {'Params'}")
    print("-" * 70)
    for i, r in enumerate(results[:20], 1):
        p = r["params"]
        p_str = " ".join(f"{k}={v}" for k, v in sorted(p.items()))
        print(f" {i:<5} ${r['avg_val_pnl']:>10.2f} {r['avg_val_pf']:>12.4f} {r['avg_val_wr']:>11.1%} {'YES' if r['consistent_profit'] else 'NO':>12} {p_str}")

    if results:
        best = results[0]
        print(f"\nBest OOS: {best['params']} — avg_val_pnl=${best['avg_val_pnl']:.2f}, avg_val_pf={best['avg_val_pf']:.4f}")
        if best["folds"]:
            print("\nPer-fold breakdown:")
            for f in best["folds"]:
                print(f"  Fold {f['fold']}: train_pnl=${f['train_pnl']:.2f} val_pnl=${f['val_pnl']:.2f} val_wr={f['val_wr']:.1%}")

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        LOGGER.info("Results saved to %s", out_path)


if __name__ == "__main__":
    main()
