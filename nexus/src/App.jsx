import { useRef, useEffect, useState, useCallback } from 'react';
import { useMemoryBridge } from './hooks/useMemoryBridge.js';
import HeatmapPage from './components/HeatmapPage.jsx';
import FootprintPage from './components/FootprintPage.jsx';
import SettingsPanel from './components/SettingsPanel.jsx';
import TimeAndSales from './components/TimeAndSales.jsx';
import AlertPanel from './components/AlertPanel.jsx';
import { DrawingManager } from './renderer/DrawingManager.js';
import { AlertManager } from './renderer/AlertManager.js';
import { getOrderRouter } from './trading/OrderRouter.js';
import { tradeBus } from './trading/TradeBus.js';
import TerminalConfig from './config/TerminalConfig.js';

const C = TerminalConfig;

function HealthHUD({ stats }) {
  const hudRef = useRef(null);
  useEffect(() => {
    const el = hudRef.current;
    if (!el) return;
    const interval = setInterval(() => {
      const s = stats();
      el.querySelector('#hud-tps').textContent = s.ticksPerSecond || 0;
      const ftEl = el.querySelector('#hud-ft');
      ftEl.textContent = (s.frameTimeMs || 0).toFixed(1);
      ftEl.style.color = s.frameTimeMs > 16.6 ? C.BEARISH : C.BULLISH;
      el.querySelector('#hud-fill').textContent = (s.ringBufferFill || 0).toFixed(1);
      const wsEl = el.querySelector('#hud-ws');
      wsEl.textContent = s.wsStatus || 'INIT';
      wsEl.style.color = s.wsStatus === 'CONNECTED' ? C.BULLISH : s.wsStatus === 'RECONNECTING' ? C.COLOR_POC : C.BEARISH;
      el.querySelector('#hud-gc').textContent = s.gcPauseCount || 0;
    }, 1000);
    return () => clearInterval(interval);
  }, [stats]);

  return (
    <div ref={hudRef} style={{
      position: 'absolute', top: 8, right: 8,
      background: C.HUD_BG, border: `1px solid ${C.HUD_BORDER}`,
      borderRadius: 4, padding: '6px 10px',
      fontFamily: "'Courier New', monospace", fontSize: 10,
      color: C.COLOR_TEXT_MUTED, zIndex: 9999,
      display: 'flex', gap: 12, pointerEvents: 'none',
    }}>
      <span>TPS:<b id="hud-tps" style={{ color: C.BULLISH }}>0</b></span>
      <span>FT:<b id="hud-ft">0.0</b>ms</span>
      <span>Fill:<b id="hud-fill">0.0</b>%</span>
      <span>WS:<b id="hud-ws">INIT</b></span>
      <span>GC:<b id="hud-gc" style={{ color: C.COLOR_POC }}>0</b></span>
    </div>
  );
}

const TABS = [
  { id: 'heatmap', label: 'HEATMAP', sub: 'Bookmap' },
  { id: 'footprint', label: 'FOOTPRINT', sub: 'GoCharting' },
];

const INTERVALS = [
  { label: '1m', ms: 60000 },
  { label: '5m', ms: 300000 },
  { label: '15m', ms: 900000 },
  { label: '1h', ms: 3600000 },
];

