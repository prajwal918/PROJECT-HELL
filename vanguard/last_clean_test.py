import asyncio
import json
import websockets

async def test():
    token = "pat_f0137fefe3092d476468e51af5e3f69bd78168ae6530949f45daaf608bc68e58"
    app_ids = ["1", "1089", "16929"]
    
    for app_id in app_ids:
        print(f"Testing App ID {app_id}...")
        try:
            url = f"wss://ws.binaryws.com/websockets/v3?app_id={app_id}"
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"authorize": token}))
                resp = json.loads(await ws.recv())
                print(f"  Response: {resp}")
        except Exception as e:
            print(f"  Error: {e}")

asyncio.run(test())
