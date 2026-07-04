import asyncio
import json
import websockets
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DERIV_API_TOKEN")

async def test():
    # Try different authorization formats for pat_ token on the V3 websocket
    url = f"wss://ws.binaryws.com/websockets/v3?app_id=1089"
    async with websockets.connect(url) as ws:
        
        # Test 1: Standard authorize
        print("Test 1: Standard")
        await ws.send(json.dumps({"authorize": token}))
        print(await ws.recv())

        # Test 2: Stripping pat_
        print("\nTest 2: Stripped pat_")
        if token.startswith("pat_"):
            stripped = token[4:]
            await ws.send(json.dumps({"authorize": stripped}))
            print(await ws.recv())

        # Test 3: OAuth format?
        print("\nTest 3: Bearer")
        await ws.send(json.dumps({"authorize": f"Bearer {token}"}))
        print(await ws.recv())

asyncio.run(test())
