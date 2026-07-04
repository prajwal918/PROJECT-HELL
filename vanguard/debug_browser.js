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
        console.log("Navigating...");
        await send(ws, 'navigate', { url: 'https://app.deriv.com/account/api-token' });
        await new Promise(r => setTimeout(r, 10000));
        
        console.log("Taking screenshot...");
        const screenshot = await send(ws, 'screenshot', {});
        // result should have .image which is base64
        if (screenshot && screenshot.image) {
            const base64Data = screenshot.image.replace(/^data:image\/png;base64,/, "");
            fs.writeFileSync('/home/jogi999/vanguard/deriv_debug.png', base64Data, 'base64');
            console.log("SCREENSHOT_SAVED");
        } else {
             console.log("SCREENSHOT_FAILED:" + JSON.stringify(screenshot));
        }

        process.exit(0);
    } catch (e) {
        process.exit(1);
    }
});
