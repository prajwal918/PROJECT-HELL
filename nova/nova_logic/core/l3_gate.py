from datetime import datetime, timedelta
from typing import Dict, Optional
import asyncio

from nexus_bridge import NEXUSBridge, L3BookTracker
from config import (
    PRE_NEWS_WINDOW_SEC,
    POST_NEWS_WINDOW_SEC,
    BOOK_THINNING_THRESHOLD,
    ANCHOR_RATIO_THRESHOLD,
    NEXUS_WS_URL,
)

class L3GateDetector:
    """
    Gate 3: L3 Order Flow Detection
    3a: Pre-news Vacuum (book thinning)
    3b: Post-news Anchor (surviving order IDs)
    """

    def __init__(self):
        self.nexus = NEXUSBridge(NEXUS_WS_URL)
        self.book = L3BookTracker(max_depth=20)
        self.monitoring = False
        self.event_start_time = None
        self.book_thinning_pct = 0.0
        self.anchor_ratio_pct = 0.0

    async def connect(self):
        """Connect to NEXUS WebSocket"""
        await self.nexus.connect()
        print("[L3] Connected to NEXUS backend")

    async def monitor_pre_news_vacuum(self, window_sec: int = PRE_NEWS_WINDOW_SEC) -> float:
        """
        Gate 3a: Monitors book thinning in pre-news window
        Returns: % depth reduction (0-100)
        """
        print(f"[L3] Starting pre-news vacuum monitor ({window_sec}s window)")
        self.book_thinning_pct = 0.0

        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=window_sec)

        capture_time = end_time - timedelta(seconds=5)

        while datetime.now() < end_time:
            tick = await self.nexus.get_tick_timeout(timeout=1.0)
            if tick:
                self.book.process_tick(tick)

            if datetime.now() >= capture_time and self.book._pre_news_book is None:
                self.book.capture_pre_news_book()
                print(f"[L3] Captured pre-news book baseline")

        self.book_thinning_pct = self.book.calculate_book_thinning()
        print(f"[L3] Pre-news book thinning: {self.book_thinning_pct:.2f}%")

        return self.book_thinning_pct

    async def monitor_post_news_anchor(self, window_sec: int = POST_NEWS_WINDOW_SEC) -> float:
        """
        Gate 3b: Monitors anchor survival in post-news window
        Returns: % orders survived (0-100)
        """
        print(f"[L3] Starting post-news anchor monitor ({window_sec}s window)")
        self.anchor_ratio_pct = 0.0

        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=window_sec)

        tick_count = 0
        while datetime.now() < end_time:
            tick = await self.nexus.get_tick_timeout(timeout=1.0)
            if tick:
                self.book.process_tick(tick)
                tick_count += 1

                if tick_count % 100 == 0:
                    print(f"[L3] Processed {tick_count} ticks...")

        self.anchor_ratio_pct = self.book.calculate_anchor_ratio()
        print(f"[L3] Post-news anchor survival: {self.anchor_ratio_pct:.2f}%")

        return self.anchor_ratio_pct

    async def run_full_detection(self, event_time: datetime) -> Dict:
        """
        Runs complete Gate 3 detection sequence:
        1. Wait until 15s before event
        2. Monitor pre-news vacuum (T-15s to T)
        3. Monitor post-news anchor (T to T+30s)
        Returns: {vacuum_score: int, anchor_score: int, total_score: int, passed: bool}
        """
        print(f"[L3] Running full detection sequence for event at {event_time}")

        now = datetime.now()
        time_to_event = (event_time - now).total_seconds()

        if time_to_event > 15:
            wait_sec = time_to_event - 15
            print(f"[L3] Waiting {wait_sec:.0f}s until pre-news window...")
            await asyncio.sleep(wait_sec)

        print(f"[L3] Starting pre-news vacuum detection...")
        vacuum_pct = await self.monitor_pre_news_vacuum()

        print(f"[L3] Starting post-news anchor detection...")
        anchor_pct = await self.monitor_post_news_anchor()

        vacuum_score = 0
        anchor_score = 0

        if vacuum_pct >= BOOK_THINNING_THRESHOLD:
            vacuum_score = 25
            print(f"[L3] Gate 3a PASSED: vacuum {vacuum_pct:.2f}% >= {BOOK_THINNING_THRESHOLD}%")
        else:
            print(f"[L3] Gate 3a FAILED: vacuum {vacuum_pct:.2f}% < {BOOK_THINNING_THRESHOLD}%")

        if anchor_pct >= ANCHOR_RATIO_THRESHOLD:
            anchor_score = 25
            print(f"[L3] Gate 3b PASSED: anchor {anchor_pct:.2f}% >= {ANCHOR_RATIO_THRESHOLD}%")
        else:
            print(f"[L3] Gate 3b FAILED: anchor {anchor_pct:.2f}% < {ANCHOR_RATIO_THRESHOLD}%")

        total_score = vacuum_score + anchor_score
        passed = total_score >= 25

        result = {
            "vacuum_pct": vacuum_pct,
            "anchor_pct": anchor_pct,
            "vacuum_score": vacuum_score,
            "anchor_score": anchor_score,
            "total_score": total_score,
            "passed": passed,
        }

        print(f"[L3] Gate 3 total: {total_score}/50 points, {'PASSED' if passed else 'FAILED'}")

        return result

    async def get_realtime_book_state(self) -> Dict:
        """
        Returns current book state for visualization
        """
        best_bid, best_ask = self.book.get_best_bid_ask()
        tob = self.book.get_top_of_book(depth=5)

        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": round(best_ask - best_bid, 5) if best_bid and best_ask else 0,
            "top_of_book": tob,
        }

    async def close(self):
        """Disconnect from NEXUS"""
        await self.nexus.close()
        print("[L3] Disconnected from NEXUS backend")