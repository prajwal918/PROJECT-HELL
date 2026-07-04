import asyncio
import websockets
import flatbuffers
from dataclasses import dataclass
from typing import Optional
from collections import deque
import time

@dataclass
class Tick:
    timestamp_ns: int
    price: float
    bid_size: float
    ask_size: float
    trade_size: float
    order_id: int
    action: int  # INSERT=0, UPDATE=1, DELETE=2, TRADE=3, TOP_OF_BOOK=4
    side: int    # BID=0, ASK=1
    flags: int   # bitmask: ICEBERG=1, ABSORPTION=2, LIQUIDATION=4, SNAPSHOT=8
    seq_num: int

class NEXUSBridge:
    """
    Connects to NEXUS Rust backend at ws://localhost:9001
    Receives FlatBuffer-encoded TickMessage
    Provides Python interface for NOVA/AEGIS L3 data
    """

    def __init__(self, url: str = "ws://localhost:9001"):
        self.url = url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.tick_queue = asyncio.Queue()
        self.lobe_snapshot = None
        self._reader_task = None
        self._last_seq = 0

    async def connect(self):
        if self.connected:
            return

        try:
            self.ws = await websockets.connect(self.url)
            self.connected = True
            self._reader_task = asyncio.create_task(self._reader_loop())
            print(f"[NEXUS] Connected to {self.url}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to NEXUS: {e}")

    def _decode_flatbuffer(self, data: bytes) -> Optional[Tick]:
        """
        Manually decode FlatBuffer TickMessage
        NEXUS encodes with raw table fields (no schema verification)
        """
        if len(data) < 16:
            return None

        buf = bytearray(data)
        offset = 0

        def get_voffset(table_offset: int, field_idx: int) -> Optional[int]:
            vtable = table_offset - buf[table_offset]
            if vtable + 2 + field_idx * 2 >= len(buf):
                return None
            voffset = int.from_bytes(buf[vtable + 2 + field_idx * 2:vtable + 4 + field_idx * 2], 'little', signed=True)
            if voffset == 0:
                return None
            return table_offset + voffset

        def get_u64(offset: int, default: int = 0) -> int:
            if offset is None or offset + 8 > len(buf):
                return default
            return int.from_bytes(buf[offset:offset+8], 'little', signed=False)

        def get_f64(offset: int, default: float = 0.0) -> float:
            if offset is None or offset + 8 > len(buf):
                return default
            import struct
            return struct.unpack('<d', buf[offset:offset+8])[0]

        def get_f32(offset: int, default: float = 0.0) -> float:
            if offset is None or offset + 4 > len(buf):
                return default
            import struct
            return struct.unpack('<f', buf[offset:offset+4])[0]

        def get_u32(offset: int, default: int = 0) -> int:
            if offset is None or offset + 4 > len(buf):
                return default
            return int.from_bytes(buf[offset:offset+4], 'little', signed=False)

        def get_u8(offset: int, default: int = 0) -> int:
            if offset is None or offset >= len(buf):
                return default
            return buf[offset]

        table_start = 0
        try:
            timestamp_ns = get_u64(get_voffset(table_start, 0), 0)
            price = get_f64(get_voffset(table_start, 1), 0.0)
            bid_size = get_f32(get_voffset(table_start, 2), 0.0)
            ask_size = get_f32(get_voffset(table_start, 3), 0.0)
            trade_size = get_f32(get_voffset(table_start, 4), 0.0)
            order_id = get_u32(get_voffset(table_start, 5), 0)
            action = get_u8(get_voffset(table_start, 6), 0)
            side = get_u8(get_voffset(table_start, 7), 0)
            flags = get_u8(get_voffset(table_start, 8), 0)
            seq_num = get_u64(get_voffset(table_start, 9), 0)

            return Tick(
                timestamp_ns=timestamp_ns,
                price=price,
                bid_size=float(bid_size),
                ask_size=float(ask_size),
                trade_size=float(trade_size),
                order_id=order_id,
                action=action,
                side=side,
                flags=flags,
                seq_num=seq_num,
            )
        except Exception as e:
            print(f"[NEXUS] Decode error: {e}")
            return None

    async def _reader_loop(self):
        try:
            async for message in self.ws:
                if isinstance(message, bytes):
                    tick = self._decode_flatbuffer(message)
                    if tick:
                        await self.tick_queue.put(tick)
                        self._last_seq = tick.seq_num
        except Exception as e:
            print(f"[NEXUS] Reader loop error: {e}")
            self.connected = False
        finally:
            if self.ws:
                await self.ws.close()

    async def get_tick(self) -> Optional[Tick]:
        """Get next tick from queue (blocking)"""
        return await self.tick_queue.get()

    async def get_tick_timeout(self, timeout: float = 1.0) -> Optional[Tick]:
        """Get next tick with timeout"""
        try:
            return await asyncio.wait_for(self.tick_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def request_recovery(self):
        """Request delta sync from last known seq_num"""
        if not self.ws:
            return

        recovery_msg = f"RECOVERY_REQUEST {self._last_seq}"
        await self.ws.send(recovery_msg)
        print(f"[NEXUS] Requested recovery from seq {self._last_seq}")

    async def close(self):
        self.connected = False
        if self._reader_task:
            self._reader_task.cancel()
        if self.ws:
            await self.ws.close()
        print("[NEXUS] Disconnected")

class L3BookTracker:
    """
    Tracks Limit Order Book state from NEXUS ticks
    Maintains order_id tracking for anchor detection (NOVA Gate 3)
    """

    def __init__(self, max_depth: int = 20):
        self.bids = {}  # price -> {size, order_count, order_ids}
        self.asks = {}  # price -> {size, order_count, order_ids}
        self.max_depth = max_depth
        self._pre_news_book = {}  # Stores pre-news order IDs for anchor detection
        self._news_order_ids = set()  # Orders active at news time
        self._surviving_orders = set()  # Orders that survived news event

    def process_tick(self, tick: Tick):
        price = tick.price
        side = "bid" if tick.side == 0 else "ask"
        book = self.bids if tick.side == 0 else self.asks

        if tick.action == 0:  # INSERT
            if price not in book:
                book[price] = {"size": 0.0, "order_count": 0, "order_ids": set()}
            book[price]["size"] = tick.bid_size if tick.side == 0 else tick.ask_size
            book[price]["order_count"] += 1
            book[price]["order_ids"].add(tick.order_id)
            self._news_order_ids.add(tick.order_id)

        elif tick.action == 1:  # UPDATE
            if price in book:
                book[price]["size"] = tick.bid_size if tick.side == 0 else tick.ask_size
                if tick.order_id in self._news_order_ids:
                    self._surviving_orders.add(tick.order_id)

        elif tick.action == 2:  # DELETE
            if price in book:
                book[price]["order_ids"].discard(tick.order_id)
                book[price]["order_count"] = max(0, book[price]["order_count"] - 1)
                if tick.order_id in self._news_order_ids:
                    self._surviving_orders.discard(tick.order_id)
                if book[price]["order_count"] == 0:
                    del book[price]

    def capture_pre_news_book(self):
        """Capture current book state before news event"""
        self._pre_news_book = {
            "bids": {p: dict(v) for p, v in list(self.bids.items())[:self.max_depth]},
            "asks": {p: dict(v) for p, v in list(self.asks.items())[:self.max_depth]},
            "order_ids": self._news_order_ids.copy(),
        }
        print(f"[L3] Captured pre-news book: {len(self._pre_news_book['order_ids'])} orders")

    def calculate_book_thinning(self) -> float:
        """
        Calculate book thinning percentage (Gate 3 pre-news vacuum detector)
        Returns: % reduction in book depth from pre-news state
        """
        if not self._pre_news_book:
            return 0.0

        pre_bid_depth = sum(v["size"] for v in self._pre_news_book["bids"].values())
        pre_ask_depth = sum(v["size"] for v in self._pre_news_book["asks"].values())
        pre_total = pre_bid_depth + pre_ask_depth

        cur_bid_depth = sum(v["size"] for v in list(self.bids.values())[:self.max_depth])
        cur_ask_depth = sum(v["size"] for v in list(self.asks.values())[:self.max_depth])
        cur_total = cur_bid_depth + cur_ask_depth

        if pre_total == 0:
            return 0.0

        thinning = ((pre_total - cur_total) / pre_total) * 100
        return max(0.0, thinning)

    def calculate_anchor_ratio(self) -> float:
        """
        Calculate anchor ratio (Gate 3 post-news anchor detector)
        Returns: % of pre-news orders that survived news event
        """
        if not self._pre_news_book or not self._news_order_ids:
            return 0.0

        total_orders = len(self._news_order_ids)
        surviving = len(self._surviving_orders)

        if total_orders == 0:
            return 0.0

        return (surviving / total_orders) * 100

    def get_best_bid_ask(self) -> tuple:
        """Returns (best_bid, best_ask) or (None, None)"""
        best_bid = max(self.bids.keys()) if self.bids else None
        best_ask = min(self.asks.keys()) if self.asks else None
        return best_bid, best_ask

    def get_top_of_book(self, depth: int = 5) -> dict:
        """Returns top N levels of LOB"""
        sorted_bids = sorted(self.bids.items(), reverse=True)[:depth]
        sorted_asks = sorted(self.asks.items())[:depth]

        return {
            "bids": [(p, v["size"], v["order_count"]) for p, v in sorted_bids],
            "asks": [(p, v["size"], v["order_count"]) for p, v in sorted_asks],
        }