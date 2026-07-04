import asyncio
import random
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core'))
from absorption_detector import AbsorptionDetector, AbsorptionLevel

@dataclass
class MockTick:
    timestamp_ns: int
    price: float
    bid_size: float
    ask_size: float
    trade_size: float
    order_id: int
    action: int
    side: int
    flags: int
    seq_num: int

class MockNEXUSBridge:
    """Mock NEXUS bridge for testing without live data"""

    def __init__(self):
        self.connected = False
        self.tick_queue = asyncio.Queue()
        self._generator_task = None
        self.seq_num = 0
        self.base_price = 1.0850

    async def connect(self):
        self.connected = True
        self._generator_task = asyncio.create_task(self._generate_mock_ticks())
        print("[MOCK] NEXUS bridge connected (mock mode)")

    async def _generate_mock_ticks(self):
        """Generates mock L3 data with absorption patterns"""
        while self.connected:
            price = self.base_price + random.uniform(-0.001, 0.001)

            tick = MockTick(
                timestamp_ns=int(datetime.now().timestamp() * 1e9),
                price=price,
                bid_size=random.uniform(100, 1000),
                ask_size=random.uniform(100, 1000),
                trade_size=random.choice([0, 0, random.uniform(50, 200)]),
                order_id=random.randint(1, 1000000),
                action=3 if random.random() < 0.3 else 0,
                side=random.choice([0, 1]),
                flags=0,
                seq_num=self.seq_num,
            )
            self.seq_num += 1
            await self.tick_queue.put(tick)
            await asyncio.sleep(random.uniform(0.01, 0.03))

    async def get_tick(self):
        return await self.tick_queue.get()

    async def get_tick_timeout(self, timeout: float = 1.0):
        try:
            return await asyncio.wait_for(self.tick_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def close(self):
        self.connected = False
        if self._generator_task:
            self._generator_task.cancel()
        print("[MOCK] NEXUS bridge disconnected")

class AEGISTestMode:
    """AEGIS test mode with mock data"""

    def __init__(self):
        self.nexus = MockNEXUSBridge()
        self.absorption_detector = AbsorptionDetector(
            window_ticks=1000,
            min_absorption_vol=500.0
        )
        self.monitoring = False

    async def start(self):
        print("=" * 60)
        print("  AEGIS TEST MODE (MOCK DATA)")
        print("=" * 60)
        print("\nThis mode uses simulated data for testing")
        print("No live market data or Deriv API required\n")

        await self.nexus.connect()
        self.monitoring = True

        await self._run_test_scenario()

    async def _run_test_scenario(self):
        """Runs a mock absorption scenario"""
        print("[TEST] Simulating absorption scenario...")
        print("[TEST] Processing ticks to detect absorption...\n")

        absorption_detected = None
        tick_count = 0
        max_ticks = 500

        while tick_count < max_ticks and self.monitoring:
            tick = await self.nexus.get_tick()

            absorption = self.absorption_detector.process_tick(tick)

            if absorption and absorption_detected is None:
                absorption_detected = absorption
                print(f"\n{'='*60}")
                print(f"🔍 ABSORPTION DETECTED 🔍")
                print(f"{'='*60}")
                print(f"Price: {absorption.price:.5f}")
                print(f"Side: {absorption.side}")
                print(f"Absorbed Volume: {absorption.absorbed_volume:.2f}")
                print(f"Initial Volume: {absorption.initial_volume:.2f}")
                print(f"Depth Retention: {absorption.depth_retention_pct:.2f}%")
                print(f"Ticks Monitored: {absorption.ticks_monitored}")
                print(f"{'='*60}\n")

                await self._evaluate_gates(absorption)
                break

            tick_count += 1

            if tick_count % 50 == 0:
                print(f"[TEST] Processed {tick_count} ticks...")

        if not absorption_detected:
            print("[TEST] No absorption detected in mock scenario")
            print("[TEST] This is normal - absorption is rare in real markets")

    async def _evaluate_gates(self, absorption: AbsorptionLevel):
        """Evaluates all 4 gates for detected absorption"""
        print("--- GATE EVALUATION (MOCK) ---\n")

        print("Gate 1: Absorption Detection")
        gate1_score = 25
        print(f"  Volume absorbed: {absorption.absorbed_volume:.2f} ≥ 500")
        print(f"  Score: {gate1_score}/25\n")

        print("Gate 2: Depth Retention")
        gate2_score = 25 if absorption.depth_retention_pct >= 70 else 0
        print(f"  Depth retention: {absorption.depth_retention_pct:.2f}% ≥ 70%")
        print(f"  Score: {gate2_score}/25\n")

        print("Gate 3: Rejection Ratio")
        rejection_ratio = 2.5
        gate3_score = 25 if rejection_ratio >= 2.0 else 0
        print(f"  Rejection ratio: {rejection_ratio:.2f} ≥ 2.0 (mocked)")
        print(f"  Score: {gate3_score}/25\n")

        print("Gate 4: Breakout Confirmation")
        breakout = True
        gate4_score = 25 if breakout else 0
        print(f"  Breakout: {'CONFIRMED' if breakout else 'NOT DETECTED'} (mocked)")
        print(f"  Score: {gate4_score}/25\n")

        total = gate1_score + gate2_score + gate3_score + gate4_score

        print("=" * 60)
        print(f"TOTAL SCORE: {total}/100")
        print(f"THRESHOLD: 75")
        print(f"RESULT: {'PASS ✓' if total >= 75 else 'FAIL ✗'}")
        print("=" * 60)

        if total >= 75:
            direction = "CALL" if absorption.side == "ask" else "PUT"
            print(f"\n[TEST] Trade would execute automatically")
            print(f"[TEST] Direction: {direction}")
            print(f"[TEST] Asset: EUR/USD")
            print(f"[TEST] Duration: 15 minutes")
            print(f"[TEST] Stake: $10.00")
            print(f"[TEST] Broker: Deriv (automated)")

        await asyncio.sleep(5)

    async def stop(self):
        self.monitoring = False
        await self.nexus.close()

async def main():
    engine = AEGISTestMode()
    try:
        await engine.start()
    except KeyboardInterrupt:
        print("\n[TEST] Interrupted by user")
    finally:
        await engine.stop()

if __name__ == "__main__":
    asyncio.run(main())