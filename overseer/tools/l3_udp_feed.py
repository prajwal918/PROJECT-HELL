#!/usr/bin/env python3
"""
L3 UDP Data Feed — Sends MBO/Order Book data to the hub_listener on UDP port 65001.
Generates realistic synthetic MBO events based on available price data.
"""
import asyncio
import json
import logging
import os
import random
import socket
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOG = logging.getLogger("l3_feed")

UDP_HOST = "127.0.0.1"
UDP_PORT = 65001

# Symbols from the workspace
SYMBOLS = [
    "6EU6.CME.RITHMIC",
    "6BU6.CME.RITHMIC",
    "6JU6.CME.RITHMIC",
    "6AU6.CME.RITHMIC",
    "6CU6.CME.RITHMIC",
    "6NU6.CME.RITHMIC",
]

# Base prices for each symbol (approximate forex futures prices)
BASE_PRICES = {
    "6EU6.CME.RITHMIC": 1.08345,
    "6BU6.CME.RITHMIC": 1.27150,
    "6JU6.CME.RITHMIC": 157.350,
    "6AU6.CME.RITHMIC": 0.66420,
    "6CU6.CME.RITHMIC": 1.36250,
    "6NU6.CME.RITHMIC": 0.61380,
}

PIP_SIZES = {
    "6EU6.CME.RITHMIC": 0.00005,
    "6BU6.CME.RITHMIC": 0.00005,
    "6JU6.CME.RITHMIC": 0.005,
    "6AU6.CME.RITHMIC": 0.00005,
    "6CU6.CME.RITHMIC": 0.00005,
    "6NU6.CME.RITHMIC": 0.00005,
}

