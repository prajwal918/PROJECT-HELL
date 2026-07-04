#!/usr/bin/env python3
"""
QUICK TEST: Use this immediately after EdgeClear support call
Replace the WebSocket URL with what they provide
"""

import asyncio
import json
import websockets
from pathlib import Path

# LOAD CREDENTIALS
PROJECT_ROOT = Path(__file__).parent
config_path = PROJECT_ROOT / "nexus" / "rust-backend" / ".env.rithmic"

config = {}
with open(config_path, 'r') as f:
    for line in f:
        line = line.strip()
        if line and '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip()

# ========================================
# REPLACE THIS URL WITH WHAT SUPPORT GIVES YOU
# ========================================
WEBSOCKET_URL = "wss://rithmic.rapi.com:443"  # ← CHANGE THIS!

async def test_endpoint():
    print("\n" + "="*60)
    print("  QUICK RITHMIC API TEST")
    print("="*60)
    
    print(f"\n[*] Testing URL: {WEBSOCKET_URL}")
    print(f"[*] Account: {config['RITHMIC_USERNAME']}")
    print(f"[*] Gateway: {config['RITHMIC_GATEWAY']}")
    
    try:
        print("\n[*] Connecting...")
        async with websockets.connect(WEBSOCKET_URL, close_timeout=10) as websocket:
            print("[+] WebSocket CONNECTED!")
            
            # Try authentication
            auth_msg = {
                "user": config['RITHMIC_USERNAME'],
                "password": config['RITHMIC_PASSWORD'],
                "gateway": config['RITHMIC_GATEWAY'],
                "app_name": "NEXUS",
                "app_version": "2.0.0",
                "requestId": 1
            }
            
            print("\n[*] Sending authentication...")
            await websocket.send(json.dumps(auth_msg))
            
            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"\n[+] Response received:")
                print(f"    {response}")
                
                try:
                    response_data = json.loads(response)
                    if response_data.get("status") == "OK" or response_data.get("success") == True:
                        print("\n" + "="*60)
                        print("  *** SUCCESS! ***")
                        print("="*60)
                        print("\n[+] Rithmic API is WORKING!")
                        print(f"[+] Endpoint: {WEBSOCKET_URL}")
                        print("\nNext steps:")
                        print("1. Update nexus/rust-backend/src/rithmic.rs with this URL")
                        print("2. Run: python update_rithmic_config.py")
                        print("3. Compile NEXUS backend on Linux")
                        return True
                    else:
                        print(f"\n[-] Authentication failed")
                        print(f"    Response: {response_data}")
                except json.JSONDecodeError:
                    print(f"\n[-] Invalid JSON response")
                    
            except asyncio.TimeoutError:
                print("\n[-] Authentication timeout")
                
    except Exception as e:
        print(f"\n[-] Connection failed: {e}")
        print("\nPossible issues:")
        print("1. URL is still incorrect")
        print("2. Account not enabled for API")
        print("3. Authentication format wrong")
        print("4. Network/firewall issue")
    
    return False

async def main():
    print("\n" + "="*60)
    print("  INSTRUCTIONS")
    print("="*60)
    
    print("\n1. Get correct URL from EdgeClear support")
    print("2. Edit this file: update WEBSOCKET_URL on line 22")
    print("3. Run this script: python quick_test_after_support.py")
    print("4. If SUCCESS: Continue to next steps")
    print("5. If FAILED: Call support back with error message")
    
    input("\nPress Enter to start testing...")
    
    success = await test_endpoint()
    
    if success:
        print("\n[+] SUCCESS! Ready to proceed with NEXUS compilation.")
    else:
        print("\n[-] FAILED. Check the error above and call support again.")

if __name__ == "__main__":
    asyncio.run(main())