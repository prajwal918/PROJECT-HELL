import asyncio
import os
import sys
import logging
from pathlib import Path

# Add the site-packages of .venv_linux to path so we can import async_rithmic
sys.path.insert(0, "/home/jogi999/PROJECT HELL/overseer/.venv_linux/lib/python3.8/site-packages")

from async_rithmic import DataType, RithmicClient
from async_rithmic.enums import Gateway

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

async def main():
    user = "desabot106@herojp.com"
    password = "fbb6x4u2af9"
    system_name = "Rithmic Paper Trading"
    gateway = Gateway.CHICAGO
    
    print(f"User: {user}")
    print(f"System: {system_name}")
    print(f"Gateway: {gateway.name} ({gateway.value})")
    
    client = RithmicClient(
        user=user,
        password=password,
        system_name=system_name,
        app_name="OVERSEER",
        app_version="12.0",
        gateway=gateway
    )
    
    async def on_tick(data):
        print("--- TICK RECEIVED ---")
        print(data)
        
    client.on_tick += on_tick
    
    print("Connecting...")
    try:
        await client.connect()
        print("SUCCESS: Connected!")
        
        # Subscribe to BBO and LAST_TRADE for 6EM6:CME
        print("Subscribing to 6EM6:CME BBO...")
        await client.subscribe_to_market_data("6EM6", "CME", DataType.BBO)
        print("Subscribing to 6EM6:CME LAST_TRADE...")
        await client.subscribe_to_market_data("6EM6", "CME", DataType.LAST_TRADE)
        
        print("Running for 15 seconds to receive ticks...")
        await asyncio.sleep(15)
        
        print("Disconnecting...")
        await client.disconnect()
        print("Done!")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(main())
