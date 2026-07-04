"""Parameter sensitivity analysis for OVERSEER backtest.

Sweeps one parameter at a time while holding others constant, showing
how each parameter affects P&L, win rate, profit factor, and drawdown.

Usage:
    python -m backtest.sensitivity --data backtest/data/spot/DAT_ASCII_EURUSD_M1_2025.csv \
        --entry-mode rule --sweep breakout_atr=0.5,0.75,1.0,1.25,1.5,2.0,2.5,3.0 \
        --sweep sl=4,5,6,8,10,12,15,20 --sweep tp=15,20,25,30,36,40,50,60
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os as _os
_os.environ.setdefault("MT5_ENABLED", "false")

from backtest.data_loader import _load_csv_file, _infer_pip_size
from backtest.engine import BacktestEngine, enrich_with_synthetic_l3
from backtest.simulator import SimTrade

LOGGER = logging.getLogger("overseer.backtest.sensitivity")

PARAM_MAPPING = {
    "breakout_atr": "breakout_atr_mult",
    "sl": "sl_override",
    "tp": "tp_override",
    "threshold": "quality_threshold",
    "cooldown": "min_trade_cooldown",
    "lot": "lot_size",
    "slippage": "slippage_pips",
    "max_daily_trades": "max_daily_trades",
    "consecutive_loss_limit": "consecutive_loss_limit",
    "momentum_lookback": "momentum_lookback",
    "sl_atr": "sl_atr_mult",
    "tp_atr": "tp_atr_mult",
    "entry_mode": "entry_mode",
}


def parse_sweep_args(sweep_args: list[str]) -> list[tuple[str, list[Any]]]:
    sweeps: list[tuple[str, list[Any]]] = []
    for item in sweep_args:
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
        sweeps.append((key.strip(), values))
    return sweeps


def run_sensitivity(
    ticks: list[dict[str, Any]],
    base_config: dict[str, Any],
    sweeps: list[tuple[str, list[Any]]],
) -> dict[str, list[dict[str, Any]]]:
    results: dict[str, list[dict[str, Any]]] = {}

    for param_name, values in sweeps:
        cfg_key = PARAM_MAPPING.get(param_name, param_name)
        param_results: list[dict[str, Any]] = []

        LOGGER.info("Sweeping %s (%s): %s", param_name, cfg_key, values)

        for val in values:
            cfg = dict(base_config)
            cfg[cfg_key] = val

            engine = BacktestEngine(cfg)
            result = engine.run(ticks)

            param_results.append({
                "value": val,
                "total_trades": result.total_trades,
                "win_rate": round(result.win_rate, 4),
                "total_pnl": round(result.total_pnl, 2),
                "profit_factor": round(result.profit_factor, 4),
                "max_drawdown": round(result.max_drawdown, 2),
                "max_drawdown_pct": round(result.max_drawdown_pct, 2),
                "sharpe_ratio": round(result.sharpe_ratio, 4),
                "avg_win": round(result.avg_win, 2),
                "avg_loss": round(result.avg_loss, 2),
                "avg_pnl_pips": round(result.avg_pnl_pips, 2),
            })

        results[param_name] = param_results

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="OVERSEER Parameter Sensitivity Analysis")
    parser.add_argument("--data", required=True, help="Path to spot CSV data")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--entry-mode", choices=["ml", "rule"], default="rule")
    parser.add_argument("--breakout-atr", type=float, default=1.5)
    parser.add_argument("--sl", type=float, default=8)
    parser.add_argument("--tp", type=float, default=36)
    parser.add_argument("--cooldown", type=int, default=100)
    parser.add_argument("--max-daily-trades", type=int, default=5)
    parser.add_argument("--consecutive-loss-limit", type=int, default=999)
    parser.add_argument("--balance", type=float, default=10000.0)
    parser.add_argument("--lot", type=float, default=0.01)
    parser.add_argument("--slippage", type=float, default=1.0)
    parser.add_argument("--l3-intensity", type=float, default=1.0)
    parser.add_argument("--no-l3", action="store_true")
    parser.add_argument("--sweep", action="append", required=True,
                        help="Parameter sweep: key=val1,val2,val3 (repeat for each param)")
    parser.add_argument("--output", default=None)
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

    base_config = {
        "entry_mode": args.entry_mode,
        "account_balance": args.balance,
        "lot_size": args.lot,
        "slippage_pips": args.slippage,
        "sl_override": args.sl,
        "tp_override": args.tp,
        "min_trade_cooldown": args.cooldown,
        "max_daily_trades": args.max_daily_trades,
        "consecutive_loss_limit": args.consecutive_loss_limit,
        "breakout_atr_mult": args.breakout_atr,
        "l3_intensity": 0.0 if args.no_l3 else args.l3_intensity,
        "quality_threshold": 0.65,
    }

    sweeps = parse_sweep_args(args.sweep)
    results = run_sensitivity(ticks, base_config, sweeps)

    for param_name, param_results in results.items():
        print("\n" + "=" * 90)
        print(f" SENSITIVITY: {param_name}")
        print("=" * 90)
        print(f" {'Value':>10} {'Trades':>7} {'WR':>8} {'P&L':>10} {'PF':>8} {'Sharpe':>8} {'MaxDD%':>8} {'AvgPips':>8}")
        print("-" * 90)
        for r in param_results:
            print(
                f" {r['value']:>10} {r['total_trades']:>7} {r['win_rate']:>7.1%} "
                f"${r['total_pnl']:>8.2f} {r['profit_factor']:>8.4f} {r['sharpe_ratio']:>8.4f} "
                f"{r['max_drawdown_pct']:>7.1f}% {r['avg_pnl_pips']:>7.2f}"
            )

        best = max(param_results, key=lambda r: r["total_pnl"])
        worst = min(param_results, key=lambda r: r["total_pnl"])
        print(f"\n  Best:  {param_name}={best['value']} -> P&L=${best['total_pnl']:.2f}, WR={best['win_rate']:.1%}, PF={best['profit_factor']:.4f}")
        print(f"  Worst: {param_name}={worst['value']} -> P&L=${worst['total_pnl']:.2f}, WR={worst['win_rate']:.1%}, PF={worst['profit_factor']:.4f}")

        pnl_range = best["total_pnl"] - worst["total_pnl"]
        print(f"  P&L sensitivity: ${pnl_range:.2f} across range")

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        LOGGER.info("Results saved to %s", out_path)


if __name__ == "__main__":
    main()
