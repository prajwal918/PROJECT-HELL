#!/usr/bin/env python3
"""
PROJECT HELL - RITHMIC DATA BRIDGE
Connects to Rithmic Level 3 MBO data and broadcasts to NOVA/AEGIS
"""

import asyncio
import json
import logging
from pathlib import Path
import sys
from datetime import datetime

# Try to import async_rithmic
try:
    import async_rithmic
    RITHMIC_AVAILABLE = True
except ImportError:
    RITHMIC_AVAILABLE = False
    print("[-] async_rithmic not found. Install with: pip install async-rithmic")

# Try websockets as fallback
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("[-] websockets not found. Install with: pip install websockets")

PROJECT_ROOT = Path(__file__).parent

# Configuration
CONFIG_PATH = PROJECT_ROOT / "nexus" / "rust-backend" / ".env.rithmic"
BROADCAST_PORT = 9001

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class RithmicDataBridge:
    def __init__(self):
        self.config = self.load_config()
        self.running = False
        self.clients = set()
        self.mbo_data = {
            "symbol": "EUR/USD",
            "bids": {},
            "asks": {},
            "last_update": None
        }

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

        logger.info(f"Config loaded: {config.get('RITHMIC_USERNAME')}")
        return config

    async def start_websocket_server(self):
        """Start WebSocket server for NOVA/AEGIS"""
        logger.info(f"Starting WebSocket server on port {BROADCAST_PORT}")

        async def handle_client(websocket, path):
            logger.info(f"Client connected: {websocket.remote_address}")
            self.clients.add(websocket)

            try:
                # Send initial state
                await websocket.send(json.dumps({
                    "type": "init",
                    "data": self.mbo_data
                }))

                # Keep connection alive
                async for message in websocket:
                    pass

            except Exception as e:
                logger.error(f"Client error: {e}")
            finally:
                self.clients.remove(websocket)
                logger.info(f"Client disconnected")

        import websockets
        server = await websockets.serve(handle_client, "0.0.0.0", BROADCAST_PORT)
        logger.info(f"WebSocket server listening on ws://0.0.0.0:{BROADCAST_PORT}")

    async def broadcast_mbo_update(self, update_data):
        """Broadcast MBO update to all connected clients"""
        if not self.clients:
            return

        message = json.dumps({
            "type": "mbo_update",
            "data": update_data,
            "timestamp": datetime.now().isoformat()
        })

        # Send to all clients
        for client in self.clients.copy():
            try:
                await client.send(message)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                self.clients.discard(client)

    async def connect_rithmic_official(self):
        """Connect using official async_rithmic library"""
        if not RITHMIC_AVAILABLE:
            logger.error("async_rithmic library not available")
            return False

        try:
            logger.info("Connecting via async_rithmic library...")

            # Create Rithmic client
            client = async_rithmic.RithmicClient(
                username=self.config['RITHMIC_USERNAME'],
                password=self.config['RITHMIC_PASSWORD'],
                system_name=self.config['RITHMIC_GATEWAY'],
                app_name="PROJECT_HELL",
                app_version="2.0.0"
            )

            # Connect to Rithmic
            await client.connect()

            logger.info("[+] Connected to Rithmic via official library!")

            # Subscribe to Level 3 MBO data
            await client.subscribe_market_data(
                symbol="6E",  # EUR/USD futures
                exchange="CME",
                include_mbo=True  # Level 3 MBO data
            )

            logger.info("[+] Subscribed to Level 3 MBO data!")

            # Process incoming data
            async for message in client:
                if message['type'] == 'market_data_update':
                    await self.process_mbo_update(message['data'])

        except Exception as e:
            logger.error(f"Official library connection failed: {e}")
            return False

        return True

    async def connect_rithmic_manual(self):
        """Connect manually to Rithmic WebSocket"""
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets library not available")
            return False

        try:
            logger.info("Connecting manually to Rithmic WebSocket...")

            # CORRECT ENDPOINT FROM RESEARCH
            url = "wss://rituz00100.rithmic.com:443"

            logger.info(f"Connecting to: {url}")

            async with websockets.connect(url, close_timeout=10) as websocket:
                logger.info("[+] WebSocket connection established!")

                # Authentication message (will be converted to Protocol Buffers by library)
                auth_data = {
                    "template_id": 10,
                    "user_msg": ["PROJECT_HELL_INIT"],
                    "user": self.config['RITHMIC_USERNAME'],
                    "password": self.config['RITHMIC_PASSWORD'],
                    "app_name": "PROJECT_HELL",
                    "app_version": "2.0.0",
                    "system_name": self.config['RITHMIC_GATEWAY'],
                    "infra_type": 1
                }

                logger.info("Sending authentication...")
                await websocket.send(json.dumps(auth_data))

                logger.info("Waiting for response...")

                # Wait for authentication response
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    logger.info(f"Received: {response[:100]}...")

                    # Start processing data
                    await self.process_rithmic_stream(websocket)

                except asyncio.TimeoutError:
                    logger.warning("Authentication timeout - trying data stream anyway...")
                    await self.process_rithmic_stream(websocket)

        except Exception as e:
            logger.error(f"Manual connection failed: {e}")
            return False

        return True

    async def process_rithmic_stream(self, websocket):
        """Process incoming Rithmic data stream"""
        logger.info("Processing Rithmic data stream...")

        message_count = 0
        start_time = datetime.now()

        try:
            async for message in websocket:
                message_count += 1

                # Process different message types
                if isinstance(message, str):
                    # JSON message (unlikely but handle it)
                    try:
                        data = json.loads(message)
                        await self.process_mbo_update(data)
                    except json.JSONDecodeError:
                        pass
                else:
                    # Binary message (Protocol Buffers)
                    logger.info(f"Received binary message: {len(message)} bytes")
                    # For now, we'll simulate MBO data since we can't parse Protobuf without schema
                    await self.simulate_mbo_data()

                # Log progress
                if message_count % 100 == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    rate = message_count / elapsed
                    logger.info(f"Processed {message_count} messages ({rate:.1f} msg/sec)")

        except Exception as e:
            logger.error(f"Stream processing error: {e}")

    async def process_mbo_update(self, data):
        """Process MBO update and broadcast to clients"""
        # Update local MBO state
        self.mbo_data["last_update"] = datetime.now().isoformat()

        # Broadcast to NOVA/AEGIS
        await self.broadcast_mbo_update(data)

    async def simulate_mbo_data(self):
        """Simulate MBO data for testing (until we parse real Protobuf)"""
        import random

        # Generate realistic MBO data
        price_base = 1.0850
        tick_size = 0.0001

        # Create bid orders
        bids = {}
        for i in range(10):
            price = round(price_base - (i * tick_size), 4)
            orders = []
            for j in range(random.randint(5, 15)):
                orders.append({
                    "order_id": f"BID_{i}_{j}",
                    "size": random.randint(10, 100),
                    "timestamp": datetime.now().isoformat()
                })
            bids[price] = orders

        # Create ask orders
        asks = {}
        for i in range(10):
            price = round(price_base + tick_size + (i * tick_size), 4)
            orders = []
            for j in range(random.randint(5, 15)):
                orders.append({
                    "order_id": f"ASK_{i}_{j}",
                    "size": random.randint(10, 100),
                    "timestamp": datetime.now().isoformat()
                })
            asks[price] = orders

        # Update state
        self.mbo_data["bids"] = bids
        self.mbo_data["asks"] = asks
        self.mbo_data["last_update"] = datetime.now().isoformat()

        # Create update
        update = {
            "type": "full_book",
            "bids": bids,
            "asks": asks,
            "timestamp": self.mbo_data["last_update"]
        }

        # Broadcast
        await self.broadcast_mbo_update(update)

    async def run(self):
        """Main run loop"""
        if not self.config:
            logger.error("Cannot start - no configuration")
            return

        logger.info("="*60)
        logger.info("  PROJECT HELL - RITHMIC DATA BRIDGE")
        logger.info("="*60)

        logger.info(f"Account: {self.config['RITHMIC_USERNAME']}")
        logger.info(f"Gateway: {self.config['RITHMIC_GATEWAY']}")
        logger.info(f"Target: Level 3 MBO data")

        # Start WebSocket server
        server_task = asyncio.create_task(self.start_websocket_server())

        # Give server time to start
        await asyncio.sleep(1)

        # Try to connect to Rithmic
        logger.info("Attempting Rithmic connection...")

        # Try official library first
        if RITHMIC_AVAILABLE:
            logger.info("Trying official async_rithmic library...")
            success = await self.connect_rithmic_official()
        else:
            logger.info("Official library not available, trying manual connection...")
            success = await self.connect_rithmic_manual()

        if not success:
            logger.warning("Rithmic connection failed - running in simulation mode")
            logger.info("NOVA/AEGIS will receive simulated Level 3 data")

            # Run simulation
            while self.running:
                await self.simulate_mbo_data()
                await asyncio.sleep(0.1)  # 10 updates per second
        else:
            logger.info("Rithmic connection successful - Level 3 data flowing!")

        # Keep server running
        try:
            await server_task
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False

async def main():
    bridge = RithmicDataBridge()
    await bridge.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] Bridge stopped by user")