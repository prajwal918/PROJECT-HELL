const { WebSocketServer } = require('ws');
const fs = require('fs');
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
        console.log("Navigating directly to DTrader...");
        await send(ws, 'navigate', { url: 'https://dtrader.deriv.com/' });
        await new Promise(r => setTimeout(r, 20000));
        
        console.log("Getting page content...");
        const content = await send(ws, 'get_page_content', { format: 'text' });
        console.log("CONTENT_START");
        console.log(content.text);
        console.log("CONTENT_END");

        process.exit(0);
    } catch (e) {
        process.exit(1);
    }
});
