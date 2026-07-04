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

# Load environment from .env file manually
def load_env():
    env_path = Path("/home/jogi999/PROJECT HELL/overseer/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

load_env()

async def main():
    user = os.getenv("RITHMIC_USER")
    password = os.getenv("RITHMIC_PASSWORD")
    system_name = os.getenv("RITHMIC_SYSTEM_NAME", "Rithmic Test")
    url = os.getenv("RITHMIC_URL", "wss://rituz00100.rithmic.com:443")
    
    print(f"User: {user}")
    print(f"System: {system_name}")
    print(f"URL: {url}")
    
    gateway = Gateway.TEST
    if "rituz00100" in url:
        gateway = Gateway.TEST
    elif "rprotocol" in url:
        gateway = Gateway.CHICAGO
        
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
    await client.connect()
    print("Connected!")
    
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

if __name__ == "__main__":
    asyncio.run(main())
