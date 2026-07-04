"""Backtest analytics and reporting for OVERSEER v12.

Computes P&L, win rate, Sharpe ratio, max drawdown, per-framework
contribution, and outputs a text + HTML report.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from backtest.simulator import SimTrade

LOGGER = logging.getLogger("overseer.backtest.analytics")
RESULTS_DIR = Path(__file__).resolve().parent / "results"


class BacktestResult:
    """Container for all backtest statistics."""

    def __init__(self, trades: list[SimTrade], balance_history: list[float], tick_count: int, config: dict[str, Any]) -> None:
        self.trades = trades
        self.balance_history = balance_history
        self.tick_count = tick_count
        self.config = config
        self._compute()

    def _compute(self) -> None:
        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        self.total_trades = len(self.trades)
        self.wins = len(wins)
        self.losses = len(losses)
        self.win_rate = self.wins / self.total_trades if self.total_trades > 0 else 0.0

        self.total_pnl = sum(t.pnl for t in self.trades)
        self.avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
        self.avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0.0
        self.best_trade = max((t.pnl for t in self.trades), default=0.0)
        self.worst_trade = min((t.pnl for t in self.trades), default=0.0)

        self.avg_pnl_pips = sum(t.pnl_pips for t in self.trades) / self.total_trades if self.total_trades else 0.0
        self.avg_win_pips = sum(t.pnl_pips for t in wins) / len(wins) if wins else 0.0
        self.avg_loss_pips = sum(t.pnl_pips for t in losses) / len(losses) if losses else 0.0

        if self.balance_history:
            self.final_balance = self.balance_history[-1]
            self.max_drawdown = _max_drawdown(self.balance_history)
            self.max_drawdown_pct = self.max_drawdown / max(self.balance_history) * 100 if self.balance_history else 0.0
        else:
            self.final_balance = 0.0
            self.max_drawdown = 0.0
            self.max_drawdown_pct = 0.0

        self.sharpe_ratio = _sharpe(self.trades)
        self.profit_factor = _profit_factor(self.trades)
        self.expectancy = _expectancy(self.trades)

        self.exit_reasons: dict[str, int] = {}
        for t in self.trades:
            self.exit_reasons[t.exit_reason] = self.exit_reasons.get(t.exit_reason, 0) + 1

        self.direction_stats: dict[str, dict[str, Any]] = {}
        for direction in ("BUY", "SELL"):
            dir_trades = [t for t in self.trades if t.direction == direction]
            dir_wins = [t for t in dir_trades if t.pnl > 0]
            self.direction_stats[direction] = {
                "count": len(dir_trades),
                "wins": len(dir_wins),
                "win_rate": len(dir_wins) / len(dir_trades) if dir_trades else 0.0,
                "pnl": sum(t.pnl for t in dir_trades),
            }

    def summary(self) -> dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 4),
            "total_pnl": round(self.total_pnl, 2),
            "final_balance": round(self.final_balance, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "profit_factor": round(self.profit_factor, 4),
            "expectancy": round(self.expectancy, 4),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "best_trade": round(self.best_trade, 2),
            "worst_trade": round(self.worst_trade, 2),
            "avg_pnl_pips": round(self.avg_pnl_pips, 2),
            "exit_reasons": self.exit_reasons,
            "direction_stats": self.direction_stats,
            "tick_count": self.tick_count,
        }

    def text_report(self) -> str:
        s = self.summary()
        lines = [
            "=" * 60,
            "  OVERSEER v12 — BACKTEST REPORT",
            "=" * 60,
            f"  Ticks processed:   {s['tick_count']:,}",
            f"  Total trades:      {s['total_trades']}",
            f"  Win rate:          {s['win_rate']:.1%}",
            f"  Total P&L:         ${s['total_pnl']:.2f}",
            f"  Final balance:     ${s['final_balance']:.2f}",
            f"  Sharpe ratio:      {s['sharpe_ratio']:.4f}",
            f"  Profit factor:     {s['profit_factor']:.4f}",
            f"  Expectancy:        ${s['expectancy']:.4f}",
            f"  Max drawdown:      ${s['max_drawdown']:.2f} ({s['max_drawdown_pct']:.1f}%)",
            "",
            "  Averages:",
            f"    Avg win:         ${s['avg_win']:.2f}",
            f"    Avg loss:        ${s['avg_loss']:.2f}",
            f"    Best trade:      ${s['best_trade']:.2f}",
            f"    Worst trade:     ${s['worst_trade']:.2f}",
            f"    Avg pips/trade:  {s['avg_pnl_pips']:.2f}",
            "",
            "  Direction breakdown:",
        ]
        for d, stats in s["direction_stats"].items():
            lines.append(f"    {d}: {stats['count']} trades, {stats['win_rate']:.1%} WR, ${stats['pnl']:.2f} P&L")

        lines.append("")
        lines.append("  Exit reasons:")
        for reason, count in sorted(s["exit_reasons"].items()):
            lines.append(f"    {reason}: {count}")

        if self.trades:
            lines.append("")
            lines.append("  Last 10 trades:")
            for t in self.trades[-10:]:
                lines.append(
                    f"    #{t.ticket} {t.direction} {t.symbol} "
                    f"entry={t.entry_price:.5f} exit={t.exit_price:.5f} "
                    f"pnl=${t.pnl:.2f} ({t.pnl_pips:.1f}p) [{t.exit_reason}]"
                )

        lines.append("=" * 60)
        return "\n".join(lines)

    def save(self, filename: str | None = None) -> Path:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = filename or f"backtest_{ts}"
        json_path = RESULTS_DIR / f"{filename}.json"
        report_path = RESULTS_DIR / f"{filename}.txt"

        json_path.write_text(json.dumps(self.summary(), indent=2, default=str), encoding="utf-8")
        report_path.write_text(self.text_report(), encoding="utf-8")
        LOGGER.info("Results saved: %s, %s", json_path.name, report_path.name)
        return report_path


def _max_drawdown(balance: list[float]) -> float:
    if not balance:
        return 0.0
    peak = balance[0]
    max_dd = 0.0
    for b in balance:
        if b > peak:
            peak = b
        dd = peak - b
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _sharpe(trades: list[SimTrade], risk_free: float = 0.0) -> float:
    if len(trades) < 2:
        return 0.0
    returns = [t.pnl for t in trades]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std == 0:
        return 0.0
    return (mean - risk_free) / std * math.sqrt(252)


def _profit_factor(trades: list[SimTrade]) -> float:
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
    return gross_profit / gross_loss if gross_loss > 0 else 0.0


def _expectancy(trades: list[SimTrade]) -> float:
    if not trades:
        return 0.0
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    wr = len(wins) / len(trades)
    avg_w = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
    avg_l = abs(sum(t.pnl for t in losses) / len(losses)) if losses else 0.0
    return wr * avg_w - (1 - wr) * avg_l
