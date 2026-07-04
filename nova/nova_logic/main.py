import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import logging
from pathlib import Path

from event_whitelist import EventWhitelist, NewsEvent
from directional_bias import DirectionalBiasModel
from l3_gate import L3GateDetector
from config import (
    ENTRY_DELAY_SEC,
    MIN_CONFIDENCE_SCORE,
    CONFLUENCE_POINTS,
    LOG_FILE,
    LOG_LEVEL,
    USE_DEMO_MODE,
    STAKE_USD,
    TRADE_DURATION,
    ASSET,
)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("NOVA")

class NOVASignalEngine:
    """
    Main NOVA signal engine
    Orchestrates all 3 gates and triggers T+90s entry
    """

    def __init__(self):
        self.event_whitelist = EventWhitelist()
        self.bias_model = DirectionalBiasModel()
        self.l3_detector = L3GateDetector()
        self.monitoring = False
        self.current_event: Optional[NewsEvent] = None
        self.gate_scores = {
            "event_impact": 0,
            "directional_bias": 0,
            "book_thinning": 0,
            "anchor_survival": 0,
        }
        self.total_score = 0
        self.direction = "NEUTRAL"
        self.trade_triggered = False

    async def start(self):
        """Start NOVA engine"""
        log.info("=== NOVA Signal Engine Starting ===")
        log.info(f"Target Asset: {ASSET}")
        log.info(f"Trade Duration: {TRADE_DURATION}s")
        log.info(f"Entry Delay: T+{ENTRY_DELAY_SEC}s")
        log.info(f"Mode: {'DEMO' if USE_DEMO_MODE else 'LIVE'}")

        await self.l3_detector.connect()
        self.monitoring = True

        asyncio.create_task(self._monitor_calendar_loop())

    async def _monitor_calendar_loop(self):
        """
        Continuously monitors economic calendar for upcoming events
        """
        while self.monitoring:
            try:
                events = self.event_whitelist.get_tradeable_events(minutes_ahead=30)

                if events:
                    log.info(f"Found {len(events)} tradeable events in next 30 minutes")

                    for event in events:
                        if not self.monitoring:
                            break

                        await self._process_event(event)

                await asyncio.sleep(60)
            except Exception as e:
                log.error(f"Calendar monitor error: {e}")
                await asyncio.sleep(60)

    async def _process_event(self, event: NewsEvent):
        """
        Processes single news event through all gates
        """
        log.info(f"\n{'='*60}")
        log.info(f"Processing Event: {event.name}")
        log.info(f"Currency: {event.currency} | Impact: {event.impact}")
        log.info(f"Time: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        log.info(f"{'='*60}\n")

        self.current_event = event
        self._reset_gates()

        now = datetime.now()
        time_to_event = (event.timestamp - now).total_seconds()

        if time_to_event > 15:
            log.info(f"Waiting {time_to_event:.0f}s until pre-news window...")
            await asyncio.sleep(max(0, time_to_event - 15))

        log.info("\n--- GATE 1: Event Whitelist ---")
        gate1_score = self.event_whitelist.get_score(event)
        self.gate_scores["event_impact"] = gate1_score
        log.info(f"Gate 1 Score: {gate1_score}/{CONFLUENCE_POINTS['event_impact']}")

        log.info("\n--- GATE 2: Directional Bias ---")
        bias_result = self.bias_model.analyze_event_impact(event.name, event.currency)
        gate2_score = self.bias_model.get_score(event.name, event.currency)
        self.direction = bias_result["direction"]
        self.gate_scores["directional_bias"] = gate2_score
        log.info(f"Direction: {self.direction} | Confidence: {gate2_score}%")
        log.info(f"Reasoning: {bias_result['reasoning']}")
        log.info(f"Gate 2 Score: {gate2_score}/{CONFLUENCE_POINTS['directional_bias']}")

        log.info("\n--- GATE 3: L3 Order Flow Detection ---")
        l3_result = await self.l3_detector.run_full_detection(event.timestamp)
        self.gate_scores["book_thinning"] = l3_result["vacuum_score"]
        self.gate_scores["anchor_survival"] = l3_result["anchor_score"]
        log.info(f"Gate 3a (Vacuum): {l3_result['vacuum_score']}/{CONFLUENCE_POINTS['book_thinning']}")
        log.info(f"Gate 3b (Anchor): {l3_result['anchor_score']}/{CONFLUENCE_POINTS['anchor_survival']}")

        self.total_score = sum(self.gate_scores.values())
        log.info(f"\n{'='*60}")
        log.info(f"TOTAL SCORE: {self.total_score}/100")
        log.info(f"Threshold: {MIN_CONFIDENCE_SCORE}")
        log.info(f"{'PASS ✓' if self.total_score >= MIN_CONFIDENCE_SCORE else 'FAIL ✗'}")
        log.info(f"{'='*60}\n")

        if self.total_score >= MIN_CONFIDENCE_SCORE:
            log.info(f"Confluence score met! Scheduling T+{ENTRY_DELAY_SEC}s entry...")
            await self._schedule_entry(event)
        else:
            log.info("Confluence score not met. Skipping this event.")

    async def _schedule_entry(self, event: NewsEvent):
        """
        Schedules T+90s entry trigger
        """
        now = datetime.now()
        entry_time = event.timestamp + timedelta(seconds=ENTRY_DELAY_SEC)
        wait_sec = (entry_time - now).total_seconds()

        if wait_sec > 0:
            log.info(f"Waiting {wait_sec:.0f}s until T+{ENTRY_DELAY_SEC}s entry window...")
            await asyncio.sleep(wait_sec)

        log.info(f"\n{'='*60}")
        log.info(f"🚀 ENTRY TRIGGERED 🚀")
        log.info(f"Event: {event.name}")
        log.info(f"Direction: {self.direction}")
        log.info(f"Confluence: {self.total_score}/100")
        log.info(f"Asset: {ASSET}")
        log.info(f"Duration: {TRADE_DURATION}s")
        log.info(f"Stake: ${STAKE_USD}")
        log.info(f"{'='*60}\n")

        await self._execute_trade()

    async def _execute_trade(self):
        """
        Executes trade on Deriv (or logs for manual execution on IQ Option/Pocket Option)
        """
        log.info("Trade execution placeholder")
        log.info("Manual execution: Place 1-min binary on IQ Option or Pocket Option")
        log.info(f"Direction: {self.direction}")
        log.info(f"Entry: Market order at T+{ENTRY_DELAY_SEC}s")

        self.trade_triggered = True

        log.info("\nTrade signal sent. Waiting for next event...")

    def _reset_gates(self):
        """Resets gate scores for new event"""
        self.gate_scores = {
            "event_impact": 0,
            "directional_bias": 0,
            "book_thinning": 0,
            "anchor_survival": 0,
        }
        self.total_score = 0
        self.direction = "NEUTRAL"
        self.trade_triggered = False

    def get_status(self) -> Dict:
        """Returns current engine status"""
        return {
            "monitoring": self.monitoring,
            "current_event": self.current_event.name if self.current_event else None,
            "gate_scores": self.gate_scores.copy(),
            "total_score": self.total_score,
            "direction": self.direction,
            "trade_triggered": self.trade_triggered,
        }

    async def stop(self):
        """Stops NOVA engine"""
        log.info("Stopping NOVA engine...")
        self.monitoring = False
        await self.l3_detector.close()
        log.info("NOVA engine stopped")

async def main():
    """Main entry point"""
    engine = NOVASignalEngine()

    try:
        await engine.start()
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        log.info("Received interrupt signal")
    finally:
        await engine.stop()

if __name__ == "__main__":
    asyncio.run(main())