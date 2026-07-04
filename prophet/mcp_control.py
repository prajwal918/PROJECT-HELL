import asyncio
import json
import websockets
import sys

async def control_browser():
    print("Starting WebSocket server on 127.0.0.1:9876...")
    async with websockets.serve(None, "127.0.0.1", 9876) as server:
        print("Waiting for Agent360 extension to connect...")
        # server.websockets is a set of connected clients
        
        ws = None
        while not ws:
            await asyncio.sleep(0.5)
            if server.websockets:
                ws = list(server.websockets)[0]
        
        print("✅ Extension connected!")
        
        async def send_cmd(method, params={}):
            cmd_id = 1
            msg = {"id": cmd_id, "method": method, "params": params}
            await ws.send(json.dumps(msg))
            # Wait for response
            while True:
                resp_text = await ws.recv()
                resp = json.loads(resp_text)
                if resp.get("id") == cmd_id:
                    return resp.get("result")

        try:
            print("1. Navigating to DTrader...")
            await send_cmd("navigate", {"url": "https://dtrader.deriv.com/"})
            await asyncio.sleep(10)
            
            print("2. Extracting Account ID...")
            script = """
            (() => {
                const bal = document.querySelector('.acc-info__balance');
                if (bal) bal.click();
                return new Promise(resolve => {
                    setTimeout(() => {
                        const idEl = document.querySelector('.acc-switcher__loginid');
                        resolve(idEl ? idEl.innerText.trim() : "NOT_FOUND");
                    }, 3000);
                });
            })()
            """
            acc_id = await send_cmd("execute_script", {"code": script})
            print(f"RESULT_ACCOUNT_ID:{acc_id}")

            print("3. Navigating to Tokens...")
            await send_cmd("navigate", {"url": "https://developers.deriv.com/dashboard/tokens/"})
            await asyncio.sleep(8)
            
            print("4. Creating 100% Token...")
            token_script = """
            (() => {
                const nameInput = document.querySelector('input[placeholder="Token name"]');
                if (!nameInput) return "PAGE_ERROR";
                
                // Check all boxes
                document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                    if (!cb.checked) cb.click();
                });
                
                nameInput.value = 'Prophet' + Math.floor(Math.random()*1000);
                const btns = Array.from(document.querySelectorAll('button'));
                const createBtn = btns.find(b => b.innerText.includes('Create'));
                if (createBtn) createBtn.click();
                
                return new Promise(resolve => {
                    setTimeout(() => {
                        const row = document.querySelector('.token-table tbody tr');
                        resolve(row ? row.innerText : "GENERATING");
                    }, 5000);
                });
            })()
            """
            token_data = await send_cmd("execute_script", {"code": token_script})
            print(f"RESULT_TOKEN_DATA:{token_data}")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            print("Done.")
            sys.exit(0)

if __name__ == "__main__":
    asyncio.run(control_browser())
