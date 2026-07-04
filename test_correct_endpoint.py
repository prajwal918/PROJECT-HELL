#!/usr/bin/env python3
"""
Test Rithmic with correct domain
"""

import asyncio
import json
import ssl
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

def load_rithmic_config():
    """Load Rithmic credentials"""
    possible_paths = [
        PROJECT_ROOT / "nexus" / "rust-backend" / ".env.rithmic",
        Path("C:\\Users\\jogip\\OneDrive\\Desktop\\PROJECT HELL\\nexus\\rust-backend\\.env.rithmic"),
    ]
    
    for path in possible_paths:
        if path.exists():
            config = {}
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
            
            required_keys = ['RITHMIC_USERNAME', 'RITHMIC_PASSWORD', 'RITHMIC_GATEWAY']
            missing = [k for k in required_keys if k not in config]
            
            if not missing:
                return config
    
    return None

async def test_correct_rithmic_endpoint(config):
    """Test Rithmic with correct domain"""
    print("\n" + "="*60)
    print("  TESTING CORRECT RITHMIC ENDPOINT")
    print("="*60)

    # Try correct Rithmic endpoints
    possible_endpoints = [
        "wss://rithmic.com:443/ws",
        "wss://rithmic.com:443/api",
        "wss://rithmic.com:443/rapi",
        "wss://rithmic.com:443",
        "ws://rithmic.com:80/ws",
    ]

    print("\n[*] Configuration:")
    print(f"  Account: {config['RITHMIC_USERNAME']} (Paper Trading)")
    print(f"  Gateway: {config['RITHMIC_GATEWAY']}")

    for endpoint in possible_endpoints:
        print(f"\n[*] Testing endpoint: {endpoint}")

        try:
            import websockets

            async with websockets.connect(endpoint, close_timeout=10) as websocket:
                print(f"    [+] WebSocket connected!")

                # Try paper trading authentication
                auth_msg = {
                    "user": config['RITHMIC_USERNAME'],
                    "password": config['RITHMIC_PASSWORD'],
                    "gateway": config['RITHMIC_GATEWAY'],
                    "app_name": "NEXUS",
                    "app_version": "2.0.0",
                    "mode": "paper",
                    "requestId": 1
                }

                print(f"    [*] Sending authentication...")
                await websocket.send(json.dumps(auth_msg))

                # Wait for response with timeout
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    print(f"    [+] Received response: {response[:200]}...")

                    try:
                        response_data = json.loads(response)
                        if response_data.get("status") == "OK" or response_data.get("success") == True:
                            print(f"\n    *** SUCCESS ***")
                            print(f"    Paper trading API is WORKING!")
                            print(f"    Endpoint: {endpoint}")
                            return True
                        else:
                            print(f"    [-] Authentication failed: {response_data}")
                    except json.JSONDecodeError:
                        print(f"    [-] Invalid JSON response")

                except asyncio.TimeoutError:
                    print(f"    [-] Authentication timeout")

        except Exception as e:
            print(f"    [-] Connection failed: {e}")
            continue

    return False

async def test_tcp_connection():
    """Test TCP connection to working domain"""
    print("\n" + "="*60)
    print("  TCP CONNECTION TEST")
    print("="*60)

    import socket

    test_targets = [
        ("rithmic.com", 443, "HTTPS"),
        ("rithmic.com", 80, "HTTP"),
        ("185.230.63.107", 443, "Direct IP HTTPS"),
    ]

    for host, port, description in test_targets:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                print(f"[+] {host:20}:{port:5} ({description}) -> CONNECTED")
            else:
                print(f"[-] {host:20}:{port:5} ({description}) -> FAILED (error {result})")

        except Exception as e:
            print(f"[-] {host:20}:{port:5} ({description}) -> ERROR: {e}")

async def main():
    print("\n" + "="*60)
    print("  RITHMIC PAPER TRADING - CORRECTED ENDPOINT TEST")
    print("="*60)

    # Load configuration
    config = load_rithmic_config()
    if not config:
        print("\n[-] Cannot proceed - Rithmic configuration missing")
        return

    print("\n[+] Paper Trading Account:")
    print(f"    Username: {config['RITHMIC_USERNAME']}")
    print(f"    Gateway: {config['RITHMIC_GATEWAY']}")

    # Test TCP connectivity
    await test_tcp_connection()

    # Test correct WebSocket endpoints
    success = await test_correct_rithmic_endpoint(config)

    # Summary
    print("\n" + "="*60)
    print("  FINAL STATUS")
    print("="*60)

    if success:
        print("\n[+] SUCCESS: Rithmic Paper Trading API is WORKING!")
        print("\nNext Steps:")
        print("1. Update Rust backend with correct endpoint")
        print("2. Compile and run NEXUS backend")
        print("3. Start receiving paper trading data")
    else:
        print("\n[-] Rithmic Paper Trading API connection failed")
        print("\nPossible Issues:")
        print("1. Account not activated for API access")
        print("2. Incorrect WebSocket endpoint path")
        print("3. Paper trading account requires different setup")
        print("4. Network/firewall restrictions")

        print("\nRecommended Actions:")
        print("1. Contact EdgeClear support: 1-844-TRADE20")
        print("2. Verify paper trading API access is enabled")
        print("3. Get correct WebSocket endpoint documentation")
        print("4. Test from different network if possible")

if __name__ == "__main__":
    asyncio.run(main())