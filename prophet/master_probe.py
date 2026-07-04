import asyncio
import json
import websockets
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DERIV_API_TOKEN")

async def master_probe():
    # Common and official Deriv App IDs
    app_ids = ["1", "1089", "16929", "19111", "21156", "31063", "36307", "16545", "29864", "50394"]
    
    print(f"Starting Master Probe with token: {token[:10]}...")
    
    for app_id in app_ids:
        url = f"wss://ws.binaryws.com/websockets/v3?app_id={app_id}"
        print(f"Testing App ID {app_id}...")
        try:
            async with websockets.connect(url, timeout=10) as ws:
                # 1. Authorize
                await ws.send(json.dumps({"authorize": token}))
                resp = json.loads(await ws.recv())
                
                if "error" in resp:
                    print(f"  ❌ Auth failed: {resp['error']['message']}")
                    continue
                
                print(f"  ✅ SUCCESS with App ID {app_id}!")
                auth_data = resp['authorize']
                main_acc = auth_data['loginid']
                print(f"  Authorized as: {auth_data.get('fullname', 'User')}")
                print(f"  Main Account: {main_acc}")

                # 2. Get all accounts to find VRTC
                await ws.send(json.dumps({"get_account_list": 1}))
                list_resp = json.loads(await ws.recv())
                
                vrtc_id = None
                if "get_account_list" in list_resp:
                    for acc in list_resp["get_account_list"]:
                        print(f"  Found: {acc['loginid']} ({acc['account_type']})")
                        if acc['loginid'].startswith("VRTC"):
                            vrtc_id = acc['loginid']
                
                final_id = vrtc_id if vrtc_id else main_acc
                print(f"\nFinal Selection for PROPHET: {final_id}")
                
                # Update .env
                with open(".env", "r") as f:
                    lines = f.readlines()
                
                with open(".env", "w") as f:
                    for line in lines:
                        if line.startswith("DERIV_APP_ID="):
                            f.write(f"DERIV_APP_ID={app_id}\n")
                        elif line.startswith("ASSET="):
                            # Ensure we have the asset line but don't overwrite if it exists
                            f.write(line)
                        else:
                            f.write(line)
                    # Append Account ID if not there
                    f.write(f"\n# Auto-discovered ID\nDERIV_ACCOUNT_ID={final_id}\n")

                print(f"RESULT_ACCOUNT:{final_id}")
                print(f"RESULT_APPID:{app_id}")
                return
                
        except Exception as e:
            print(f"  ⚠️ Error: {e}")

    print("\n❌ Master Probe failed to find a working configuration. Please ensure 'Read' permission is enabled.")

if __name__ == "__main__":
    asyncio.run(master_probe())
