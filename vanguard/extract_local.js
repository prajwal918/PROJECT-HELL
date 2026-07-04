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
        }, 30000);
        pending.set(id, { resolve, reject, timer });
        ws.send(JSON.stringify({ id, method, params }));
    });
}
server.on('connection', async (ws) => {
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
        console.log("Navigating to app.deriv.com...");
        await send(ws, 'navigate', { url: 'https://app.deriv.com/' });
        await new Promise(r => setTimeout(r, 10000));
        
        console.log("Extracting localStorage...");
        const result = await send(ws, 'execute_script', { 
            code: `localStorage.getItem('client.accounts')` 
        });
        console.log("STORAGE_DATA:" + JSON.stringify(result));
        process.exit(0);
    } catch (e) {
        process.exit(1);
    }
});
