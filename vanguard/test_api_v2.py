import asyncio
import json
import websockets
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN", "")
DERIV_APP_ID = os.getenv("DERIV_APP_ID", "1089")

async def test_deriv_v2():
    if not DERIV_API_TOKEN:
        print("❌ Error: No DERIV_API_TOKEN found in .env")
        return

    print("🔐 Attempting REST Authentication to get OTP...")
    # Using a placeholder account ID for now, as the new flow requires it.
    # Usually, we need to fetch accounts first. Let's see if there's a generic way.
    
    headers = {
        "Authorization": f"Bearer {DERIV_API_TOKEN}",
        "Deriv-App-ID": DERIV_APP_ID
    }
    
    # We might need to get the account ID first. Let's try the generic WebSocket approach 
    # to see if the old V3 endpoint is still somewhat active for basic authorize.
    url = f"wss://ws.binaryws.com/websockets/v3?app_id={DERIV_APP_ID}"
    print(f"Testing direct V3 authorize with PAT just in case...")
    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"authorize": DERIV_API_TOKEN}))
            auth_resp = json.loads(await ws.recv())
            print("Response:", auth_resp)
    except Exception as e:
         print(f"❌ Connection Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_deriv_v2())
