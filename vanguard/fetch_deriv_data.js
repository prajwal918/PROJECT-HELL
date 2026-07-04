const { WebSocketServer } = require('ws');

const server = new WebSocketServer({ host: '127.0.0.1', port: 9876 });
let cmdId = 0;
const pending = new Map();

async function send(ws, method, params = {}) {
    return new Promise((resolve, reject) => {
        const id = ++cmdId;
        const timer = setTimeout(() => {
            pending.delete(id);
            reject(new Error(`Timeout: ${method}`));
        }, 60000);
        pending.set(id, { resolve, reject, timer });
        ws.send(JSON.stringify({ id, method, params }));
    });
}

server.on('connection', async (ws) => {
    console.log("Extension connected!");
    
    ws.on('message', (data) => {
        const msg = JSON.parse(data.toString());
        const p = pending.get(msg.id);
        if (p) {
            clearTimeout(p.timer);
            pending.delete(msg.id);
            if (msg.error) p.reject(msg.error);
            else p.resolve(msg.result);
        }
    });

    try {
        // 1. Get Account ID
        console.log("Navigating to DTrader...");
        await send(ws, 'navigate', { url: 'https://dtrader.deriv.com/' });
        await new Promise(r => setTimeout(r, 10000)); // Wait for load

        console.log("Extracting Account ID...");
        const accountData = await send(ws, 'execute_script', { 
            code: `(() => {
                const bal = document.querySelector('.acc-info__balance');
                if (bal) bal.click();
                return new Promise(resolve => {
                    setTimeout(() => {
                        const idEl = document.querySelector('.acc-switcher__loginid');
                        resolve(idEl ? idEl.innerText.trim() : "NOT_FOUND");
                    }, 5000);
                });
            })()`
        });
        console.log("RESULT_ACCOUNT_ID:" + JSON.stringify(accountData));

        // 2. Get/Generate PAT
        console.log("Navigating to Tokens page...");
        await send(ws, 'navigate', { url: 'https://developers.deriv.com/dashboard/tokens/' });
        await new Promise(r => setTimeout(r, 10000));

        console.log("Generating/Extracting Token...");
        const tokenData = await send(ws, 'execute_script', {
            code: `(() => {
                const nameInput = document.querySelector('input[placeholder="Token name"]');
                if (!nameInput) return "PAGE_NOT_READY";
                
                // Check Read and Trade
                document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                    if (cb.value === 'read' || cb.value === 'trade' || cb.nextElementSibling?.innerText.includes("Read") || cb.nextElementSibling?.innerText.includes("Trade")) {
                        if (!cb.checked) cb.click();
                    }
                });
                
                nameInput.value = 'Vanguard' + Math.floor(Math.random()*1000);
                const btns = Array.from(document.querySelectorAll('button'));
                const createBtn = btns.find(b => b.innerText.includes('Create'));
                if (createBtn) createBtn.click();
                
                return new Promise(resolve => {
                    setTimeout(() => {
                        const table = document.querySelector('.token-table') || document.querySelector('table');
                        if (table) {
                             const rows = table.querySelectorAll('tbody tr');
                             if (rows.length > 0) resolve(rows[0].innerText);
                        }
                        resolve("TOKEN_NOT_VISIBLE");
                    }, 5000);
                });
            })()`
        });
        console.log("RESULT_TOKEN_DATA:" + JSON.stringify(tokenData));
        
        process.exit(0);

    } catch (e) {
        console.error("Error:", e);
        process.exit(1);
    }
});

console.log("Waiting for extension on port 9876...");
