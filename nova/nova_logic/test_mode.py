import asyncio
import random
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core'))
from event_whitelist import EventWhitelist, NewsEvent
from directional_bias import DirectionalBiasModel
from config import ENTRY_DELAY_SEC, MIN_CONFIDENCE_SCORE, CONFLUENCE_POINTS

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
        """Generates mock L3 data"""
        while self.connected:
            tick = MockTick(
                timestamp_ns=int(datetime.now().timestamp() * 1e9),
                price=self.base_price + random.uniform(-0.001, 0.001),
                bid_size=random.uniform(100, 1000),
                ask_size=random.uniform(100, 1000),
                trade_size=random.choice([0, 0, 0, random.uniform(10, 100)]),
                order_id=random.randint(1, 1000000),
                action=random.choice([0, 1, 2, 3]),
                side=random.choice([0, 1]),
                flags=0,
                seq_num=self.seq_num,
            )
            self.seq_num += 1
            await self.tick_queue.put(tick)
            await asyncio.sleep(random.uniform(0.01, 0.05))

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

class MockL3BookTracker:
    """Mock L3 book tracker for testing"""

    def __init__(self):
        self.bids = {}
        self.asks = {}
        self._pre_news_book = None
        self._news_order_ids = set()
        self._surviving_orders = set()
        self._book_thinning_pct = 0.0
        self._anchor_ratio_pct = 0.0

    def process_tick(self, tick):
        price = tick.price
        side = "bid" if tick.side == 0 else "ask"

        if tick.action == 0:
            book = self.bids if tick.side == 0 else self.asks
            book[price] = {"size": tick.bid_size if tick.side == 0 else tick.ask_size, "order_ids": set([tick.order_id])}
            self._news_order_ids.add(tick.order_id)
        elif tick.action == 2:
            book = self.bids if tick.side == 0 else self.asks
            if price in book:
                book[price]["order_ids"].discard(tick.order_id)
                if tick.order_id in self._news_order_ids:
                    self._surviving_orders.discard(tick.order_id)

    def capture_pre_news_book(self):
        self._pre_news_book = {"bids": self.bids.copy(), "asks": self.asks.copy(), "order_ids": self._news_order_ids.copy()}

    def calculate_book_thinning(self):
        if not self._pre_news_book:
            return 0.0

        pre_depth = sum(v["size"] for v in self._pre_news_book["bids"].values()) + sum(v["size"] for v in self._pre_news_book["asks"].values())
        cur_depth = sum(v["size"] for v in self.bids.values()) + sum(v["size"] for v in self.asks.values())

        if pre_depth == 0:
            return 0.0

        self._book_thinning_pct = ((pre_depth - cur_depth) / pre_depth) * 100
        return max(0.0, self._book_thinning_pct)

    def calculate_anchor_ratio(self):
        if not self._pre_news_book or not self._news_order_ids:
            return 0.0

        total_orders = len(self._news_order_ids)
        surviving = len(self._surviving_orders)

        if total_orders == 0:
            return 0.0

        self._anchor_ratio_pct = (surviving / total_orders) * 100
        return self._anchor_ratio_pct

class NOVATestMode:
    """NOVA test mode with mock data"""

    def __init__(self):
        self.event_whitelist = EventWhitelist()
        self.bias_model = DirectionalBiasModel()
        self.nexus = MockNEXUSBridge()
        self.book = MockL3BookTracker()
        self.monitoring = False

    async def start(self):
        print("=" * 60)
        print("  NOVA TEST MODE (MOCK DATA)")
        print("=" * 60)
        print("\nThis mode uses simulated data for testing")
        print("No live market data or API keys required\n")

        await self.nexus.connect()
        self.monitoring = True

        await self._run_test_scenario()

    async def _run_test_scenario(self):
        """Runs a mock news event scenario"""
        print("[TEST] Creating mock news event...")

        mock_event = NewsEvent(
            timestamp=datetime.now() + timedelta(seconds=30),
            currency="USD",
            name="Non-Farm Payrolls",
            impact="High",
        )

        print(f"[TEST] Event: {mock_event.name}")
        print(f"[TEST] Time: {mock_event.timestamp.strftime('%H:%M:%S')}")
        print(f"[TEST] Starting pre-news vacuum detection (30s window)...\n")

        await asyncio.sleep(5)

        print("[TEST] Capturing pre-news book state...")
        self.book.capture_pre_news_book()

        await asyncio.sleep(10)

        print("[TEST] Processing ticks...")
        for _ in range(100):
            tick = await self.nexus.get_tick()
            self.book.process_tick(tick)

        thinning = self.book.calculate_book_thinning()
        print(f"[TEST] Book thinning: {thinning:.2f}%")

        await asyncio.sleep(15)

        print("[TEST] Processing post-news ticks...")
        for _ in range(100):
            tick = await self.nexus.get_tick()
            self.book.process_tick(tick)

        anchor = self.book.calculate_anchor_ratio()
        print(f"[TEST] Anchor survival: {anchor:.2f}%")

        print("\n" + "=" * 60)
        print("  GATE EVALUATION (MOCK)")
        print("=" * 60)

        gate1_score = 25
        print(f"Gate 1 (Event Whitelist): {gate1_score}/25")

        bias_result = self.bias_model.analyze_event_impact(mock_event.name, mock_event.currency)
        gate2_score = self.bias_model.get_score(mock_event.name, mock_event.currency)
        print(f"Gate 2 (Directional Bias): {gate2_score}/25")
        print(f"  Direction: {bias_result['direction']}")
        print(f"  Confidence: {gate2_score}%")

        gate3a_score = 25 if thinning >= 25 else 0
        print(f"Gate 3a (Book Thinning): {gate3a_score}/25")
        print(f"  Thinning: {thinning:.2f}%")

        gate3b_score = 25 if anchor >= 60 else 0
        print(f"Gate 3b (Anchor Survival): {gate3b_score}/25")
        print(f"  Survival: {anchor:.2f}%")

        total = gate1_score + gate2_score + gate3a_score + gate3b_score

        print("\n" + "=" * 60)
        print(f"TOTAL SCORE: {total}/100")
        print(f"THRESHOLD: {MIN_CONFIDENCE_SCORE}")
        print(f"RESULT: {'PASS ✓' if total >= MIN_CONFIDENCE_SCORE else 'FAIL ✗'}")
        print("=" * 60)

        if total >= MIN_CONFIDENCE_SCORE:
            print(f"\n[TEST] Entry signal would trigger at T+{ENTRY_DELAY_SEC}s")
            print(f"[TEST] Direction: {bias_result['direction']}")
        else:
            print(f"\n[TEST] No entry signal (insufficient confluence)")

        await asyncio.sleep(5)

    async def stop(self):
        self.monitoring = False
        await self.nexus.close()

async def main():
    engine = NOVATestMode()
    try:
        await engine.start()
    except KeyboardInterrupt:
        print("\n[TEST] Interrupted by user")
    finally:
        await engine.stop()

if __name__ == "__main__":
    asyncio.run(main())