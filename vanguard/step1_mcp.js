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
        console.log("1. Finding 'Trade' button for Options...");
        await send(ws, 'execute_script', { 
            code: `(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const tradeBtn = btns.find(b => b.innerText === 'Trade' && b.closest('div').innerText.includes('Options'));
                if (tradeBtn) tradeBtn.click();
                return tradeBtn ? "CLICKED" : "NOT_FOUND";
            })()`
        });
        await new Promise(r => setTimeout(r, 10000));

        console.log("2. Taking screenshot of Trading page...");
        const screenshot = await send(ws, 'screenshot', {});
        if (screenshot && screenshot.image) {
            fs.writeFileSync('/home/jogi999/vanguard/deriv_trading.png', screenshot.image.replace(/^data:image\/png;base64,/, ""), 'base64');
        }

        console.log("3. Extracting Account ID...");
        const id = await send(ws, 'execute_script', {
             code: `(() => {
                const idEl = document.querySelector('.acc-info__loginid') || document.querySelector('.account-id');
                if (idEl) return idEl.innerText;
                const bal = document.querySelector('.acc-info__balance');
                if (bal) bal.click();
                return "NEED_WAIT";
             })()`
        });
        console.log("RESULT_ID:" + id);

        process.exit(0);
    } catch (e) {
        process.exit(1);
    }
});
