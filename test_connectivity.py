import asyncio
import ssl
import websockets

URLS = [
    "wss://rituz00100.rithmic.com:443",
    "wss://ritmz01001.01.rithmic.com:443",
    "wss://ritmz01002.01.rithmic.com:443",
]

async def test_url(url):
    print(f"[TEST] {url} ...", end=" ", flush=True)
    try:
        ctx = ssl.create_default_context()
        ws = await asyncio.wait_for(
            websockets.connect(url, ssl=ctx),
            timeout=10
        )
        print("CONNECTED")
        await ws.close()
        return True
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        return False

async def main():
    for url in URLS:
        await test_url(url)

asyncio.run(main())
