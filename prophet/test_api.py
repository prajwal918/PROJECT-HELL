import asyncio
import json
import websockets
import os
from dotenv import load_dotenv

load_dotenv()

DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN", "")
DERIV_APP_ID = os.getenv("DERIV_APP_ID", "1089")

async def test_deriv():
    if not DERIV_API_TOKEN:
        print("❌ Error: No DERIV_API_TOKEN found in .env")
        return

    url = f"wss://ws.binaryws.com/websockets/v3?app_id={DERIV_APP_ID}"
    
    try:
        async with websockets.connect(url) as ws:
            print(f"✅ Connected to Deriv WebSocket (App ID: {DERIV_APP_ID})")
            
            # 1. Test Authentication
            print("🔐 Attempting authentication...")
            await ws.send(json.dumps({"authorize": DERIV_API_TOKEN}))
            auth_resp = json.loads(await ws.recv())
            
            if "error" in auth_resp:
                print(f"❌ Auth Error: {auth_resp['error']['message']}")
                return
                
            account = auth_resp['authorize']
            print(f"✅ Auth Success! Account: {account['loginid']} | Balance: {account['balance']} {account['currency']}")
            
            # 2. Test 5-Minute Proposal (What PROPHET actually does)
            print("\n📈 Requesting test 5-Minute CALL proposal on frxEURUSD...")
            proposal_msg = {
                "proposal": 1,
                "amount": 10.0,
                "basis": "stake",
                "contract_type": "CALL",
                "currency": "USD",
                "duration": 300,
                "duration_unit": "s",
                "symbol": "frxEURUSD"
            }
            await ws.send(json.dumps(proposal_msg))
            prop_resp = json.loads(await ws.recv())
            
            if "error" in prop_resp:
                print(f"❌ Proposal Error: {prop_resp['error']['message']}")
            else:
                prop = prop_resp['proposal']
                print(f"✅ Proposal Success!")
                print(f"   Stake: ${prop['ask_price']}")
                print(f"   Payout: ${prop['payout']}")
                print(f"   Net Profit: ${float(prop['payout']) - float(prop['ask_price']):.2f}")
                print("   This confirms Deriv accepts the exact 5-minute trade format.")
                
    except Exception as e:
        print(f"❌ Connection Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_deriv())