function App() {
  const {
    sab, featureSAB, ringBuffer, worker, viewState,
    heatmapRef, footprintRef,
    getStats, startMock, stopMock, connect, setCandleInterval,
  } = useMemoryBridge({ useMock: C.USE_MOCK_DATA, mockRate: C.MOCK_RATE });

  const [activeTab, setActiveTab] = useState('heatmap');
  const [wsStatus, setWsStatus] = useState('INIT');
  const [isMockActive, setIsMockActive] = useState(C.USE_MOCK_DATA);
  const [candleInterval, setCandleIntervalState] = useState(60000);
  const [showSettings, setShowSettings] = useState(false);
  const [showTimeAndSales, setShowTimeAndSales] = useState(false);
  const [showAlertPanel, setShowAlertPanel] = useState(false);
  const [activeTool, setActiveTool] = useState(null);
  const [indicators, setIndicators] = useState([]);
  const [showRSI, setShowRSI] = useState(false);
  const [showMACD, setShowMACD] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const orderRouterRef = useRef(null);
  const drawingManagerRef = useRef(null);
  const alertManagerRef = useRef(null);

  useEffect(() => {
    drawingManagerRef.current = new DrawingManager();
  }, []);

  useEffect(() => {
    alertManagerRef.current = new AlertManager((alert) => {
      setAlerts([...alertManagerRef.current.getAlerts()]);
    });
    setAlerts(alertManagerRef.current.getAlerts());
  }, []);

  useEffect(() => {
    const w = worker.current;
    if (w) w.onmessage = (e) => {
      if (e.data.type === 'status') setWsStatus(e.data.status);
      if (e.data.type === 'stats') {
        const d = e.data.data;
        if (d.lastTradePrice && d.lastTradeSize) {
          tradeBus.publish({
            price: d.lastTradePrice,
            size: d.lastTradeSize,
            side: d.lastTradeSide,
          });
          if (alertManagerRef.current) {
            alertManagerRef.current.checkAlerts(d.lastTradePrice);
          }
        }
      }
    };
  }, [worker]);

  useEffect(() => { orderRouterRef.current = getOrderRouter(); }, []);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

      switch (e.key) {
        case '1':
          setActiveTab('heatmap');
          break;
        case '2':
          setActiveTab('footprint');
          break;
        case '+':
        case '=':
          if (viewState?.current) {
            viewState.current.priceMin += 1;
            viewState.current.priceMax -= 1;
          }
          break;
        case '-':
        case '_':
          if (viewState?.current) {
            viewState.current.priceMin -= 1;
            viewState.current.priceMax += 1;
          }
          break;
        case 'ArrowUp':
          e.preventDefault();
          if (viewState?.current) {
            viewState.current.priceMin += 1;
            viewState.current.priceMax += 1;
          }
          break;
        case 'ArrowDown':
          e.preventDefault();
          if (viewState?.current) {
            viewState.current.priceMin -= 1;
            viewState.current.priceMax -= 1;
          }
          break;
        case 'm':
        case 'M':
          handleMockToggle();
          break;
        case 'r':
        case 'R':
          if (viewState?.current) {
            const mid = (viewState.current.bestBid + viewState.current.bestAsk) / 2 || 4500;
            const range = (viewState.current.priceMax - viewState.current.priceMin) / 2;
            viewState.current.priceMin = mid - range;
            viewState.current.priceMax = mid + range;
          }
          break;
        case 't':
        case 'T':
          setShowTimeAndSales(prev => !prev);
          break;
        case 's':
        case 'S':
          setShowSettings(prev => !prev);
          break;
        case 'a':
        case 'A':
          setShowAlertPanel(prev => !prev);
          break;
        case 'Escape':
          setShowSettings(false);
          setShowTimeAndSales(false);
          setShowAlertPanel(false);
          setActiveTool(null);
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [viewState]);

  const handleMockToggle = useCallback(() => {
    if (isMockActive) { stopMock(); setIsMockActive(false); }
    else { startMock(C.MOCK_RATE); setIsMockActive(true); }
  }, [isMockActive, startMock, stopMock]);

  const handleConnect = useCallback(() => {
    connect();
    if (orderRouterRef.current) orderRouterRef.current.connect();
  }, [connect]);

  const handleIntervalChange = useCallback((e) => {
    const ms = parseInt(e.target.value, 10);
    setCandleIntervalState(ms);
    setCandleInterval(ms);
  }, [setCandleInterval]);

  const handleToolSelect = useCallback((tool) => {
    if (tool === 'clear_all') {
      if (drawingManagerRef.current) drawingManagerRef.current.clearAll();
      setActiveTool(null);
    } else {
      setActiveTool(tool);
    }
  }, []);

  const handleAddAlert = useCallback((price, direction) => {
    if (alertManagerRef.current) {
      alertManagerRef.current.addAlert(price, direction);
      setAlerts([...alertManagerRef.current.getAlerts()]);
    }
  }, []);

  const handleRemoveAlert = useCallback((id) => {
    if (alertManagerRef.current) {
      alertManagerRef.current.removeAlert(id);
      setAlerts([...alertManagerRef.current.getAlerts()]);
    }
  }, []);

  const handleToggleIndicator = useCallback((type) => {
    setIndicators(prev => {
      const exists = prev.find(i => i.type === type);
      if (exists) return prev.filter(i => i.type !== type);
      return [...prev, { type, period: type === 'sma' ? 20 : type === 'ema' ? 20 : 20, stdDev: 2 }];
    });
  }, []);

  const vs = viewState?.current;

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', background: C.BG_PRIMARY, color: C.COLOR_TEXT_MUTED, overflow: 'hidden' }}>

      <div style={{ height: 44, background: C.TOOLBAR_BG, borderBottom: `1px solid ${C.TOOLBAR_BORDER}`, display: 'flex', alignItems: 'center', padding: '0 16px', gap: 20, flexShrink: 0 }}>

        <span style={{ color: C.TOOLBAR_ACCENT, fontWeight: 'bold', fontSize: 15, letterSpacing: 2, fontFamily: "'Courier New', monospace" }}>NEXUS FLOW</span>

        <div style={{ width: 1, height: 24, background: C.COLOR_BORDER }} />

        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              background: activeTab === tab.id ? C.BULLISH : 'transparent',
              color: activeTab === tab.id ? C.BG_PRIMARY : C.COLOR_TEXT_MUTED,
              border: `1px solid ${activeTab === tab.id ? C.BULLISH : C.COLOR_BORDER}`,
              borderRadius: 4, padding: '5px 16px', cursor: 'pointer',
              fontSize: 12, fontFamily: "'Courier New', monospace",
              fontWeight: activeTab === tab.id ? 'bold' : 'normal', letterSpacing: 1,
            }}
          >
            {tab.label}
            <span style={{ fontSize: 9, marginLeft: 6, opacity: 0.6 }}>{tab.sub}</span>
          </button>
        ))}

        <div style={{ width: 1, height: 24, background: C.COLOR_BORDER }} />

        <select style={{ background: C.BG_PRIMARY, color: C.COLOR_TEXT_PRIMARY, border: `1px solid ${C.COLOR_BORDER}`, padding: '4px 8px', borderRadius: 3, fontSize: 12, fontFamily: "'Courier New', monospace" }}>
          <option value="ES">ES (S&P 500)</option><option value="NQ">NQ (Nasdaq)</option>
          <option value="CL">CL (Crude Oil)</option><option value="GC">GC (Gold)</option>
        </select>

        <select value={candleInterval} onChange={handleIntervalChange} style={{ background: C.BG_PRIMARY, color: C.COLOR_TEXT_PRIMARY, border: `1px solid ${C.COLOR_BORDER}`, padding: '4px 8px', borderRadius: 3, fontSize: 12, fontFamily: "'Courier New', monospace" }}>
          {INTERVALS.map(iv => <option key={iv.ms} value={iv.ms}>{iv.label}</option>)}
        </select>

        <div style={{ width: 8, height: 8, borderRadius: '50%', background: wsStatus === 'CONNECTED' ? C.BULLISH : wsStatus === 'RECONNECTING' ? C.COLOR_POC : C.BEARISH, boxShadow: wsStatus === 'CONNECTED' ? `0 0 6px ${C.BULLISH}` : 'none' }} />
        <span style={{ fontSize: 11 }}>{wsStatus}</span>

        <button onClick={handleMockToggle} style={{ background: isMockActive ? C.BULLISH : C.BG_PRIMARY, color: isMockActive ? C.BG_PRIMARY : C.COLOR_TEXT_MUTED, border: `1px solid ${isMockActive ? C.BULLISH : C.COLOR_BORDER}`, padding: '4px 12px', borderRadius: 3, cursor: 'pointer', fontSize: 11, fontFamily: "'Courier New', monospace" }}>
          {isMockActive ? 'STOP MOCK' : 'START MOCK'}
        </button>

        <button onClick={handleConnect} style={{ background: C.BG_PRIMARY, color: '#3B82F6', border: `1px solid #3B82F6`, padding: '4px 12px', borderRadius: 3, cursor: 'pointer', fontSize: 11, fontFamily: "'Courier New', monospace" }}>
          CONNECT
        </button>

        <div style={{ width: 1, height: 24, background: C.COLOR_BORDER }} />

        {activeTab === 'footprint' && (
          <>
            <button onClick={() => handleToggleIndicator('sma')} style={{ background: indicators.find(i => i.type === 'sma') ? C.BULLISH : C.BG_PRIMARY, color: indicators.find(i => i.type === 'sma') ? C.BG_PRIMARY : C.COLOR_TEXT_MUTED, border: `1px solid ${indicators.find(i => i.type === 'sma') ? C.BULLISH : C.COLOR_BORDER}`, padding: '4px 8px', borderRadius: 3, cursor: 'pointer', fontSize: 10, fontFamily: "'Courier New', monospace" }}>SMA</button>
            <button onClick={() => handleToggleIndicator('ema')} style={{ background: indicators.find(i => i.type === 'ema') ? '#FF9800' : C.BG_PRIMARY, color: indicators.find(i => i.type === 'ema') ? C.BG_PRIMARY : C.COLOR_TEXT_MUTED, border: `1px solid ${indicators.find(i => i.type === 'ema') ? '#FF9800' : C.COLOR_BORDER}`, padding: '4px 8px', borderRadius: 3, cursor: 'pointer', fontSize: 10, fontFamily: "'Courier New', monospace" }}>EMA</button>
            <button onClick={() => handleToggleIndicator('bollinger')} style={{ background: indicators.find(i => i.type === 'bollinger') ? '#2196F3' : C.BG_PRIMARY, color: indicators.find(i => i.type === 'bollinger') ? C.BG_PRIMARY : C.COLOR_TEXT_MUTED, border: `1px solid ${indicators.find(i => i.type === 'bollinger') ? '#2196F3' : C.COLOR_BORDER}`, padding: '4px 8px', borderRadius: 3, cursor: 'pointer', fontSize: 10, fontFamily: "'Courier New', monospace" }}>BOLL</button>
            <button onClick={() => setShowRSI(prev => !prev)} style={{ background: showRSI ? '#AB47BC' : C.BG_PRIMARY, color: showRSI ? '#FFF' : C.COLOR_TEXT_MUTED, border: `1px solid ${showRSI ? '#AB47BC' : C.COLOR_BORDER}`, padding: '4px 8px', borderRadius: 3, cursor: 'pointer', fontSize: 10, fontFamily: "'Courier New', monospace" }}>RSI</button>
            <button onClick={() => setShowMACD(prev => !prev)} style={{ background: showMACD ? '#2196F3' : C.BG_PRIMARY, color: showMACD ? '#FFF' : C.COLOR_TEXT_MUTED, border: `1px solid ${showMACD ? '#2196F3' : C.COLOR_BORDER}`, padding: '4px 8px', borderRadius: 3, cursor: 'pointer', fontSize: 10, fontFamily: "'Courier New', monospace" }}>MACD</button>
            <div style={{ width: 1, height: 24, background: C.COLOR_BORDER }} />
          </>
        )}

        <button onClick={() => setShowTimeAndSales(prev => !prev)} style={{ background: showTimeAndSales ? C.BULLISH : C.BG_PRIMARY, color: showTimeAndSales ? C.BG_PRIMARY : C.COLOR_TEXT_MUTED, border: `1px solid ${showTimeAndSales ? C.BULLISH : C.COLOR_BORDER}`, padding: '4px 10px', borderRadius: 3, cursor: 'pointer', fontSize: 11, fontFamily: "'Courier New', monospace" }}>
          T&S
        </button>

        <button onClick={() => setShowAlertPanel(prev => !prev)} style={{ background: showAlertPanel ? '#F2C94C' : C.BG_PRIMARY, color: showAlertPanel ? C.BG_PRIMARY : C.COLOR_TEXT_MUTED, border: `1px solid ${showAlertPanel ? '#F2C94C' : C.COLOR_BORDER}`, padding: '4px 10px', borderRadius: 3, cursor: 'pointer', fontSize: 11, fontFamily: "'Courier New', monospace" }}>
          ALERTS
        </button>

        <button onClick={() => setShowSettings(prev => !prev)} style={{ background: showSettings ? C.BULLISH : C.BG_PRIMARY, color: showSettings ? C.BG_PRIMARY : C.COLOR_TEXT_MUTED, border: `1px solid ${showSettings ? C.BULLISH : C.COLOR_BORDER}`, padding: '4px 10px', borderRadius: 3, cursor: 'pointer', fontSize: 13, fontFamily: "'Courier New', monospace" }}>
          &#9881;
        </button>

        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 11 }}>Bid:</span>
        <span style={{ color: C.BULLISH, fontWeight: 'bold', fontSize: 12 }}>{vs?.bestBid?.toFixed(2) || '\u2014'}</span>
        <span style={{ fontSize: 9, color: C.COLOR_TEXT_MUTED }}>({vs?.bestBidSize?.toFixed(0) || '0'})</span>
        <span style={{ fontSize: 11, marginLeft: 8 }}>Ask:</span>
        <span style={{ color: C.BEARISH, fontWeight: 'bold', fontSize: 12 }}>{vs?.bestAsk?.toFixed(2) || '\u2014'}</span>
        <span style={{ fontSize: 9, color: C.COLOR_TEXT_MUTED }}>({vs?.bestAskSize?.toFixed(0) || '0'})</span>
      </div>

      <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        {activeTab === 'heatmap' && (
          <HeatmapPage
            featureSAB={featureSAB.current}
            sab={sab.current}
            viewState={vs}
            heatmapRef={heatmapRef}
            drawingManager={drawingManagerRef.current}
            alertManager={alertManagerRef.current}
            activeTool={activeTool}
            onToolSelect={handleToolSelect}
          />
        )}
        {activeTab === 'footprint' && (
          <FootprintPage
            featureSAB={featureSAB.current}
            sab={sab.current}
            viewState={vs}
            footprintRef={footprintRef}
            drawingManager={drawingManagerRef.current}
            alertManager={alertManagerRef.current}
            activeTool={activeTool}
            onToolSelect={handleToolSelect}
            indicators={indicators}
            showRSI={showRSI}
            showMACD={showMACD}
          />
        )}
        <HealthHUD stats={getStats} />

        <SettingsPanel
          visible={showSettings}
          onClose={() => setShowSettings(false)}
          heatmapRef={heatmapRef}
          footprintRef={footprintRef}
        />

        <AlertPanel
          visible={showAlertPanel}
          alerts={alerts}
          onAddAlert={handleAddAlert}
          onRemoveAlert={handleRemoveAlert}
          onClose={() => setShowAlertPanel(false)}
        />
      </div>

      <TimeAndSales visible={showTimeAndSales} />

      <div style={{ height: 28, background: C.STATUSBAR_BG, borderTop: `1px solid ${C.COLOR_BORDER}`, display: 'flex', alignItems: 'center', padding: '0 12px', fontFamily: "'Courier New', monospace", fontSize: 10, color: C.COLOR_TEXT_MUTED, gap: 16, flexShrink: 0 }}>
        <span style={{ color: C.BULLISH }}>NEXUS FLOW</span>
        <span style={{ color: C.COLOR_BORDER }}>|</span>
        <span>v0.3.0</span>
        <span style={{ color: C.COLOR_BORDER }}>|</span>
        <span>{activeTab === 'heatmap' ? 'Bookmap Mode' : 'GoCharting Mode'}</span>
        <span style={{ color: C.COLOR_BORDER }}>|</span>
        <span>Cell Vol: ON</span>
        <span style={{ color: C.COLOR_BORDER }}>|</span>
        <span>LOB Depth: LIVE</span>
        <span style={{ color: C.COLOR_BORDER }}>|</span>
        {indicators.length > 0 && <span>Indicators: {indicators.map(i => i.type.toUpperCase()).join(', ')}</span>}
        {indicators.length > 0 && <span style={{ color: C.COLOR_BORDER }}>|</span>}
        {alerts.length > 0 && <span>Alerts: {alerts.filter(a => !a.triggered).length} active</span>}
        {alerts.length > 0 && <span style={{ color: C.COLOR_BORDER }}>|</span>}
        <div style={{ flex: 1 }} />
        <span>SAB: {sab.current ? `${C.SAB_SIZE_MB}MB` : 'N/A'}</span>
        <span style={{ color: C.COLOR_BORDER }}>|</span>
        <span style={{ color: ringBuffer.current ? C.BULLISH : C.COLOR_TEXT_MUTED }}>Ring: {ringBuffer.current ? 'ACTIVE' : 'PENDING'}</span>
        <span style={{ color: C.COLOR_BORDER }}>|</span>
        <span>P&L: <b style={{ color: C.BULLISH }}>+$0.00</b></span>
      </div>
    </div>
  );
}

export default App;
