import asyncio
import json
import websockets
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DERIV_API_TOKEN")

async def test():
    # Try the modern API websocket endpoint
    url = f"wss://api.derivws.com/ws/real?app_id=1089"
    print(f"Testing {url}")
    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"authorize": token}))
            resp = json.loads(await ws.recv())
            print(resp)
    except Exception as e:
        print(f"Error connecting: {e}")

asyncio.run(test())
