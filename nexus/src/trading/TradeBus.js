const listeners = new Set();

export const tradeBus = {
  publish(trade) {
    const entry = {
      time: trade.time || new Date().toLocaleTimeString('en-US', { hour12: false }),
      price: typeof trade.price === 'number' ? trade.price.toFixed(2) : String(trade.price),
      size: typeof trade.size === 'number' ? trade.size.toFixed(0) : String(trade.size),
      side: trade.side === 1 || trade.side === 'ASK' ? 'BUY' : 'SELL',
    };
    for (const cb of listeners) {
      try { cb(entry); } catch (e) { /* ignore */ }
    }
  },

  subscribe(callback) {
    listeners.add(callback);
    return () => { listeners.delete(callback); };
  },

  clear() {
    listeners.clear();
  },
};
