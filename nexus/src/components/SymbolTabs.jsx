import { useCallback } from 'react';
import TerminalConfig from '../config/TerminalConfig.js';

const C = {
  BG: '#0B0E11',
  BORDER: '#1E222D',
  TEXT: '#E1E4E8',
  TEXT_MUTED: '#787B86',
  ACCENT: '#26A69A',
  ACTIVE_BG: '#131722',
  HOVER: '#1A1E2A',
};

const AVAILABLE_SYMBOLS = ['ES', 'NQ', 'CL', 'GC', 'YM', 'RTY', 'ZB', 'ZN'];
const MAX_TABS = 10;

export default function SymbolTabs({ symbols, activeSymbol, onSwitch, onAdd, onRemove }) {
  const handleAdd = useCallback(() => {
    const current = symbols || ['ES'];
    const available = AVAILABLE_SYMBOLS.filter(s => !current.includes(s));
    if (available.length > 0 && current.length < MAX_TABS) {
      onAdd(available[0]);
    }
  }, [symbols, onAdd]);

  return (
    <div style={{
      height: 32,
      background: C.BG,
      borderBottom: `1px solid ${C.BORDER}`,
      display: 'flex',
      alignItems: 'center',
      padding: '0 8px',
      gap: 2,
      flexShrink: 0,
      fontFamily: "'Courier New', monospace",
    }}>
      {(symbols || ['ES']).map(sym => (
        <div
          key={sym}
          onClick={() => onSwitch(sym)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '3px 10px',
            borderRadius: 3,
            cursor: 'pointer',
            fontSize: 11,
            fontWeight: sym === activeSymbol ? 'bold' : 'normal',
            letterSpacing: 1,
            background: sym === activeSymbol ? C.ACTIVE_BG : 'transparent',
            color: sym === activeSymbol ? C.ACCENT : C.TEXT_MUTED,
            border: `1px solid ${sym === activeSymbol ? C.ACCENT : 'transparent'}`,
            transition: 'all 0.15s ease',
          }}
          onMouseEnter={e => { if (sym !== activeSymbol) e.currentTarget.style.background = C.HOVER; }}
          onMouseLeave={e => { if (sym !== activeSymbol) e.currentTarget.style.background = 'transparent'; }}
        >
          {sym}
          {(symbols || []).length > 1 && (
            <span
              onClick={(e) => { e.stopPropagation(); onRemove(sym); }}
              style={{
                color: C.TEXT_MUTED,
                fontSize: 10,
                lineHeight: 1,
                padding: '0 2px',
                borderRadius: 2,
                cursor: 'pointer',
              }}
              onMouseEnter={e => { e.currentTarget.style.color = C.TEXT; e.currentTarget.style.background = 'rgba(239,83,80,0.3)'; }}
              onMouseLeave={e => { e.currentTarget.style.color = C.TEXT_MUTED; e.currentTarget.style.background = 'transparent'; }}
            >
              ×
            </span>
          )}
        </div>
      ))}

      {(symbols || []).length < MAX_TABS && (
        <button
          onClick={handleAdd}
          style={{
            background: 'transparent',
            border: `1px dashed ${C.BORDER}`,
            color: C.TEXT_MUTED,
            borderRadius: 3,
            padding: '3px 8px',
            cursor: 'pointer',
            fontSize: 12,
            fontFamily: "'Courier New', monospace",
            lineHeight: 1,
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = C.ACCENT; e.currentTarget.style.color = C.ACCENT; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = C.BORDER; e.currentTarget.style.color = C.TEXT_MUTED; }}
        >
          +
        </button>
      )}
    </div>
  );
}
