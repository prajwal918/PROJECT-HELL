#!/usr/bin/env python3
"""
PROJECT HELL - TEST NOVA/AEGIS CONNECTION TO DATA BRIDGE
"""

import asyncio
import json
import websockets

async def test_nova_connection():
    """Test NOVA connection to data bridge"""
    print("\n" + "="*60)
    print("  TESTING NOVA CONNECTION TO DATA BRIDGE")
    print("="*60)

    url = "ws://localhost:9001"

    try:
        print(f"\n[*] Connecting to: {url}")

        async with websockets.connect(url) as websocket:
            print("[+] Connected to Rithmic Data Bridge!")

            # Receive messages
            message_count = 0
            start_time = asyncio.get_event_loop().time()

            print("\n[*] Receiving Level 3 MBO data...")

            async for message in websocket:
                message_count += 1
                data = json.loads(message)

                if message_count == 1:
                    print(f"\n[+] First message type: {data.get('type')}")
                    print(f"    Content: {data.get('message', 'N/A')}")

                elif message_count == 2:
                    print(f"\n[+] Second message type: {data.get('type')}")
                    mbo_data = data.get('data', {})
                    print(f"    Symbol: {mbo_data.get('symbol')}")
                    print(f"    Best Bid: {mbo_data.get('best_bid')}")
                    print(f"    Best Ask: {mbo_data.get('best_ask')}")
                    print(f"    Spread: {mbo_data.get('spread')}")
                    print(f"    Bid Levels: {len(mbo_data.get('bids', {}))}")
                    print(f"    Ask Levels: {len(mbo_data.get('asks', {}))}")

                    print("\n[+] LEVEL 3 MBO DATA STRUCTURE:")
                    print("    BIDS:")
                    for price, info in list(mbo_data.get('bids', {}).items())[:3]:
                        print(f"      {price}: {info['total_size']} contracts ({info['order_count']} orders)")

                    print("    ASKS:")
                    for price, info in list(mbo_data.get('asks', {}).items())[:3]:
                        print(f"      {price}: {info['total_size']} contracts ({info['order_count']} orders)")

                elif message_count % 10 == 0:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    rate = message_count / elapsed
                    print(f"[*] Received {message_count} messages ({rate:.1f} msg/sec)")

                if message_count >= 20:
                    print("\n" + "="*60)
                    print("  TEST SUCCESSFUL!")
                    print("="*60)
                    print("\n[+] Data bridge is operational")
                    print("[+] Level 3 MBO data is flowing")
                    print("[+] NOVA/AEGIS can connect and receive data")
                    print("\n[+] Ready for production testing!")
                    break

    except Exception as e:
        print(f"\n[-] Connection failed: {e}")
        print("\n[-] Make sure the data bridge is running:")
        print("    python rithmic_data_bridge_v2.py")

async def main():
    await test_nova_connection()

if __name__ == "__main__":
    asyncio.run(main())