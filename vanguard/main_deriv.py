"""
VANGUARD — 5-Minute Binary Direction Engine (90% Win Rate)
Auto-execution on Deriv via WebSocket using CME Level 3 data

Usage:
    python main_deriv.py
"""

import asyncio
import websockets
from websockets.exceptions import ConnectionClosed
from rich.console import Console
from rich.panel import Panel

from data.cme_feed import CMELevel3Feed
from data.models import Candle
from vanguard_signal.aggregator_90 import generate_signal_90
from execution.deriv_bridge import DerivBridge
from risk.manager import RiskManager
from utils.logger import get_logger, TradeLogger
from config import (
    ASSET,
    CANDLE_INTERVAL_SECONDS,
    DEMO_MODE,
    MIN_CANDLES_FOR_SIGNAL,
    MIN_SIGNAL_CONFIDENCE,
    USE_DERIV,
)

log     = get_logger("VANGUARD")
console = Console()


async def main():
    if not USE_DERIV:
        console.print("[yellow]Deriv API token not configured. Running signal-only mode.[/yellow]")
        console.print("[yellow]Add a valid DERIV_API_TOKEN to .env to enable auto-execution.[/yellow]")

    console.print(Panel.fit(
        "[bold cyan]VANGUARD v2.0 - Strict Binary Direction Engine[/bold cyan]\n"
        "15-Minute Candle/Expiry with High-Quality Filter Stack\n"
        f"Asset: [yellow]{ASSET}[/yellow] | "
        f"Mode: [{'green' if DEMO_MODE else 'red'}]{'DEMO' if DEMO_MODE else '⚠ LIVE'}[/]",
        border_style="cyan"
    ))

    bridge    = DerivBridge() if USE_DERIV else None
    risk      = RiskManager()
    db        = TradeLogger()

    while True:
        try:
            if bridge:
                await bridge.connect()

            active_signal_id = None

            async def on_candle(candle: Candle, history):
                nonlocal active_signal_id
                
                current_asset = candle.asset

                if len(history) < MIN_CANDLES_FOR_SIGNAL:
                    log.debug(f"[{current_asset}] Building history... {len(history)}/{MIN_CANDLES_FOR_SIGNAL}")
                    return

                signal      = generate_signal_90(history, current_asset)
                signal_id   = db.log_signal(signal)

                if signal.direction is None:
                    log.debug(f"[{current_asset}] No trade: {signal.reason}")
                    return

                if signal.confidence < MIN_SIGNAL_CONFIDENCE:
                    log.info(
                        f"[{current_asset}] Trade blocked: quality score "
                        f"{signal.confidence:.1%} < {MIN_SIGNAL_CONFIDENCE:.1%}"
                    )
                    return

                allowed, reason = risk.can_trade()
                if not allowed:
                    log.warning(f"[{current_asset}] ⛔ Trade blocked by risk manager: {reason}")
                    return

                # Override the signal asset just in case
                signal.asset = current_asset
                if not bridge:
                    log.info(f"[{current_asset}] SIGNAL ONLY: {signal.direction} | {signal.reason}")
                    return

                record = await bridge.place_trade(signal)
                if record:
                    active_signal_id = signal_id
                    db.log_trade(record, signal_id)

            feed = CMELevel3Feed(
                interval=CANDLE_INTERVAL_SECONDS,
                on_candle=on_candle,
            )
            await feed.connect()
            await feed.fetch_history(count=100)

            async def result_loop():
                if not bridge:
                    while True:
                        await asyncio.sleep(3600)

                async for trade_result in bridge.listen_results():
                    risk.record_trade(trade_result)
                    if active_signal_id:
                        db.log_trade(trade_result, active_signal_id)
                    stats = risk.stats
                    console.print(
                        f"📊 Today: {stats['trades']} trades | "
                        f"Win Rate: {stats['win_rate']:.0%} | "
                        f"P&L: ${stats['pnl']:+.2f}"
                    )

            await asyncio.gather(
                feed.stream(),
                result_loop()
            )

        except ConnectionClosed:
            log.warning("WebSocket dropped — reconnecting...")
            await asyncio.sleep(2)
        except Exception as e:
            log.error(f"Error in main loop: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]VANGUARD stopped.[/yellow]")
