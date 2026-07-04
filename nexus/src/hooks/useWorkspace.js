import { useState, useCallback, useRef, useEffect } from 'react';

const STORAGE_KEY = 'nexus_workspace';
const AVAILABLE_SYMBOLS = ['ES', 'NQ', 'CL', 'GC', 'YM', 'RTY', 'ZB', 'ZN'];
const MAX_TABS = 10;

const MOCK_BASE_PRICES = {
  ES: 4500.25,
  NQ: 18500.50,
  CL: 72.35,
  GC: 2350.75,
  YM: 39500.00,
  RTY: 2100.50,
  ZB: 115.25,
  ZN: 110.75,
};

function loadWorkspace() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const data = JSON.parse(raw);
      if (data.symbols && data.symbols.length > 0) return data;
    }
  } catch (e) { /* ignore */ }
  return { symbols: ['ES'], activeSymbol: 'ES', viewStates: {} };
}

function saveWorkspace(data) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch (e) { /* ignore */ }
}

export function useWorkspace() {
  const [activeSymbol, setActiveSymbol] = useState(() => loadWorkspace().activeSymbol);
  const [symbols, setSymbols] = useState(() => loadWorkspace().symbols);
  const viewStatesRef = useRef(loadWorkspace().viewStates || {});

  useEffect(() => {
    saveWorkspace({ symbols, activeSymbol, viewStates: viewStatesRef.current });
  }, [symbols, activeSymbol]);

  const addSymbol = useCallback((sym) => {
    setSymbols(prev => {
      if (prev.includes(sym) || prev.length >= MAX_TABS) return prev;
      return [...prev, sym];
    });
  }, []);

  const removeSymbol = useCallback((sym) => {
    setSymbols(prev => {
      if (prev.length <= 1) return prev;
      return prev.filter(s => s !== sym);
    });
    setActiveSymbol(prev => {
      if (prev === sym) {
        const remaining = symbols.filter(s => s !== sym);
        return remaining.length > 0 ? remaining[0] : 'ES';
      }
      return prev;
    });
  }, [symbols]);

  const switchSymbol = useCallback((sym) => {
    setActiveSymbol(sym);
  }, []);

  const getViewState = useCallback((sym) => {
    return viewStatesRef.current[sym] || {
      priceMin: (MOCK_BASE_PRICES[sym] || 4500) - 10,
      priceMax: (MOCK_BASE_PRICES[sym] || 4500) + 10,
      bestBid: MOCK_BASE_PRICES[sym] || 4500,
      bestAsk: (MOCK_BASE_PRICES[sym] || 4500) + 0.25,
    };
  }, []);

  const saveViewState = useCallback((sym, vs) => {
    viewStatesRef.current[sym] = vs;
  }, []);

  const getMockBasePrice = useCallback((sym) => {
    return MOCK_BASE_PRICES[sym] || 4500.25;
  }, []);

  return {
    activeSymbol,
    symbols,
    addSymbol,
    removeSymbol,
    switchSymbol,
    getViewState,
    saveViewState,
    getMockBasePrice,
  };
}
