import asyncio
import json
import websockets
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DERIV_API_TOKEN")

async def test():
    # Try different websocket endpoints with the pat_ token
    urls = [
        f"wss://ws.derivws.com/websockets/v3?app_id=1089",
        f"wss://ws.binaryws.com/websockets/v3?app_id=1089",
        f"wss://api.derivws.com/websockets/v3?app_id=1089",
        f"wss://ws.derivws.com/?app_id=1089"
    ]
    
    for url in urls:
        print(f"\nTesting {url}")
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"authorize": token}))
                resp = json.loads(await ws.recv())
                print(resp)
        except Exception as e:
            print(f"Error connecting to {url}: {e}")

asyncio.run(test())
