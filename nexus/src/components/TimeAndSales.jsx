import { useRef, useEffect, useState, useCallback } from 'react';
import TerminalConfig from '../config/TerminalConfig.js';
import { tradeBus } from '../trading/TradeBus.js';

const C = TerminalConfig;
const MAX_ROWS = 200;

export default function TimeAndSales({ visible }) {
  const [trades, setTrades] = useState([]);
  const containerRef = useRef(null);

  useEffect(() => {
    const unsubscribe = tradeBus.subscribe((trade) => {
      setTrades(prev => {
        const next = [trade, ...prev];
        if (next.length > MAX_ROWS) next.length = MAX_ROWS;
        return next;
      });
    });
    return unsubscribe;
  }, []);

  if (!visible) return null;

  return (
    <div style={{
      height: 150,
      background: C.BG_SURFACE,
      borderTop: `1px solid ${C.COLOR_BORDER}`,
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
    }}>
      <div style={{
        height: 22,
        display: 'flex',
        alignItems: 'center',
        padding: '0 8px',
        borderBottom: `1px solid ${C.COLOR_BORDER}`,
        background: C.BG_SURFACE,
        gap: 24,
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 9, color: C.BULLISH, fontFamily: "'Courier New', monospace", letterSpacing: 2 }}>TIME & SALES</span>
        <span style={{ fontSize: 9, color: C.COLOR_TEXT_MUTED, fontFamily: "'Courier New', monospace" }}>
          {trades.length} trades
        </span>
      </div>

      <div style={{
        height: 22,
        display: 'flex',
        alignItems: 'center',
        padding: '0 8px',
        borderBottom: `1px solid ${C.COLOR_BORDER}`,
        background: C.BG_PRIMARY,
        gap: 0,
        flexShrink: 0,
        fontFamily: "'Courier New', monospace",
        fontSize: 9,
        color: C.COLOR_TEXT_MUTED,
        letterSpacing: 1,
      }}>
        <span style={{ width: 90 }}>TIME</span>
        <span style={{ width: 100 }}>PRICE</span>
        <span style={{ width: 70 }}>SIZE</span>
        <span>SIDE</span>
      </div>

      <div ref={containerRef} style={{
        flex: 1,
        overflow: 'auto',
        fontFamily: "'Courier New', monospace",
        fontSize: 10,
      }}>
        {trades.map((t, i) => (
          <div key={i} style={{
            display: 'flex',
            alignItems: 'center',
            padding: '0 8px',
            height: 18,
            background: i % 2 === 0 ? C.BG_PRIMARY : C.BG_ROW_EVEN,
            gap: 0,
          }}>
            <span style={{ width: 90, color: C.COLOR_TEXT_MUTED }}>{t.time}</span>
            <span style={{ width: 100, color: t.side === 'BUY' ? C.BULLISH : C.BEARISH, fontWeight: 'bold' }}>
              {t.price}
            </span>
            <span style={{ width: 70, color: C.COLOR_TEXT_PRIMARY }}>{t.size}</span>
            <span style={{ color: t.side === 'BUY' ? C.BULLISH : C.BEARISH }}>
              {t.side}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