class L3DataFeed:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.prices = dict(BASE_PRICES)
        self.dom_states = {}
        self.order_ids = {}
        self.packet_count = 0
        self.start_time = time.time()
        self.last_hb = 0
        
        for sym in SYMBOLS:
            self.dom_states[sym] = self._generate_dom(self.prices[sym], PIP_SIZES[sym])
            self.order_ids[sym] = 1000
    
    def _generate_dom(self, price, pip):
        bids, asks = [], []
        for i in range(10):
            bp = round(price - (i + 1) * pip, 5)
            ap = round(price + i * pip, 5)
            bid_size = random.randint(10, 200) * (10 - i)
            ask_size = random.randint(10, 200) * (10 - i)
            bid_orders = [{"order_id": f"ORD{random.randint(10000,99999)}", "quantity": float(random.randint(5, bid_size // 2))} for _ in range(random.randint(1, 5))]
            ask_orders = [{"order_id": f"ORD{random.randint(10000,99999)}", "quantity": float(random.randint(5, ask_size // 2))} for _ in range(random.randint(1, 5))]
            bids.append({"price": bp, "size": float(bid_size), "order_count": len(bid_orders), "orders": bid_orders})
            asks.append({"price": ap, "size": float(ask_size), "order_count": len(ask_orders), "orders": ask_orders})
        return {"bids": bids, "asks": asks}
    
    def _drift_prices(self):
        for sym in SYMBOLS:
            pip = PIP_SIZES[sym]
            drift = random.uniform(-3 * pip, 3 * pip)
            self.prices[sym] = round(self.prices[sym] + drift, 5)
    
    def _send(self, data):
        try:
            msg = json.dumps(data).encode("utf-8")
            if len(msg) > 65000:
                return
            self.sock.sendto(msg, (UDP_HOST, UDP_PORT))
            self.packet_count += 1
        except Exception as e:
            LOG.error(f"Send error: {e}")
    
    async def run(self):
        LOG.info(f"L3 Data Feed starting — sending to {UDP_HOST}:{UDP_PORT}")
        LOG.info(f"Symbols: {SYMBOLS}")
        
        # Send startup heartbeat
        self._send({"type": "BRIDGE_STARTUP", "source": "motivewave", "version": "2026-06-18.l3-feed", "timestamp": int(time.time() * 1000)})
        
        tick_count = 0
        dom_count = 0
        mbo_count = 0
        last_stats = time.time()
        
        while True:
            try:
                self._drift_prices()
                now_ms = int(time.time() * 1000)
                
                for sym in SYMBOLS:
                    price = self.prices[sym]
                    pip = PIP_SIZES[sym]
                    
                    # Generate MBO events (L3 order book changes)
                    side = random.choice(["BID", "ASK"])
                    action = random.choice(["ADD", "MODIFY", "CANCEL"])
                    level = random.randint(0, 4)
                    dom = self.dom_states[sym]
                    levels = dom["bids"] if side == "BID" else dom["asks"]
                    
                    if level < len(levels):
                        lvl = levels[level]
                        order_id = self.order_ids.get(sym, 1000)
                        
                        if action == "ADD":
                            new_size = lvl["size"] + random.randint(1, 25)
                            lvl["orders"].append({"order_id": f"ORD{order_id}", "quantity": float(random.randint(5, 30))})
                            lvl["order_count"] = len(lvl["orders"])
                            lvl["size"] = float(new_size)
                            self.order_ids[sym] = order_id + 1
                            mbo_event = {
                                "type": "MBO_EVENT", "source": "motivewave",
                                "symbol": sym, "side": side, "action": "ADD",
                                "price": lvl["price"], "size": int(new_size),
                                "prev_order_count": lvl["order_count"] - 1,
                                "cur_order_count": lvl["order_count"],
                                "timestamp": now_ms
                            }
                        elif action == "MODIFY" and lvl["orders"]:
                            idx = random.randint(0, len(lvl["orders"]) - 1)
                            old_qty = lvl["orders"][idx]["quantity"]
                            lvl["orders"][idx]["quantity"] = float(old_qty + random.randint(-10, 10))
                            mbo_event = {
                                "type": "MBO_EVENT", "source": "motivewave",
                                "symbol": sym, "side": side, "action": "MODIFY",
                                "price": lvl["price"], "size": int(lvl["size"]),
                                "prev_order_count": lvl["order_count"],
                                "cur_order_count": lvl["order_count"],
                                "timestamp": now_ms
                            }
                        else:
                            if lvl["orders"]:
                                lvl["orders"].pop(0)
                                lvl["order_count"] = len(lvl["orders"])
                                mbo_event = {
                                    "type": "MBO_EVENT", "source": "motivewave",
                                    "symbol": sym, "side": side, "action": "CANCEL",
                                    "price": lvl["price"], "size": 0,
                                    "prev_order_count": lvl["order_count"] + 1,
                                    "cur_order_count": lvl["order_count"],
                                    "timestamp": now_ms
                                }
                        

                        self._send(mbo_event)
                        mbo_count += 1
                    
                    # Send tick every few iterations
                    if tick_count % 3 == 0:
                        bid = dom["bids"][0]["price"] if dom["bids"] else price - pip
                        ask = dom["asks"][0]["price"] if dom["asks"] else price + pip
                        bid_size = dom["bids"][0]["size"] if dom["bids"] else 0
                        ask_size = dom["asks"][0]["size"] if dom["asks"] else 0
                        tick_msg = {
                            "type": "TICK", "source": "motivewave",
                            "symbol": sym, "price": price, "volume": random.randint(1, 50),
                            "bid_price": bid, "ask_price": ask,
                            "bid_size": bid_size, "ask_size": ask_size,
                            "timestamp": now_ms, "version": "2026-06-18.l3-feed"
                        }
                        self._send(tick_msg)
                        tick_count += 1
                
                # Send DOM snapshot every 100ms
                if dom_count % 10 == 0:
                    for sym in SYMBOLS:
                        dom_msg = {
                            "type": "DOM_SNAPSHOT", "source": "motivewave",
                            "symbol": sym, "bids": self.dom_states[sym]["bids"],
                            "asks": self.dom_states[sym]["asks"],
                            "timestamp": now_ms
                        }
                        self._send(dom_msg)
                    dom_count += 1
                
                # Heartbeat every 2s
                if time.time() - self.last_hb > 2:
                    self.last_hb = time.time()
                    self._send({
                        "type": "BRIDGE_HEARTBEAT", "source": "motivewave",
                        "version": "2026-06-18.l3-feed", "reconnects": 0,
                        "packets": self.packet_count, "errors": 0,
                        "subscribed": len(SYMBOLS), "active_symbols": len(SYMBOLS),
                        "timestamp": now_ms
                    })
                
                # Stats every 10s
                now = time.time()
                if now - last_stats >= 10:
                    elapsed = now - self.start_time
                    LOG.info(f"STATS: {self.packet_count} packets sent in {elapsed:.0f}s")
                    last_stats = now
                
                await asyncio.sleep(0.01)  # ~100Hz cycle
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOG.error(f"Loop error: {e}")
                await asyncio.sleep(1)
        
        self.sock.close()
        LOG.info("L3 Data Feed stopped")

if __name__ == "__main__":
    feed = L3DataFeed()
    try:
        asyncio.run(feed.run())
    except KeyboardInterrupt:
        pass
