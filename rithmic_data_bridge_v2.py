#!/usr/bin/env python3
"""
PROJECT HELL - RITHMIC DATA BRIDGE V2
Simplified version with fallback to simulation
"""

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
import random
import websockets

# Configuration
PROJECT_ROOT = Path(__file__).parent
CONFIG_PATH = PROJECT_ROOT / "nexus" / "rust-backend" / ".env.rithmic"
BROADCAST_PORT = 9001

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class SimpleRithmicBridge:
    def __init__(self):
        self.config = self.load_config()
        self.clients = set()
        self.running = True
        self.message_count = 0
        self.start_time = datetime.now()

    def load_config(self):
        """Load Rithmic credentials"""
        if not CONFIG_PATH.exists():
            logger.error(f"Config file not found: {CONFIG_PATH}")
            return None

        config = {}
        with open(CONFIG_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if line and '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()

        return config

    async def start_websocket_server(self):
        """Start WebSocket server for NOVA/AEGIS"""
        logger.info(f"Starting WebSocket server on port {BROADCAST_PORT}")

        async def handle_client(websocket, path):
            logger.info(f"Client connected: {websocket.remote_address}")
            self.clients.add(websocket)

            try:
                # Send immediate confirmation
                await websocket.send(json.dumps({
                    "type": "connected",
                    "message": "Rithmic Data Bridge Connected",
                    "timestamp": datetime.now().isoformat()
                }))

                # Send initial MBO state
                initial_state = self.generate_mbo_state()
                await websocket.send(json.dumps({
                    "type": "mbo_update",
                    "data": initial_state,
                    "timestamp": datetime.now().isoformat()
                }))

                # Keep connection alive and send updates
                while self.running:
                    await asyncio.sleep(0.1)  # 10 updates per second
                    mbo_update = self.generate_mbo_update()
                    await websocket.send(json.dumps({
                        "type": "mbo_update",
                        "data": mbo_update,
                        "timestamp": datetime.now().isoformat()
                    }))

            except Exception as e:
                logger.error(f"Client error: {e}")
            finally:
                self.clients.discard(websocket)
                logger.info(f"Client disconnected")

        server = await websockets.serve(handle_client, "0.0.0.0", BROADCAST_PORT)
        logger.info(f"WebSocket server listening on ws://0.0.0.0:{BROADCAST_PORT}")

    def generate_mbo_state(self):
        """Generate initial MBO state"""
        price_base = 1.0850
        tick_size = 0.0001

        bids = {}
        for i in range(10):
            price = round(price_base - (i * tick_size), 4)
            bids[price] = {
                "total_size": random.randint(500, 2000),
                "order_count": random.randint(10, 30)
            }

        asks = {}
        for i in range(10):
            price = round(price_base + tick_size + (i * tick_size), 4)
            asks[price] = {
                "total_size": random.randint(500, 2000),
                "order_count": random.randint(10, 30)
            }

        return {
            "symbol": "EUR/USD",
            "bids": bids,
            "asks": asks,
            "best_bid": price_base,
            "best_ask": price_base + tick_size,
            "spread": tick_size
        }

    def generate_mbo_update(self):
        """Generate MBO update with realistic microstructure"""
        self.message_count += 1

        # Simulate realistic order book dynamics
        price_base = 1.0850
        tick_size = 0.0001

        # Random walk for price
        if random.random() < 0.1:  # 10% chance of price move
            price_move = random.choice([-tick_size, tick_size])
            price_base += price_move

        # Generate realistic depth
        bids = {}
        for i in range(10):
            price = round(price_base - (i * tick_size), 4)
            # Simulate book thinning (important for NOVA Gate 3a)
            if random.random() < 0.05:  # 5% chance of thinning
                size = random.randint(50, 200)
            else:
                size = random.randint(500, 2000)

            bids[price] = {
                "total_size": size,
                "order_count": random.randint(10, 30)
            }

        asks = {}
        for i in range(10):
            price = round(price_base + tick_size + (i * tick_size), 4)
            # Simulate absorption (important for AEGIS Gate 1)
            if random.random() < 0.05:  # 5% chance of absorption
                size = random.randint(1000, 5000)  # Large size = absorption
            else:
                size = random.randint(500, 2000)

            asks[price] = {
                "total_size": size,
                "order_count": random.randint(10, 30)
            }

        return {
            "symbol": "EUR/USD",
            "bids": bids,
            "asks": asks,
            "best_bid": price_base,
            "best_ask": price_base + tick_size,
            "spread": tick_size,
            "sequence": self.message_count
        }

    async def monitor_performance(self):
        """Monitor and log performance"""
        while self.running:
            await asyncio.sleep(10)  # Every 10 seconds

            elapsed = (datetime.now() - self.start_time).total_seconds()
            rate = self.message_count / elapsed if elapsed > 0 else 0

            logger.info(f"Performance: {self.message_count} messages | {rate:.1f} msg/sec | {len(self.clients)} clients")

    async def try_rithmic_connection(self):
        """Try to connect to real Rithmic (for future use)"""
        if not self.config:
            return

        logger.info("Rithmic connection endpoint found:")
        logger.info("  URL: wss://rituz00100.rithmic.com:443")
        logger.info("  Gateway: Rithmic Paper Trading")
        logger.info("  Protocol: Protocol Buffers (not JSON)")
        logger.info("")
        logger.info("Current status: Using high-fidelity simulation")
        logger.info("Real Rithmic connection requires Protocol Buffers implementation")
        logger.info("")

    async def run(self):
        """Main run loop"""
        logger.info("="*60)
        logger.info("  PROJECT HELL - RITHMIC DATA BRIDGE V2")
        logger.info("="*60)

        if self.config:
            logger.info(f"Account: {self.config['RITHMIC_USERNAME']}")
            logger.info(f"Gateway: {self.config['RITHMIC_GATEWAY']}")
        else:
            logger.warning("No config found - using simulation only")

        logger.info("")
        logger.info("Starting services...")

        # Start all services
        server_task = asyncio.create_task(self.start_websocket_server())
        monitor_task = asyncio.create_task(self.monitor_performance())
        connection_task = asyncio.create_task(self.try_rithmic_connection())

        logger.info("")
        logger.info("="*60)
        logger.info("  BRIDGE OPERATIONAL")
        logger.info("="*60)
        logger.info("")
        logger.info("WebSocket server: ws://0.0.0.0:9001")
        logger.info("Data: High-fidelity Level 3 MBO simulation")
        logger.info("Update rate: 10 Hz (10 updates per second)")
        logger.info("")
        logger.info("NOVA/AEGIS can connect to receive Level 3 data!")
        logger.info("")
        logger.info("Press Ctrl+C to stop")

        # Keep running
        try:
            await asyncio.gather(server_task, monitor_task, connection_task)
        except KeyboardInterrupt:
            logger.info("")
            logger.info("Shutting down bridge...")
            self.running = False

async def main():
    bridge = SimpleRithmicBridge()
    await bridge.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] Bridge stopped")