#!/usr/bin/env python3
"""
Rithmic API Connection Test
Tests if Rithmic Level 3 API is working
"""

import asyncio
import json
import websockets
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
RITHMIC_ENV = PROJECT_ROOT / "nexus" / "rust-backend" / ".env.rithmic"

def load_rithmic_config():
    """Load Rithmic credentials"""
    # Try multiple possible paths
    possible_paths = [
        PROJECT_ROOT / "nexus" / "rust-backend" / ".env.rithmic",
        PROJECT_ROOT / ".env.rithmic",
        Path("C:\\Users\\jogip\\OneDrive\\Desktop\\PROJECT HELL\\nexus\\rust-backend\\.env.rithmic"),
    ]
    
    rithmic_env = None
    for path in possible_paths:
        if path.exists():
            rithmic_env = path
            break
    
    if not rithmic_env:
        print("[-] Rithmic config file not found")
        print(f"  Tried paths:")
        for path in possible_paths:
            print(f"    - {path}")
        return None

    config = {}
    with open(rithmic_env, 'r') as f:
        for line in f:
            line = line.strip()
            if line and '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()

    required_keys = ['RITHMIC_USERNAME', 'RITHMIC_PASSWORD', 'RITHMIC_GATEWAY']
    missing = [k for k in required_keys if k not in config]

    if missing:
        print(f"[-] Missing Rithmic config keys: {missing}")
        return None

    return config

async def test_rithmic_websocket(config):
    """Test Rithmic WebSocket connection"""
    print("\n" + "="*60)
    print("  RITHMIC API CONNECTION TEST")
    print("="*60)

    print("\n[*] Configuration:")
    print(f"  Username: {config['RITHMIC_USERNAME']}")
    print(f"  Gateway: {config['RITHMIC_GATEWAY']}")
    print(f"  App Name: NEXUS")
    print(f"  App Version: 2.0.0")

    print("\n[*] Testing Rithmic WebSocket connection...")

    # Try multiple Rithmic WebSocket endpoints
    possible_urls = [
        "wss://rithmic.rapi.com:443",
        "wss://api.rithmic.com:443",
        "wss://rithmic.com:443",
        "wss://rithmic.com/ws",
        "wss://wss.rithmic.com:443"
    ]

    for ws_url in possible_urls:
        try:
            print(f"[*] Connecting to: {ws_url}")

            async with websockets.connect(ws_url) as websocket:
                print("[+] WebSocket connection established!")

                # Send login message (matching Rithmic Rust client format)
                login_msg = {
                    "user": config['RITHMIC_USERNAME'],
                    "password": config['RITHMIC_PASSWORD'],
                    "gateway": config['RITHMIC_GATEWAY'],
                    "app_name": "NEXUS",
                    "app_version": "2.0.0",
                    "requestId": 1
                }

                print("[*] Sending login request...")
                await websocket.send(json.dumps(login_msg))

                # Wait for response
                response = await websocket.recv()
                print(f"[+] Received response: {response}")

                # Parse response
                try:
                    response_data = json.loads(response)
                    if response_data.get("status") == "OK":
                        print("\n[+] Rithmic API login SUCCESSFUL")
                        print("[+] Level 3 API is WORKING")
                        return True
                    else:
                        print(f"\n[-] Rithmic API login FAILED: {response_data}")
                        return False
                except json.JSONDecodeError:
                    print(f"\n[-] Invalid response format: {response}")
                    return False

        except OSError as e:
            print(f"[-] Connection failed for {ws_url}: {e}")
            continue
        except Exception as e:
            print(f"[-] Unexpected error for {ws_url}: {e}")
            continue

async def check_rithmic_alternative_methods():
    """Check alternative methods to verify Rithmic API"""
    print("\n" + "="*60)
    print("  ALTERNATIVE VERIFICATION METHODS")
    print("="*60)

    methods = [
        ("1", "Rithmic Test Website", "https://test.rithmic.com"),
        ("2", "Rithmic Web Console", "https://rithmic.com/console"),
        ("3", "Rithmic API Documentation", "https://rithmic.com/api-docs"),
    ]

    print("\nTo verify Rithmic API manually:")
    for num, name, url in methods:
        print(f"\n{num}. {name}")
        print(f"   URL: {url}")

async def main():
    print("\n" + "="*60)
    print("  RITHMIC LEVEL 3 API TEST")
    print("="*60)

    # Load configuration
    config = load_rithmic_config()
    if not config:
        print("\n[-] Cannot test - Rithmic configuration missing")
        await check_rithmic_alternative_methods()
        return

    # Test WebSocket connection
    success = await test_rithmic_websocket(config)

    if not success:
        print("\n" + "="*60)
        print("  DIAGNOSTIC INFORMATION")
        print("="*60)

        print("\nPossible issues:")
        print("1. Rithmic WebSocket URL is incorrect")
        print("2. Network connection to Rithmic servers is blocked")
        print("3. Rithmic account credentials are invalid")
        print("4. Rithmic API service is temporarily unavailable")
        print("5. Rithmic account not activated for API access")

        print("\nRecommended actions:")
        print("1. Contact Rithmic support to verify API access")
        print("2. Check Rithmic account status at: https://rithmic.com")
        print("3. Verify account is activated and API permissions are granted")
        print("4. Test connection from a different network/location")

        await check_rithmic_alternative_methods()
    else:
        print("\n" + "="*60)
        print("  SUCCESS")
        print("="*60)
        print("\n[+] Rithmic Level 3 API is working")
        print("[+] Ready to compile NEXUS backend")

if __name__ == "__main__":
    asyncio.run(main())