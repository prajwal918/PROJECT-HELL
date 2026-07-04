import { useEffect, useRef, useState, useCallback } from 'react';

const MENU_WIDTH = 200;
const MENU_ITEM_HEIGHT = 28;
const SEPARATOR_HEIGHT = 9;

export default function ContextMenu({ x, y, items, onClose }) {
  const menuRef = useRef(null);
  const [focusedIndex, setFocusedIndex] = useState(-1);

  const adjustedPos = adjustPosition(x, y, items);

  useEffect(() => {
    const firstEnabled = items.findIndex(it => !it.disabled && !it.separator);
    setFocusedIndex(firstEnabled >= 0 ? firstEnabled : -1);
  }, [items]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        onClose();
      }
    };

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }

      const enabledIndices = items
        .map((it, idx) => ({ idx, disabled: it.disabled, separator: it.separator }))
        .filter(it => !it.disabled && !it.separator)
        .map(it => it.idx);

      if (enabledIndices.length === 0) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const currentPos = enabledIndices.indexOf(focusedIndex);
        const nextPos = currentPos < enabledIndices.length - 1 ? currentPos + 1 : 0;
        setFocusedIndex(enabledIndices[nextPos]);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const currentPos = enabledIndices.indexOf(focusedIndex);
        const prevPos = currentPos > 0 ? currentPos - 1 : enabledIndices.length - 1;
        setFocusedIndex(enabledIndices[prevPos]);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (focusedIndex >= 0 && focusedIndex < items.length) {
          const item = items[focusedIndex];
          if (!item.disabled && !item.separator && item.action) {
            item.action();
            onClose();
          }
        }
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose, items, focusedIndex]);

  let visualIndex = 0;
  return (
    <div
      ref={menuRef}
      style={{
        position: 'fixed',
        left: adjustedPos.x,
        top: adjustedPos.y,
        background: '#131722',
        border: '1px solid #2A2E39',
        borderRadius: 4,
        padding: '4px 0',
        minWidth: MENU_WIDTH,
        zIndex: 10000,
        fontFamily: "'Courier New', monospace",
        fontSize: 11,
        boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
      }}
    >
      {items.map((item, i) => {
        if (item.separator) {
          return (
            <div
              key={i}
              style={{
                height: SEPARATOR_HEIGHT,
                display: 'flex',
                alignItems: 'center',
                padding: '0 8px',
              }}
            >
              <div style={{ width: '100%', height: 1, background: '#2A2E39' }} />
            </div>
          );
        }

        const isFocused = i === focusedIndex;
        const isDisabled = item.disabled;

        return (
          <div
            key={i}
            onClick={() => {
              if (!isDisabled && item.action) {
                item.action();
                onClose();
              }
            }}
            onMouseEnter={() => setFocusedIndex(i)}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              height: MENU_ITEM_HEIGHT,
              padding: '0 12px',
              cursor: isDisabled ? 'default' : 'pointer',
              color: isDisabled ? '#555' : isFocused ? '#E1E4E8' : '#787B86',
              background: isFocused && !isDisabled ? '#1E222D' : 'transparent',
              transition: 'background 0.05s, color 0.05s',
              userSelect: 'none',
            }}
          >
            <span>{item.label}</span>
            {item.shortcut && (
              <span style={{ fontSize: 9, color: '#555', marginLeft: 16 }}>{item.shortcut}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function adjustPosition(x, y, items) {
  const itemCount = items.filter(it => !it.separator).length;
  const sepCount = items.filter(it => it.separator).length;
  const menuHeight = itemCount * MENU_ITEM_HEIGHT + sepCount * SEPARATOR_HEIGHT + 8;

  let adjX = x;
  let adjY = y;

  if (x + MENU_WIDTH > window.innerWidth) {
    adjX = window.innerWidth - MENU_WIDTH - 8;
  }
  if (y + menuHeight > window.innerHeight) {
    adjY = window.innerHeight - menuHeight - 8;
  }
  if (adjX < 0) adjX = 0;
  if (adjY < 0) adjY = 0;

  return { x: adjX, y: adjY };
}

export function buildChartContextMenu({ onAddAlert, onDrawLine, onDrawTrendLine, onDrawRay, onDrawFibonacci, onCustomVolumeProfile, onChartTypeChange, onSettings }) {
  return [
    { label: 'Add Alert (Above)', action: () => onAddAlert?.('above'), shortcut: '' },
    { label: 'Add Alert (Below)', action: () => onAddAlert?.('below'), shortcut: '' },
    { separator: true },
    { label: 'Draw Horizontal Line', action: () => onDrawLine?.(), shortcut: 'H' },
    { label: 'Draw Trend Line', action: () => onDrawTrendLine?.(), shortcut: 'T' },
    { label: 'Draw Ray', action: () => onDrawRay?.(), shortcut: 'R' },
    { label: 'Draw Fibonacci', action: () => onDrawFibonacci?.(), shortcut: 'F' },
    { separator: true },
    { label: 'Custom Volume Profile (from here...)', action: () => onCustomVolumeProfile?.() },
    { separator: true },
    { label: 'Chart Type → Footprint', action: () => onChartTypeChange?.('footprint') },
    { label: 'Chart Type → Candlestick', action: () => onChartTypeChange?.('candlestick') },
    { label: 'Chart Type → Line', action: () => onChartTypeChange?.('line') },
    { separator: true },
    { label: 'Settings', action: () => onSettings?.(), shortcut: 'S' },
  ];
}

export function buildDOMContextMenu({ price, onBuyLimit, onSellLimit, onBuyStop, onSellStop, onAddAlert, onDrawLine }) {
  return [
    { label: `Buy Limit @ ${price.toFixed(2)}`, action: () => onBuyLimit?.(price) },
    { label: `Sell Limit @ ${price.toFixed(2)}`, action: () => onSellLimit?.(price) },
    { separator: true },
    { label: `Buy Stop @ ${price.toFixed(2)}`, action: () => onBuyStop?.(price) },
    { label: `Sell Stop @ ${price.toFixed(2)}`, action: () => onSellStop?.(price) },
    { separator: true },
    { label: `Add Alert at ${price.toFixed(2)}`, action: () => onAddAlert?.(price) },
    { label: `Draw Horizontal Line @ ${price.toFixed(2)}`, action: () => onDrawLine?.(price) },
  ];
}
