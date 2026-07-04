import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional

from absorption_detector import AbsorptionDetector, AbsorptionLevel
from deriv_execution import DerivExecution
from nexus_bridge import NEXUSBridge, Tick
from config import (
    NEXUS_WS_URL,
    MIN_ABSORPTION_VOLUME,
    MIN_DEPTH_RETENTION_PCT,
    MIN_REJECTION_RATIO,
    CONFLUENCE_POINTS,
    MIN_CONFIDENCE_SCORE,
    STAKE_USD,
    TRADE_DURATION,
    ASSET,
)

logging.basicConfig(
    level="INFO",
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("aegis.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("AEGIS")

class AEGISSignalEngine:
    """
    Main AEGIS signal engine
    Orchestrates 4 gates for MBO absorption trap detection
    Automated execution via Deriv API
    """

    def __init__(self):
        self.nexus = NEXUSBridge(NEXUS_WS_URL)
        self.absorption_detector = AbsorptionDetector(
            window_ticks=1000,
            min_absorption_vol=MIN_ABSORPTION_VOLUME
        )
        self.deriv = DerivExecution()
        self.monitoring = False
        self.current_absorption: Optional[AbsorptionLevel] = None
        self.gate_scores = {
            "absorption_detection": 0,
            "depth_retention": 0,
            "rejection_ratio": 0,
            "breakout_confirmation": 0,
        }
        self.total_score = 0
        self.direction = None
        self.trade_triggered = False

    async def start(self):
        """Start AEGIS engine"""
        log.info("=== AEGIS Signal Engine Starting ===")
        log.info(f"Target Asset: {ASSET}")
        log.info(f"Trade Duration: {TRADE_DURATION}s (15 min)")
        log.info(f"Stake: ${STAKE_USD}")
        log.info(f"Absorption Threshold: {MIN_ABSORPTION_VOLUME} contracts")
        log.info(f"Depth Retention: ≥{MIN_DEPTH_RETENTION_PCT}%")
        log.info(f"Rejection Ratio: ≥{MIN_REJECTION_RATIO}")

        await self.nexus.connect()
        await self.deriv.connect()
        self.monitoring = True

        asyncio.create_task(self._monitor_results())
        asyncio.create_task(self._tick_loop())

    async def _tick_loop(self):
        """Main tick processing loop"""
        log.info("Starting tick processing loop...")

        while self.monitoring:
            tick = await self.nexus.get_tick_timeout(timeout=1.0)

            if tick:
                absorption = self.absorption_detector.process_tick(tick)

                if absorption and self.current_absorption is None:
                    log.info(f"\n{'='*60}")
                    log.info(f"🔍 ABSORPTION DETECTED 🔍")
                    log.info(f"Price: {absorption.price}")
                    log.info(f"Side: {absorption.side}")
                    log.info(f"Absorbed Volume: {absorption.absorbed_volume:.2f}")
                    log.info(f"Initial Volume: {absorption.initial_volume:.2f}")
                    log.info(f"Depth Retention: {absorption.depth_retention_pct:.2f}%")
                    log.info(f"Ticks Monitored: {absorption.ticks_monitored}")
                    log.info(f"{'='*60}\n")

                    self.current_absorption = absorption
                    await self._evaluate_gates(absorption)

    async def _evaluate_gates(self, absorption: AbsorptionLevel):
        """
        Evaluates all 4 gates for detected absorption
        """
        log.info("--- GATE 1: Absorption Detection ---")
        gate1_score = CONFLUENCE_POINTS["absorption_detection"]
        self.gate_scores["absorption_detection"] = gate1_score
        log.info(f"Absorption detected: {absorption.absorbed_volume:.2f} ≥ {MIN_ABSORPTION_VOLUME}")
        log.info(f"Gate 1 Score: {gate1_score}/{CONFLUENCE_POINTS['absorption_detection']}")

        log.info("\n--- GATE 2: Depth Retention ---")
        gate2_score = 0
        if absorption.depth_retention_pct >= MIN_DEPTH_RETENTION_PCT:
            gate2_score = CONFLUENCE_POINTS["depth_retention"]
        self.gate_scores["depth_retention"] = gate2_score
        log.info(f"Depth Retention: {absorption.depth_retention_pct:.2f}% ≥ {MIN_DEPTH_RETENTION_PCT}%")
        log.info(f"Gate 2 Score: {gate2_score}/{CONFLUENCE_POINTS['depth_retention']}")

        log.info("\n--- GATE 3: Rejection Ratio ---")
        rejection_ratio = self.absorption_detector.calculate_rejection_ratio(absorption.price)
        gate3_score = 0
        if rejection_ratio >= MIN_REJECTION_RATIO:
            gate3_score = CONFLUENCE_POINTS["rejection_ratio"]
        self.gate_scores["rejection_ratio"] = gate3_score
        log.info(f"Rejection Ratio: {rejection_ratio:.2f} ≥ {MIN_REJECTION_RATIO}")
        log.info(f"Gate 3 Score: {gate3_score}/{CONFLUENCE_POINTS['rejection_ratio']}")

        self.total_score = sum(self.gate_scores.values())
        log.info(f"\nPre-Breakout Confluence: {self.total_score}/100")

        if self.total_score >= 50:
            log.info(f"Awaiting breakout confirmation (Gate 4)...")
            await self._monitor_breakout(absorption)
        else:
            log.info("Confluence insufficient. Waiting for next absorption...")
            self.current_absorption = None

    async def _monitor_breakout(self, absorption: AbsorptionLevel):
        """Monitors for breakout through absorption level"""
        log.info(f"Monitoring breakout at {absorption.price}...")

        breakout_detected = False
        attempts = 0
        max_attempts = 300

        while attempts < max_attempts and self.monitoring:
            breakout = self.absorption_detector.detect_breakout(absorption.price, absorption.side)

            if breakout:
                log.info(f"\n{'='*60}")
                log.info(f"🚀 BREAKOUT CONFIRMED 🚀")
                log.info(f"{'='*60}\n")

                breakout_detected = True
                break

            attempts += 1
            await asyncio.sleep(1)

        log.info("\n--- GATE 4: Breakout Confirmation ---")
        gate4_score = 0
        if breakout_detected:
            gate4_score = CONFLUENCE_POINTS["breakout_confirmation"]
        self.gate_scores["breakout_confirmation"] = gate4_score
        log.info(f"Breakout: {'CONFIRMED' if breakout_detected else 'NOT DETECTED'}")
        log.info(f"Gate 4 Score: {gate4_score}/{CONFLUENCE_POINTS['breakout_confirmation']}")

        self.total_score = sum(self.gate_scores.values())
        log.info(f"\n{'='*60}")
        log.info(f"TOTAL SCORE: {self.total_score}/100")
        log.info(f"Threshold: {MIN_CONFIDENCE_SCORE}")
        log.info(f"{'PASS ✓' if self.total_score >= MIN_CONFIDENCE_SCORE else 'FAIL ✗'}")
        log.info(f"{'='*60}\n")

        if self.total_score >= MIN_CONFIDENCE_SCORE:
            self.direction = "CALL" if absorption.side == "ask" else "PUT"
            log.info(f"Trade Direction: {self.direction}")
            await self._execute_trade()
        else:
            log.info("Confluence not met. Waiting for next absorption...")

        self.current_absorption = None

    async def _execute_trade(self):
        """Executes trade via Deriv API"""
        log.info(f"\n{'='*60}")
        log.info(f"💹 EXECUTING TRADE 💹")
        log.info(f"Direction: {self.direction}")
        log.info(f"Confluence: {self.total_score}/100")
        log.info(f"Asset: {ASSET}")
        log.info(f"Duration: {TRADE_DURATION}s")
        log.info(f"Stake: ${STAKE_USD}")
        log.info(f"{'='*60}\n")

        record = await self.deriv.place_trade(self.direction)

        if record:
            log.info(f"Trade ID: {record.broker_trade_id}")
            self.trade_triggered = True
        else:
            log.error("Trade execution failed")

    async def _monitor_results(self):
        """Monitors trade results"""
        async for result in self.deriv.listen_results():
            log.info(f"\n{'='*60}")
            log.info(f"📊 TRADE RESULT 📊")
            log.info(f"ID: {result.broker_trade_id}")
            log.info(f"Direction: {result.direction}")
            log.info(f"Result: {result.result}")
            log.info(f"Profit: ${result.profit:.2f}")
            log.info(f"{'='*60}\n")

            self.trade_triggered = False

    def get_status(self) -> Dict:
        """Returns current engine status"""
        return {
            "monitoring": self.monitoring,
            "current_absorption": self.current_absorption.price if self.current_absorption else None,
            "gate_scores": self.gate_scores.copy(),
            "total_score": self.total_score,
            "direction": self.direction,
            "trade_triggered": self.trade_triggered,
        }

    async def stop(self):
        """Stops AEGIS engine"""
        log.info("Stopping AEGIS engine...")
        self.monitoring = False
        await self.nexus.close()
        await self.deriv.close()
        log.info("AEGIS engine stopped")

async def main():
    """Main entry point"""
    engine = AEGISSignalEngine()

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