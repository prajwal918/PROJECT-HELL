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

async def test_system(system_name):
    user = "fghfgh2626"
    password = "4125c893"
    url = "wss://rituz00100.rithmic.com:443"
    gateway = Gateway.TEST
    
    print(f"\n--- Testing System Name: '{system_name}' ---")
    client = RithmicClient(
        user=user,
        password=password,
        system_name=system_name,
        app_name="OVERSEER",
        app_version="12.0",
        gateway=gateway
    )
    
    try:
        await client.connect()
        print(f"SUCCESS: Connected with system '{system_name}'!")
        await client.disconnect()
        return True
    except Exception as e:
        print(f"FAILED for system '{system_name}': {e}")
        return False

async def main():
    systems = ["Rithmic Test", "Rithmic Paper Trading", "Rithmic 01", "Rithmic"]
    for sys_name in systems:
        success = await test_system(sys_name)
        if success:
            break

if __name__ == "__main__":
    asyncio.run(main())
