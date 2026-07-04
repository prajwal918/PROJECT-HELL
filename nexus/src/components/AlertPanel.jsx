import { useState, useCallback } from 'react';
import TerminalConfig from '../config/TerminalConfig.js';

const C = TerminalConfig;

export default function AlertPanel({ visible, alerts, onAddAlert, onRemoveAlert, onClose }) {
  const [priceInput, setPriceInput] = useState('');
  const [direction, setDirection] = useState('above');

  const handleSubmit = useCallback((e) => {
    e.preventDefault();
    const price = parseFloat(priceInput);
    if (isNaN(price) || price <= 0) return;
    onAddAlert(price, direction);
    setPriceInput('');
  }, [priceInput, direction, onAddAlert]);

  if (!visible) return null;

  return (
    <div style={{
      position: 'absolute',
      top: 0,
      right: 0,
      width: 250,
      height: '100%',
      background: C.BG_SURFACE,
      borderLeft: `1px solid ${C.COLOR_BORDER}`,
      zIndex: 100,
      display: 'flex',
      flexDirection: 'column',
      fontFamily: "'Courier New', monospace",
      fontSize: 11,
      color: C.COLOR_TEXT_PRIMARY,
    }}>
      <div style={{
        padding: '8px 10px',
        borderBottom: `1px solid ${C.COLOR_BORDER}`,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{ fontWeight: 'bold', fontSize: 12, letterSpacing: 1 }}>ALERTS</span>
        <button onClick={onClose} style={{
          background: 'transparent',
          border: 'none',
          color: C.COLOR_TEXT_MUTED,
          cursor: 'pointer',
          fontSize: 14,
          padding: 0,
        }}>\u2715</button>
      </div>

      <form onSubmit={handleSubmit} style={{
        padding: '8px 10px',
        borderBottom: `1px solid ${C.COLOR_BORDER}`,
        display: 'flex',
        gap: 4,
        alignItems: 'center',
      }}>
        <input
          type="text"
          value={priceInput}
          onChange={e => setPriceInput(e.target.value)}
          placeholder="Price"
          style={{
            flex: 1,
            background: C.BG_PRIMARY,
            border: `1px solid ${C.COLOR_BORDER}`,
            borderRadius: 2,
            padding: '4px 6px',
            color: C.COLOR_TEXT_PRIMARY,
            fontSize: 11,
            fontFamily: "'Courier New', monospace",
            outline: 'none',
          }}
        />
        <select
          value={direction}
          onChange={e => setDirection(e.target.value)}
          style={{
            background: C.BG_PRIMARY,
            border: `1px solid ${C.COLOR_BORDER}`,
            borderRadius: 2,
            padding: '4px 4px',
            color: C.COLOR_TEXT_PRIMARY,
            fontSize: 10,
            fontFamily: "'Courier New', monospace",
          }}
        >
          <option value="above">ABOVE</option>
          <option value="below">BELOW</option>
          <option value="cross">CROSS</option>
        </select>
        <button type="submit" style={{
          background: C.BULLISH,
          color: C.BG_PRIMARY,
          border: 'none',
          borderRadius: 2,
          padding: '4px 8px',
          cursor: 'pointer',
          fontSize: 10,
          fontFamily: "'Courier New', monospace",
          fontWeight: 'bold',
        }}>ADD</button>
      </form>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {alerts.map(alert => (
          <div key={alert.id} style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '6px 10px',
            borderBottom: `1px solid ${C.COLOR_BORDER}`,
            background: alert.triggered ? 'rgba(242,201,76,0.08)' : 'transparent',
          }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <span style={{ color: alert.triggered ? '#F2C94C' : C.COLOR_TEXT_PRIMARY, fontWeight: 'bold' }}>
                {alert.price.toFixed(2)}
              </span>
              <span style={{ fontSize: 9, color: C.COLOR_TEXT_MUTED }}>
                {alert.direction.toUpperCase()}
                {alert.triggered ? ' \u2014 TRIGGERED' : ''}
              </span>
            </div>
            <button onClick={() => onRemoveAlert(alert.id)} style={{
              background: 'transparent',
              border: `1px solid ${C.COLOR_BORDER}`,
              borderRadius: 2,
              color: C.BEARISH,
              cursor: 'pointer',
              fontSize: 10,
              padding: '2px 6px',
              fontFamily: "'Courier New', monospace",
            }}>DEL</button>
          </div>
        ))}
        {alerts.length === 0 && (
          <div style={{ padding: '20px 10px', color: C.COLOR_TEXT_MUTED, textAlign: 'center', fontSize: 10 }}>
            No alerts set
          </div>
        )}
      </div>
    </div>
  );
}
