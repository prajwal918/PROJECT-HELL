import asyncio
import json
import websockets
import os
from dotenv import load_dotenv

load_dotenv()

DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN", "")
DERIV_APP_ID = "1089"

async def find_vrtc():
    if not DERIV_API_TOKEN:
        print("Error: No token found")
        return

    # Try standard WebSocket authorize first
    url = f"wss://ws.binaryws.com/websockets/v3?app_id={DERIV_APP_ID}"
    try:
        async with websockets.connect(url) as ws:
            print("Connected to WebSocket, authorizing...")
            await ws.send(json.dumps({"authorize": DERIV_API_TOKEN}))
            resp = json.loads(await ws.recv())
            
            if "error" in resp:
                print(f"Auth failed: {resp['error']['message']}")
                return

            # Success! Let's find the VRTC account
            print("Authorized! Looking for accounts...")
            
            # The authorize response contains the main account
            main_id = resp['authorize']['loginid']
            print(f"Main Account: {main_id}")
            
            # Request account list to find all IDs
            await ws.send(json.dumps({"get_account_list": 1}))
            list_resp = json.loads(await ws.recv())
            
            if "get_account_list" in list_resp:
                for acc in list_resp["get_account_list"]:
                    print(f"Found: {acc['loginid']} ({acc['account_type']})")
                    if acc['loginid'].startswith("VRTC"):
                        print(f"RESULT_VRTC:{acc['loginid']}")
            else:
                # If only one account, check if it's VRTC
                if main_id.startswith("VRTC"):
                    print(f"RESULT_VRTC:{main_id}")

    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(find_vrtc())
