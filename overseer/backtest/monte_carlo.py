"""Monte Carlo simulation for OVERSEER backtest.

Takes the trade list from a backtest and reshuffles it (with replacement)
thousands of times to estimate the distribution of outcomes. This reveals
the range of possible P&L paths and the probability of drawdown/ruin
given the observed trade distribution.

Usage:
    python -m backtest.monte_carlo --data backtest/data/spot/DAT_ASCII_EURUSD_M1_2025.csv \
        --entry-mode rule --breakout-atr 1.5 --sl 8 --tp 36 \
        --simulations 10000 --risk-ruin-pct 10
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
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

LOGGER = logging.getLogger("overseer.backtest.monte_carlo")


def run_monte_carlo(
    trades: list[SimTrade],
    initial_balance: float = 10000.0,
    simulations: int = 10000,
    risk_ruin_pct: float = 10.0,
    seed: int = 42,
) -> dict[str, Any]:
    if not trades:
        return {"error": "no trades to simulate"}

    pnls = [t.pnl for t in trades]
    n_trades = len(pnls)

    rng = random.Random(seed)
    ruin_threshold = initial_balance * (risk_ruin_pct / 100.0)

    final_balances: list[float] = []
    max_drawdowns: list[float] = []
    ruin_count = 0

    for _ in range(simulations):
        balance = initial_balance
        peak = initial_balance
        max_dd = 0.0
        ruined = False

        shuffled = rng.choices(pnls, k=n_trades)

        for pnl in shuffled:
            balance += pnl
            if balance < ruin_threshold:
                ruined = True
                break
            if balance > peak:
                peak = balance
            dd = peak - balance
            if dd > max_dd:
                max_dd = dd

        final_balances.append(balance)
        max_drawdowns.append(max_dd)
        if ruined:
            ruin_count += 1

    final_balances.sort()
    max_drawdowns.sort()

    n = len(final_balances)
    def percentile(sorted_list: list[float], p: float) -> float:
        idx = int(p / 100.0 * (len(sorted_list) - 1))
        return sorted_list[min(idx, len(sorted_list) - 1)]

    return {
        "simulations": simulations,
        "original_trades": n_trades,
        "original_pnl": round(sum(pnls), 2),
        "original_wr": round(len([p for p in pnls if p > 0]) / n_trades, 4) if n_trades else 0,
        "avg_final_balance": round(sum(final_balances) / n, 2),
        "median_final_balance": round(percentile(final_balances, 50), 2),
        "p5_final_balance": round(percentile(final_balances, 5), 2),
        "p95_final_balance": round(percentile(final_balances, 95), 2),
        "p1_final_balance": round(percentile(final_balances, 1), 2),
        "p99_final_balance": round(percentile(final_balances, 99), 2),
        "worst_final_balance": round(final_balances[0], 2),
        "best_final_balance": round(final_balances[-1], 2),
        "avg_max_drawdown": round(sum(max_drawdowns) / n, 2),
        "median_max_drawdown": round(percentile(max_drawdowns, 50), 2),
        "p95_max_drawdown": round(percentile(max_drawdowns, 95), 2),
        "ruin_probability": round(ruin_count / n, 4),
        "ruin_threshold": round(ruin_threshold, 2),
        "profit_probability": round(len([b for b in final_balances if b > initial_balance]) / n, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OVERSEER Monte Carlo Simulation")
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
    parser.add_argument("--simulations", type=int, default=10000)
    parser.add_argument("--risk-ruin-pct", type=float, default=10.0, help="Ruin = balance below this %% of initial")
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

    config = {
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

    engine = BacktestEngine(config)
    result = engine.run(ticks)
    print(result.text_report())

    LOGGER.info("Running Monte Carlo: %d simulations, %d trades", args.simulations, result.total_trades)

    mc = run_monte_carlo(
        result.trades,
        initial_balance=args.balance,
        simulations=args.simulations,
        risk_ruin_pct=args.risk_ruin_pct,
    )

    print("\n" + "=" * 60)
    print(" MONTE CARLO SIMULATION RESULTS")
    print("=" * 60)
    print(f"  Simulations:          {mc['simulations']:,}")
    print(f"  Original trades:      {mc['original_trades']}")
    print(f"  Original P&L:         ${mc['original_pnl']:.2f}")
    print(f"  Original WR:          {mc['original_wr']:.1%}")
    print("")
    print(f"  Avg final balance:    ${mc['avg_final_balance']:.2f}")
    print(f"  Median final balance: ${mc['median_final_balance']:.2f}")
    print(f"  5th percentile:       ${mc['p5_final_balance']:.2f}")
    print(f"  95th percentile:      ${mc['p95_final_balance']:.2f}")
    print(f"  1st percentile:       ${mc['p1_final_balance']:.2f}")
    print(f"  99th percentile:      ${mc['p99_final_balance']:.2f}")
    print(f"  Worst case:           ${mc['worst_final_balance']:.2f}")
    print(f"  Best case:            ${mc['best_final_balance']:.2f}")
    print("")
    print(f"  Avg max drawdown:     ${mc['avg_max_drawdown']:.2f}")
    print(f"  Median max drawdown:  ${mc['median_max_drawdown']:.2f}")
    print(f"  95th pct drawdown:    ${mc['p95_max_drawdown']:.2f}")
    print("")
    print(f"  Profit probability:   {mc['profit_probability']:.1%}")
    print(f"  Ruin probability:     {mc['ruin_probability']:.2%} (threshold ${mc['ruin_threshold']:.2f})")
    print("=" * 60)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(mc, indent=2, default=str), encoding="utf-8")
        LOGGER.info("Results saved to %s", out_path)


if __name__ == "__main__":
    main()
