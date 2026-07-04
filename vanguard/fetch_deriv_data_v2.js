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
        console.log("1. Navigating to account-settings...");
        await send(ws, 'navigate', { url: 'https://app.deriv.com/account/personal-details' });
        await new Promise(r => setTimeout(r, 10000));
        
        console.log("2. Grabbing Account ID from DOM...");
        const accountId = await send(ws, 'execute_script', { 
            code: `(document.querySelector('.acc-info__loginid') || document.querySelector('.account-id') || {innerText: 'NOT_FOUND'}).innerText` 
        });
        console.log("FINAL_ID:" + accountId);

        console.log("3. Navigating to Token page...");
        await send(ws, 'navigate', { url: 'https://app.deriv.com/account/api-token' });
        await new Promise(r => setTimeout(r, 10000));

        console.log("4. Scraping existing tokens...");
        const tokens = await send(ws, 'execute_script', {
            code: `Array.from(document.querySelectorAll('tr')).map(r => r.innerText).join('|')`
        });
        console.log("FINAL_TOKENS:" + tokens);

        process.exit(0);
    } catch (e) {
        console.error("Error:", e);
        process.exit(1);
    }
});
