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

async def test_system(gateway, system_name):
    user = "fghfgh2626"
    password = "4125c893"
    
    print(f"\n--- Testing Gateway: '{gateway.name}' ({gateway.value}) System: '{system_name}' ---")
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
        print(f"SUCCESS: Connected with gateway '{gateway.name}' system '{system_name}'!")
        await client.disconnect()
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False

async def main():
    gateways = [Gateway.CHICAGO, Gateway.TEST]
    systems = ["Rithmic Paper Trading", "Rithmic Test", "Rithmic"]
    
    for gw in gateways:
        for sys_name in systems:
            success = await test_system(gw, sys_name)
            if success:
                print(f"Connection FOUND: Gateway: {gw}, System: {sys_name}")
                return

if __name__ == "__main__":
    asyncio.run(main())
