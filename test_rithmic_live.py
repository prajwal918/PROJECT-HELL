import asyncio
import sys
from async_rithmic import RithmicClient

USERNAME = "poteljdjdjxiusus@gmail.com"
PASSWORD = "fbb6x4u2af9"
SYSTEM_NAME = "Rithmic Paper Trading"
APP_NAME = "pojd:NEXUS_L3_TEST"
APP_VERSION = "1.0.0"

tick_count = 0
mbo_count = 0
book_count = 0

async def on_tick(data):
    global tick_count
    tick_count += 1
    if tick_count <= 3:
        dtype = data.get("data_type", "?")
        symbol = data.get("symbol", "?")
        print(f"[TICK #{tick_count}] type={dtype} symbol={symbol}")

async def on_order_book(book):
    global book_count
    book_count += 1
    if book_count <= 3:
        symbol = getattr(book, 'symbol', '?')
        print(f"[BOOK #{book_count}] symbol={symbol}")

async def on_market_depth(depth):
    global mbo_count
    mbo_count += 1
    if mbo_count <= 3:
        symbol = getattr(depth, 'symbol', '?')
        print(f"[MBO #{mbo_count}] symbol={symbol}")

async def on_connected(plant_type):
    print(f"[CONNECTED] {plant_type}")

async def on_disconnected(plant_type):
    print(f"[DISCONNECTED] {plant_type}")

async def main():
    print("[TEST] Creating RithmicClient for L3 MBO...")
    client = RithmicClient(
        user=USERNAME,
        password=PASSWORD,
        system_name=SYSTEM_NAME,
        app_name=APP_NAME,
        app_version=APP_VERSION,
        url="wss://rprotocol.rithmic.com:443",
    )

    client.on_connected += on_connected
    client.on_disconnected += on_disconnected
    client.on_tick += on_tick
    client.on_order_book += on_order_book
    client.on_market_depth += on_market_depth

    print("[TEST] Connecting all plants...")
    try:
        await client.connect()
        print("[TEST] Connected! Authenticated across all plants.")

        # Get front month contract for ES
        print("[TEST] Getting front month ES contract...")
        try:
            es_contract = await client.get_front_month_contract("ES", "CME")
            print(f"[TEST] ES front month: {es_contract}")
        except Exception as e:
            print(f"[TEST] Could not get ES contract: {e}")
            es_contract = "ESU6"

        # Subscribe to Level 3 MBO (market depth by order)
        print(f"[TEST] Subscribing to L3 MBO for {es_contract}@CME...")
        await client.subscribe_to_market_depth(es_contract, "CME", 0)
        print("[TEST] L3 MBO subscription sent. Listening for 30 seconds...")

        # Also subscribe to market data (trades + BBO)
        from async_rithmic.enums import DataType
        await client.subscribe_to_market_data(es_contract, "CME", DataType.LAST_TRADE | DataType.BBO)
        print(f"[TEST] Subscribed to trades + BBO for {es_contract}")

        # Wait for data
        await asyncio.sleep(300)

        print(f"\n=== RESULTS ===")
        print(f"Ticks (Trades+BBO): {tick_count}")
        print(f"Order Books (L2):   {book_count}")
        print(f"MBO (Level 3):      {mbo_count}")

        if mbo_count > 0:
            print("\n[PASS] Level 3 MBO data received! Rithmic is working.")
        else:
            print("\n[WARN] No MBO data received. Check market hours or contract.")

    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            await client.disconnect()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())