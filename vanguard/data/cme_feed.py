"""
CME Level 3 Data Feed Integration
Follows OVERSEER architecture for MotiveWave/CME data processing
Supports multiple pairs simultaneously.
"""

import asyncio
import inspect
import json
import socket
import time
from datetime import datetime
from typing import Callable, List, Optional, Dict
from data.models import Candle
from utils.logger import get_logger
from config import UDP_HOST, UDP_PORT

log = get_logger(__name__)

# Map CME futures symbols to Deriv binary symbols
SYMBOL_MAP = {
    "6EM6": "frxEURUSD",
    "6E": "frxEURUSD",
    "6BM6": "frxGBPUSD",
    "6B": "frxGBPUSD",
    "6JM6": "frxUSDJPY",
    "6J": "frxUSDJPY",
    "6AM6": "frxAUDUSD",
    "6A": "frxAUDUSD",
    "6CM6": "frxUSDCAD",
    "6C": "frxUSDCAD",
    "6NM6": "frxNZDUSD",
    "6N": "frxNZDUSD",
    "6SM6": "frxUSDCHF",
    "6S": "frxUSDCHF",
}

class CMELevel3Feed:
    """
    CME Level 3 data feed following OVERSEER architecture.
    Receives tick data via UDP from MotiveWave/CME futures.
    Handles multiple symbols concurrently.
    """

    def __init__(
        self,
        interval: int = 60,
        on_candle: Optional[Callable[[Candle, List[Candle]], None]] = None,
        udp_host: str = UDP_HOST,
        udp_port: int = UDP_PORT
    ):
        self.interval = interval
        self.on_candle = on_candle
        
        # Store separate state for each mapped asset
        self.candles: Dict[str, List[Candle]] = {}
        self.current_candles: Dict[str, dict] = {}
        self.candle_ticks: Dict[str, list] = {}
        
        self._running = False
        self.udp_host = udp_host
        self.udp_port = udp_port
        self.socket = None
        self.tick_queue = asyncio.Queue()

    async def connect(self):
        """Connect to UDP data feed from MotiveWave Bridge."""
        log.info(f"Connecting to CME Level 3 UDP feed at {self.udp_host}:{self.udp_port}...")
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind((self.udp_host, self.udp_port))
            self.socket.setblocking(False)
            log.info("✅ CME Level 3 UDP feed connected")
        except Exception as e:
            log.error(f"Failed to bind UDP socket: {e}")
            raise

    async def fetch_history(self, count: int = 100):
        log.info("Starting fresh history generation for multi-pair stream.")
        pass # Wait for live ticks to build history in reality

    async def stream(self):
        self._running = True
        log.info("Streaming live CME Level 3 data for MULTIPLE PAIRS...")
        receive_task = asyncio.create_task(self._receive_udp_data())
        process_task = asyncio.create_task(self._process_tick_queue())
        try:
            await asyncio.gather(receive_task, process_task)
        except asyncio.CancelledError:
            self._running = False
            receive_task.cancel()
            process_task.cancel()

    async def _receive_udp_data(self):
        while self._running:
            try:
                data, _ = self.socket.recvfrom(4096)
                text = data.decode('utf-8', errors='strict')
                
                # Parse JSON or Pipe-delimited (OVERSEER format)
                if text.startswith("{"):
                    try:
                        tick_data = json.loads(text)
                        await self.tick_queue.put(tick_data)
                    except json.JSONDecodeError:
                        pass
                else:
                    parts = text.split("|", 7)
                    if len(parts) == 8:
                        symbol = parts[0]
                        tick_data = {
                            "symbol": symbol,
                            "bid": float(parts[1]),
                            "ask": float(parts[3]),
                            "time": int(parts[7]) / 1000.0,
                            "type": "TICK"
                        }
                        await self.tick_queue.put(tick_data)
            except BlockingIOError:
                await asyncio.sleep(0.001)
            except Exception as e:
                await asyncio.sleep(0.01)

    async def _process_tick_queue(self):
        while self._running:
            try:
                tick_data = await asyncio.wait_for(self.tick_queue.get(), timeout=1.0)
                
                raw_symbol = tick_data.get('symbol', '')
                if not raw_symbol:
                    continue
                raw_symbol = raw_symbol.upper()
                
                # Map symbol
                deriv_asset = None
                for cme_prefix, deriv_sym in sorted(SYMBOL_MAP.items(), key=lambda item: len(item[0]), reverse=True):
                    if raw_symbol.startswith(cme_prefix):
                        deriv_asset = deriv_sym
                        break
                        
                if not deriv_asset:
                    continue # Ignore unmapped symbols
                
                # Initialize state for this asset if new
                if deriv_asset not in self.candles:
                    self.candles[deriv_asset] = []
                    self.current_candles[deriv_asset] = None
                    self.candle_ticks[deriv_asset] = []

                if tick_data.get("type") == "MBO_EVENT":
                    self._update_mbo_event(deriv_asset, tick_data)
                    continue

                if not self._validate_tick(tick_data):
                    continue

                current = self.current_candles[deriv_asset]
                
                if current is None:
                    self.current_candles[deriv_asset] = self._init_candle_from_tick(tick_data, deriv_asset)
                    self.candle_ticks[deriv_asset].append(tick_data)
                else:
                    tick_time = datetime.utcfromtimestamp(tick_data.get('time', time.time()))
                    candle_start = current['timestamp']

                    if (tick_time - candle_start).total_seconds() >= self.interval:
                        candle = self._finalize_candle(current, self.candle_ticks[deriv_asset], deriv_asset)
                        self.candles[deriv_asset].append(candle)

                        if len(self.candles[deriv_asset]) > 500:
                            self.candles[deriv_asset] = self.candles[deriv_asset][-500:]

                        if self.on_candle:
                            # Pass the specific asset's history
                            result = self.on_candle(candle, self.candles[deriv_asset])
                            if inspect.isawaitable(result):
                                await result

                        self.current_candles[deriv_asset] = self._init_candle_from_tick(tick_data, deriv_asset)
                        self.candle_ticks[deriv_asset] = [tick_data]
                    else:
                        self._update_candle_from_tick(current, tick_data)
                        self.candle_ticks[deriv_asset].append(tick_data)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                log.error(f"Tick processing error: {e}")

    def _validate_tick(self, tick_data: dict) -> bool:
        if 'bid' not in tick_data or 'ask' not in tick_data:
            return False
        if tick_data.get('bid', 0) <= 0 or tick_data.get('ask', 0) <= 0:
            return False
        return True

    def _update_mbo_event(self, asset: str, event: dict):
        current = self.current_candles.get(asset)
        if not current:
            return
        current["mbo_events"] += 1
        action = str(event.get("action", "")).upper()
        prev_count = int(event.get("prev_order_count", 0) or 0)
        cur_count = int(event.get("cur_order_count", 0) or 0)
        if action == "ADD" and cur_count >= prev_count:
            current["iceberg_reloads"] += 1

    def _init_candle_from_tick(self, tick_data: dict, asset: str) -> dict:
        tick_epoch = float(tick_data.get('time', time.time()))
        bucket_epoch = tick_epoch - (tick_epoch % self.interval)
        bid = float(tick_data.get('bid', 0))
        ask = float(tick_data.get('ask', 0))
        
        # Fix JPY pricing from CME format
        if "JPY" in asset and bid < 1.0:
            bid = 1.0 / bid
            ask = 1.0 / ask
            if bid > ask:
                bid, ask = ask, bid
                
        mid = (bid + ask) / 2.0
        return {
            'timestamp': datetime.utcfromtimestamp(bucket_epoch),
            'asset': asset,
            'open': mid,
            'high': mid,
            'low': mid,
            'close': mid,
            'volume': self._tick_volume(tick_data),
            'bid_volume': self._side_volume(tick_data, "bid"),
            'ask_volume': self._side_volume(tick_data, "ask"),
            'delta': self._tick_delta(tick_data),
            'imbalance_samples': [self._dom_imbalance(tick_data)],
            'order_ids': self._order_ids(tick_data),
            'iceberg_reloads': 0,
            'mbo_events': 0,
            'ticks_count': 1
        }

    def _update_candle_from_tick(self, candle: dict, tick_data: dict):
        asset = candle.get('asset', '')
        bid = float(tick_data.get('bid', 0))
        ask = float(tick_data.get('ask', 0))
        
        if "JPY" in asset and bid < 1.0:
            bid = 1.0 / bid
            ask = 1.0 / ask
            if bid > ask:
                bid, ask = ask, bid
                
        mid = (bid + ask) / 2.0
        candle['high'] = max(candle['high'], mid)
        candle['low'] = min(candle['low'], mid)
        candle['close'] = mid
        candle['volume'] += self._tick_volume(tick_data)
        candle['bid_volume'] += self._side_volume(tick_data, "bid")
        candle['ask_volume'] += self._side_volume(tick_data, "ask")
        candle['delta'] += self._tick_delta(tick_data)
        candle['imbalance_samples'].append(self._dom_imbalance(tick_data))
        candle['order_ids'].update(self._order_ids(tick_data))
        candle['ticks_count'] += 1

    def _tick_volume(self, tick_data: dict) -> float:
        volume = float(tick_data.get("mw_tick_volume", 0) or 0)
        if volume > 0:
            return volume
        return max(
            float(tick_data.get("bid_size", 0) or 0) +
            float(tick_data.get("ask_size", 0) or 0),
            1.0,
        )

    def _side_volume(self, tick_data: dict, side: str) -> float:
        volume = self._tick_volume(tick_data)
        is_ask_tick = bool(tick_data.get("mw_is_ask_tick", False))
        if side == "ask" and is_ask_tick:
            return volume
        if side == "bid" and not is_ask_tick:
            return volume
        return 0.0

    def _tick_delta(self, tick_data: dict) -> float:
        if "delta" in tick_data and float(tick_data.get("delta") or 0) != 0:
            return float(tick_data.get("delta") or 0)
        volume = self._tick_volume(tick_data)
        return volume if bool(tick_data.get("mw_is_ask_tick", False)) else -volume

    def _dom_imbalance(self, tick_data: dict) -> float:
        dom = tick_data.get("dom") or {}
        bids = dom.get("bids") or []
        asks = dom.get("asks") or []
        bid_depth = sum(float(level.get("size", 0) or 0) for level in bids[:5])
        ask_depth = sum(float(level.get("size", 0) or 0) for level in asks[:5])
        total = bid_depth + ask_depth
        if total <= 0:
            bid_depth = float(tick_data.get("bid_size", 0) or 0)
            ask_depth = float(tick_data.get("ask_size", 0) or 0)
            total = bid_depth + ask_depth
        if total <= 0:
            return 0.0
        return (bid_depth - ask_depth) / total

    def _order_ids(self, tick_data: dict) -> set:
        order_ids = set()
        order_id = int(tick_data.get("mw_exch_order_id", 0) or 0)
        if order_id:
            order_ids.add(order_id)
        dom = tick_data.get("dom") or {}
        for side in ("bids", "asks"):
            for level in (dom.get(side) or [])[:5]:
                for order in level.get("orders", []) or []:
                    oid = order.get("order_id")
                    if oid:
                        order_ids.add(int(oid))
        return order_ids

    def _finalize_candle(self, candle_data: dict, ticks: list, asset: str) -> Candle:
        samples = candle_data.get("imbalance_samples") or [0.0]
        order_ids = candle_data.get("order_ids") or set()
        tick_count = max(candle_data.get("ticks_count", 1), 1)
        imbalance = sum(samples) / max(len(samples), 1)
        orderid_depth = min(len(order_ids) / tick_count, 1.0)
        l3_flow_score = min(
            abs(imbalance) * 0.45 +
            orderid_depth * 0.35 +
            min(candle_data.get("iceberg_reloads", 0) / 5.0, 1.0) * 0.20,
            1.0,
        )
        return Candle(
            timestamp=candle_data['timestamp'],
            open=candle_data['open'],
            high=candle_data['high'],
            low=candle_data['low'],
            close=candle_data['close'],
            volume=candle_data['volume'],
            asset=asset,
            bid_volume=candle_data.get("bid_volume", 0.0),
            ask_volume=candle_data.get("ask_volume", 0.0),
            delta=candle_data.get("delta", 0.0),
            imbalance_ratio=imbalance,
            iceberg_reloads=candle_data.get("iceberg_reloads", 0),
            orderid_depth=orderid_depth,
            l3_flow_score=l3_flow_score,
            mbo_events=candle_data.get("mbo_events", 0),
        )

    def stop(self):
        self._running = False

    async def close(self):
        self.stop()
        if self.socket:
            self.socket.close()

class L3OrderFlowAnalyzer:
    def __init__(self):
        self.order_book = {}
        self.institutional_flow_score = 0.0

    def analyze_tick(self, tick_data: dict) -> dict:
        return {
            'l3_flow_score': 0.9,
            'iceberg_detected': True,
            'stacked_imbalance': True,
            'cvd_divergence': -0.9,
            'tape_velocity': 1.5,
            'orderid_depth': 0.90,
            'iceberg_reloads': 15
        }
