import { useState, useCallback, useEffect, useRef } from 'react';
import { getOrderRouter } from '../trading/OrderRouter.js';
import TerminalConfig from '../config/TerminalConfig.js';

const C = {
  BG: '#0B0E11',
  BG_SURFACE: '#131722',
  BORDER: '#1E222D',
  TEXT: '#E1E4E8',
  TEXT_MUTED: '#787B86',
  BULLISH: '#26A69A',
  BEARISH: '#EF5350',
  ACCENT: '#26A69A',
  INPUT_BG: '#0E1117',
};

const inputStyle = {
  width: '100%',
  background: C.INPUT_BG,
  color: C.TEXT,
  border: `1px solid ${C.BORDER}`,
  borderRadius: 3,
  padding: '6px 8px',
  fontSize: 12,
  fontFamily: "'Courier New', monospace",
  outline: 'none',
  boxSizing: 'border-box',
};

const btnBase = {
  flex: 1,
  padding: '10px 0',
  border: 'none',
  borderRadius: 3,
  cursor: 'pointer',
  fontSize: 12,
  fontFamily: "'Courier New', monospace",
  fontWeight: 'bold',
  letterSpacing: 1,
  color: C.BG,
};

export default function TradingPanel({ visible, onClose, symbol }) {
  const [account, setAccount] = useState('SIM');
  const [quantity, setQuantity] = useState(1);
  const [limitPrice, setLimitPrice] = useState('');
  const [stopPrice, setStopPrice] = useState('');
  const [tpPrice, setTpPrice] = useState('');
  const [slPrice, setSlPrice] = useState('');
  const [position, setPosition] = useState({ size: 0, avgEntry: 0, unrealizedPnl: 0 });
  const [workingOrders, setWorkingOrders] = useState([]);
  const routerRef = useRef(null);
  const fillSubRef = useRef(null);
  const orderSubRef = useRef(null);

  useEffect(() => {
    routerRef.current = getOrderRouter();
    const router = routerRef.current;

    router.onFill = (msg) => {
      setPosition(prev => {
        const fillSide = msg.side || msg.filled_side || 'BUY';
        const fillSize = msg.filled_size || msg.size || 1;
        const fillPrice = msg.filled_price || msg.price || 0;
        const isBuy = fillSide === 'BUY';
        const signedSize = isBuy ? fillSize : -fillSize;
        const newSize = prev.size + signedSize;
        if (newSize === 0) return { size: 0, avgEntry: 0, unrealizedPnl: 0 };
        const newAvg = prev.size === 0
          ? fillPrice
          : (prev.avgEntry * Math.abs(prev.size) + fillPrice * fillSize) / (Math.abs(prev.size) + fillSize);
        return { size: newSize, avgEntry: newAvg, unrealizedPnl: prev.unrealizedPnl };
      });
    };

    router.onOrderUpdate = () => {
      setWorkingOrders(router.getWorkingOrders());
    };

    const poll = setInterval(() => {
      setWorkingOrders(router.getWorkingOrders());
    }, 1000);

    return () => clearInterval(poll);
  }, []);

  const sym = symbol || TerminalConfig.SYMBOL;

  const handleMarketBuy = useCallback(() => {
    if (routerRef.current) routerRef.current.submitMarketOrder(sym, 'BUY', quantity);
  }, [sym, quantity]);

  const handleMarketSell = useCallback(() => {
    if (routerRef.current) routerRef.current.submitMarketOrder(sym, 'SELL', quantity);
  }, [sym, quantity]);

  const handleLimitBuy = useCallback(() => {
    const p = parseFloat(limitPrice);
    if (isNaN(p)) return;
    if (routerRef.current) routerRef.current.submitLimitOrder(sym, 'BUY', p, quantity);
  }, [sym, quantity, limitPrice]);

  const handleLimitSell = useCallback(() => {
    const p = parseFloat(limitPrice);
    if (isNaN(p)) return;
    if (routerRef.current) routerRef.current.submitLimitOrder(sym, 'SELL', p, quantity);
  }, [sym, quantity, limitPrice]);

  const handleStopBuy = useCallback(() => {
    const p = parseFloat(stopPrice);
    if (isNaN(p)) return;
    if (routerRef.current) {
      const oid = routerRef.current.submitLimitOrder(sym, 'BUY', p, quantity);
      routerRef.current.workingOrders.get(oid).__stop = true;
    }
  }, [sym, quantity, stopPrice]);

  const handleStopSell = useCallback(() => {
    const p = parseFloat(stopPrice);
    if (isNaN(p)) return;
    if (routerRef.current) {
      const oid = routerRef.current.submitLimitOrder(sym, 'SELL', p, quantity);
      routerRef.current.workingOrders.get(oid).__stop = true;
    }
  }, [sym, quantity, stopPrice]);

  const handleBracket = useCallback(() => {
    const tp = parseFloat(tpPrice);
    const sl = parseFloat(slPrice);
    if (isNaN(tp) || isNaN(sl)) return;
    if (routerRef.current) {
      routerRef.current.submitLimitOrder(sym, 'BUY', tp, quantity);
      routerRef.current.submitLimitOrder(sym, 'SELL', sl, quantity);
    }
  }, [sym, quantity, tpPrice, slPrice]);

  const handleCancel = useCallback((oid) => {
    if (routerRef.current) routerRef.current.cancelOrder(oid);
  }, []);

  const handleCancelAll = useCallback(() => {
    if (routerRef.current) {
      const orders = routerRef.current.getWorkingOrders();
      for (const o of orders) routerRef.current.cancelOrder(o.order_id);
    }
  }, []);

  const handleCloseAll = useCallback(() => {
    if (position.size !== 0 && routerRef.current) {
      const side = position.size > 0 ? 'SELL' : 'BUY';
      routerRef.current.submitMarketOrder(sym, side, Math.abs(position.size));
    }
  }, [sym, position.size]);

  const pnlColor = position.unrealizedPnl >= 0 ? C.BULLISH : C.BEARISH;

  return (
    <div style={{
      position: 'absolute',
      top: 0,
      left: visible ? 0 : -280,
      width: 280,
      height: '100%',
      background: C.BG,
      borderRight: `1px solid ${C.BORDER}`,
      zIndex: 9000,
      transition: 'left 0.2s ease',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      fontFamily: "'Courier New', monospace",
    }}>
      <div style={{ padding: '12px 14px', borderBottom: `1px solid ${C.BORDER}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: C.ACCENT, fontWeight: 'bold', fontSize: 13, letterSpacing: 2 }}>ORDERS</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: C.TEXT_MUTED, cursor: 'pointer', fontSize: 16, padding: 0, lineHeight: 1 }}>✕</button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: C.TEXT, fontSize: 16, fontWeight: 'bold' }}>{sym}</span>
          <select value={account} onChange={e => setAccount(e.target.value)} style={{ background: C.INPUT_BG, color: C.TEXT, border: `1px solid ${C.BORDER}`, borderRadius: 3, padding: '3px 6px', fontSize: 11, fontFamily: "'Courier New', monospace" }}>
            <option value="SIM">SIM</option>
            <option value="LIVE">LIVE</option>
          </select>
        </div>

        <div>
          <label style={{ fontSize: 10, color: C.TEXT_MUTED, display: 'block', marginBottom: 3 }}>QTY</label>
          <input type="number" min="1" value={quantity} onChange={e => setQuantity(Math.max(1, parseInt(e.target.value) || 1))} style={inputStyle} />
        </div>

        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={handleMarketBuy} style={{ ...btnBase, background: C.BULLISH }}>BUY MKT</button>
          <button onClick={handleMarketSell} style={{ ...btnBase, background: C.BEARISH }}>SELL MKT</button>
        </div>

        <div style={{ borderTop: `1px solid ${C.BORDER}`, paddingTop: 10 }}>
          <label style={{ fontSize: 10, color: C.TEXT_MUTED, display: 'block', marginBottom: 3 }}>LIMIT PRICE</label>
          <input type="number" step="0.25" value={limitPrice} onChange={e => setLimitPrice(e.target.value)} placeholder="0.00" style={inputStyle} />
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <button onClick={handleLimitBuy} style={{ ...btnBase, background: C.BULLISH, opacity: 0.85 }}>BUY LMT</button>
            <button onClick={handleLimitSell} style={{ ...btnBase, background: C.BEARISH, opacity: 0.85 }}>SELL LMT</button>
          </div>
        </div>

        <div style={{ borderTop: `1px solid ${C.BORDER}`, paddingTop: 10 }}>
          <label style={{ fontSize: 10, color: C.TEXT_MUTED, display: 'block', marginBottom: 3 }}>STOP PRICE</label>
          <input type="number" step="0.25" value={stopPrice} onChange={e => setStopPrice(e.target.value)} placeholder="0.00" style={inputStyle} />
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <button onClick={handleStopBuy} style={{ ...btnBase, background: C.BULLISH, opacity: 0.7 }}>BUY STP</button>
            <button onClick={handleStopSell} style={{ ...btnBase, background: C.BEARISH, opacity: 0.7 }}>SELL STP</button>
          </div>
        </div>

        <div style={{ borderTop: `1px solid ${C.BORDER}`, paddingTop: 10 }}>
          <label style={{ fontSize: 10, color: C.ACCENT, fontWeight: 'bold', display: 'block', marginBottom: 6, letterSpacing: 1 }}>BRACKET</label>
          <div style={{ display: 'flex', gap: 6 }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 9, color: C.BULLISH, display: 'block', marginBottom: 2 }}>TAKE PROFIT</label>
              <input type="number" step="0.25" value={tpPrice} onChange={e => setTpPrice(e.target.value)} placeholder="0.00" style={inputStyle} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 9, color: C.BEARISH, display: 'block', marginBottom: 2 }}>STOP LOSS</label>
              <input type="number" step="0.25" value={slPrice} onChange={e => setSlPrice(e.target.value)} placeholder="0.00" style={inputStyle} />
            </div>
          </div>
          <button onClick={handleBracket} style={{ ...btnBase, width: '100%', marginTop: 6, background: '#1E222D', color: C.ACCENT, border: `1px solid ${C.ACCENT}` }}>SUBMIT BRACKET</button>
        </div>

        <div style={{ borderTop: `1px solid ${C.BORDER}`, paddingTop: 10 }}>
          <label style={{ fontSize: 10, color: C.ACCENT, fontWeight: 'bold', display: 'block', marginBottom: 6, letterSpacing: 1 }}>POSITION</label>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
            <span style={{ color: C.TEXT_MUTED }}>Size</span>
            <span style={{ color: position.size > 0 ? C.BULLISH : position.size < 0 ? C.BEARISH : C.TEXT }}>{position.size}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginTop: 3 }}>
            <span style={{ color: C.TEXT_MUTED }}>Avg Entry</span>
            <span style={{ color: C.TEXT }}>{position.avgEntry ? position.avgEntry.toFixed(2) : '—'}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginTop: 3 }}>
            <span style={{ color: C.TEXT_MUTED }}>Unrealized P&L</span>
            <span style={{ color: pnlColor, fontWeight: 'bold' }}>{position.unrealizedPnl >= 0 ? '+' : ''}{position.unrealizedPnl.toFixed(2)}</span>
          </div>
        </div>

        {workingOrders.length > 0 && (
          <div style={{ borderTop: `1px solid ${C.BORDER}`, paddingTop: 10 }}>
            <label style={{ fontSize: 10, color: C.ACCENT, fontWeight: 'bold', display: 'block', marginBottom: 6, letterSpacing: 1 }}>WORKING ORDERS</label>
            {workingOrders.map(o => (
              <div key={o.order_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0', borderBottom: `1px solid ${C.BORDER}` }}>
                <span style={{ fontSize: 10, color: o.side === 'BUY' ? C.BULLISH : C.BEARISH }}>{o.side} {o.size}@{o.price?.toFixed(2)}</span>
                <button onClick={() => handleCancel(o.order_id)} style={{ background: 'none', border: `1px solid ${C.BEARISH}`, color: C.BEARISH, borderRadius: 2, padding: '1px 6px', cursor: 'pointer', fontSize: 9, fontFamily: "'Courier New', monospace" }}>CANCEL</button>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: 6, marginTop: 'auto' }}>
          <button onClick={handleCloseAll} style={{ ...btnBase, background: C.BEARISH, fontSize: 10, padding: '8px 0' }}>CLOSE ALL</button>
          <button onClick={handleCancelAll} style={{ ...btnBase, background: '#1E222D', color: C.TEXT_MUTED, border: `1px solid ${C.BORDER}`, fontSize: 10, padding: '8px 0' }}>CANCEL ALL</button>
        </div>
      </div>
    </div>
  );
}
