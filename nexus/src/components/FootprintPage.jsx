import { useRef, useEffect, useCallback, useState } from 'react';
import { FootprintCanvas } from '../renderer/FootprintCanvas.js';
import { CrosshairOverlay } from '../renderer/CrosshairOverlay.js';
import { DrawingManager } from '../renderer/DrawingManager.js';
import { AlertManager } from '../renderer/AlertManager.js';
import { drawSMA, drawEMA, drawBollinger, drawRSI, drawMACD } from '../renderer/IndicatorOverlay.js';
import { sma, ema, rsi, macd, bollinger } from '../renderer/IndicatorEngine.js';
import DrawingToolbar, { CURSORS } from './DrawingToolbar.jsx';
import CVDOscillator from './CVDOscillator.jsx';
import { FEATURE, MAX_PRICE_LEVELS, MAX_CANDLES } from '../types/MemoryLayout.js';
import TerminalConfig from '../config/TerminalConfig.js';
import { getOrderRouter } from '../trading/OrderRouter.js';

const C = TerminalConfig;
const DOM_ROW_COUNT = 40;

export default function FootprintPage({
  featureSAB, sab, viewState, footprintRef, onMouseMove,
  drawingManager, alertManager, activeTool, onToolSelect,
  indicators, showRSI, showMACD,
}) {
  const canvasRef = useRef(null);
  const fpRef = useRef(null);
  const containerRef = useRef(null);
  const domRef = useRef(null);
  const crosshairCanvasRef = useRef(null);
  const crosshairRef = useRef(null);
  const overlayCanvasRef = useRef(null);
  const indicatorCanvasRef = useRef(null);
  const rsiCanvasRef = useRef(null);
  const macdCanvasRef = useRef(null);
  const [orderPopup, setOrderPopup] = useState(null);
  const orderMarkersRef = useRef([]);
  const drawPointsRef = useRef([]);
  const animFrameRef = useRef(null);

  const priceToY = useCallback((price) => {
    if (!viewState) return 0;
    const h = canvasRef.current?.height || 600;
    return h - ((price - viewState.priceMin) / (viewState.priceMax - viewState.priceMin)) * h;
  }, [viewState]);

  const yToPrice = useCallback((y) => {
    if (!viewState) return 0;
    const h = canvasRef.current?.height || 600;
    return viewState.priceMin + ((h - y) / h) * (viewState.priceMax - viewState.priceMin);
  }, [viewState]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !featureSAB) return;

    const rect = containerRef.current?.getBoundingClientRect();
    const w = Math.floor(rect?.width || 1200);
    const h = Math.floor(rect?.height || 800);
    canvas.width = w;
    canvas.height = h;

    const fp = new FootprintCanvas(canvas, featureSAB);
    fpRef.current = fp;
    if (footprintRef) footprintRef.current = fp;

    fp.start();

    if (domRef.current) buildDOMLadder(domRef.current, (price, side) => {
      handleDOMClick(price, side);
    });

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          fp.resize(Math.floor(width), Math.floor(height));
          if (crosshairRef.current) {
            crosshairRef.current.resize(Math.floor(width), Math.floor(height));
            if (crosshairCanvasRef.current) {
              crosshairCanvasRef.current.style.width = width + 'px';
              crosshairCanvasRef.current.style.height = height + 'px';
            }
          }
          if (overlayCanvasRef.current) {
            overlayCanvasRef.current.width = Math.floor(width);
            overlayCanvasRef.current.height = Math.floor(height);
            overlayCanvasRef.current.style.width = width + 'px';
            overlayCanvasRef.current.style.height = height + 'px';
          }
          if (indicatorCanvasRef.current) {
            indicatorCanvasRef.current.width = Math.floor(width);
            indicatorCanvasRef.current.height = Math.floor(height);
            indicatorCanvasRef.current.style.width = width + 'px';
            indicatorCanvasRef.current.style.height = height + 'px';
          }
          if (rsiCanvasRef.current) {
            rsiCanvasRef.current.width = Math.floor(width);
            rsiCanvasRef.current.height = 100;
            rsiCanvasRef.current.style.width = width + 'px';
          }
          if (macdCanvasRef.current) {
            macdCanvasRef.current.width = Math.floor(width);
            macdCanvasRef.current.height = 100;
            macdCanvasRef.current.style.width = width + 'px';
          }
        }
      }
    });
    if (containerRef.current) resizeObserver.observe(containerRef.current);

    return () => { fp.stop(); resizeObserver.disconnect(); };
  }, [featureSAB]);

  useEffect(() => {
    const chCanvas = crosshairCanvasRef.current;
    if (!chCanvas) return;
    const rect = containerRef.current?.getBoundingClientRect();
    const w = Math.floor(rect?.width || 1200);
    const h = Math.floor(rect?.height || 800);
    chCanvas.width = w;
    chCanvas.height = h;
    const ch = new CrosshairOverlay(chCanvas);
    crosshairRef.current = ch;
  }, [featureSAB]);

  useEffect(() => {
    const oCanvas = overlayCanvasRef.current;
    if (!oCanvas) return;
    const rect = containerRef.current?.getBoundingClientRect();
    oCanvas.width = Math.floor(rect?.width || 1200);
    oCanvas.height = Math.floor(rect?.height || 800);
  }, [featureSAB]);

  useEffect(() => {
    const iCanvas = indicatorCanvasRef.current;
    if (!iCanvas) return;
    const rect = containerRef.current?.getBoundingClientRect();
    iCanvas.width = Math.floor(rect?.width || 1200);
    iCanvas.height = Math.floor(rect?.height || 800);
  }, [featureSAB]);

  useEffect(() => {
    if (fpRef.current && viewState) fpRef.current.updateViewState(viewState);
    if (crosshairRef.current && viewState) crosshairRef.current.updateViewState(viewState);
  }, [viewState, viewState?.priceMin, viewState?.priceMax, viewState?.zoom, viewState?.scrollX]);

  useEffect(() => {
    if (!domRef.current || !viewState || !featureSAB) return;
    updateDOMLadder(domRef.current, viewState, featureSAB);
  }, [viewState, viewState?.priceMin, viewState?.priceMax, featureSAB]);

  useEffect(() => {
    const renderOverlay = () => {
      const oCanvas = overlayCanvasRef.current;
      if (!oCanvas || !drawingManager || !alertManager || !viewState) { animFrameRef.current = requestAnimationFrame(renderOverlay); return; }
      const ctx = oCanvas.getContext('2d');
      ctx.clearRect(0, 0, oCanvas.width, oCanvas.height);

      const chartWidth = oCanvas.width - (fpRef.current?.volumeProfileWidth || 80);
      drawingManager.drawAll(ctx, viewState, chartWidth, oCanvas.height, priceToY, yToPrice);
      alertManager.drawAlerts(ctx, viewState, chartWidth, priceToY);

      animFrameRef.current = requestAnimationFrame(renderOverlay);
    };
    animFrameRef.current = requestAnimationFrame(renderOverlay);
    return () => { if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current); };
  }, [drawingManager, alertManager, viewState, priceToY, yToPrice]);

  useEffect(() => {
    const renderIndicators = () => {
      const iCanvas = indicatorCanvasRef.current;
      if (!iCanvas || !featureSAB || !viewState || !indicators) return;
      const ctx = iCanvas.getContext('2d');
      ctx.clearRect(0, 0, iCanvas.width, iCanvas.height);
      if (!fpRef.current) return;

      const chartWidth = iCanvas.width - (fpRef.current.volumeProfileWidth || 80);
      const { zoom, scrollX } = viewState;
      const candleCount = new Int32Array(featureSAB, FEATURE.HEADER_SIZE / 4, 1)[0] || 0;
      const visibleCandles = Math.max(1, Math.floor(chartWidth / zoom));
      const startCandle = Math.max(0, candleCount - visibleCandles - scrollX);
      const endCandle = Math.min(candleCount, startCandle + visibleCandles);

      const closes = new Float64Array(featureSAB, FEATURE.OHLC_CLOSE_OFFSET, MAX_CANDLES);
      const highs = new Float64Array(featureSAB, FEATURE.OHLC_HIGH_OFFSET, MAX_CANDLES);
      const lows = new Float64Array(featureSAB, FEATURE.OHLC_LOW_OFFSET, MAX_CANDLES);

      for (const ind of indicators) {
        if (ind.type === 'sma') {
          const result = sma(closes, ind.period || 20);
          drawSMA(ctx, result.data, startCandle, endCandle, chartWidth, viewState, null, priceToY);
        } else if (ind.type === 'ema') {
          const result = ema(closes, ind.period || 20);
          drawEMA(ctx, result.data, startCandle, endCandle, chartWidth, viewState, null, priceToY);
        } else if (ind.type === 'bollinger') {
          const result = bollinger(closes, ind.period || 20, ind.stdDev || 2);
          drawBollinger(ctx, result.upper, result.middle, result.lower, startCandle, endCandle, chartWidth, viewState, priceToY);
        }
      }

      if (showRSI) {
        const rsiCanvas = rsiCanvasRef.current;
        if (rsiCanvas) {
          const rCtx = rsiCanvas.getContext('2d');
          rCtx.clearRect(0, 0, rsiCanvas.width, rsiCanvas.height);
          const result = rsi(closes, 14);
          drawRSI(rCtx, result.data, startCandle, endCandle, chartWidth, viewState, 100);
        }
      }

      if (showMACD) {
        const macdCanvas = macdCanvasRef.current;
        if (macdCanvas) {
          const mCtx = macdCanvas.getContext('2d');
          mCtx.clearRect(0, 0, macdCanvas.width, macdCanvas.height);
          const result = macd(closes, 12, 26, 9);
          drawMACD(mCtx, result.macdLine, result.signalLine, result.histogram, startCandle, endCandle, chartWidth, viewState, 100);
        }
      }
    };

    const id = setInterval(renderIndicators, 200);
    return () => clearInterval(id);
  }, [featureSAB, viewState, indicators, showRSI, showMACD, priceToY]);

  const handleWheel = useCallback((e) => {
    e.preventDefault();
    if (!viewState) return;

    if (e.ctrlKey || e.metaKey) {
      const zoomDelta = e.deltaY > 0 ? -2 : 2;
      viewState.zoom = Math.max(4, Math.min(200, viewState.zoom + zoomDelta));
    } else {
      const priceDelta = e.deltaY * 0.25;
      viewState.priceMin += priceDelta;
      viewState.priceMax += priceDelta;
    }
    viewState.pixelsPerTick =
      (canvasRef.current?.height || 600) /
      ((viewState.priceMax - viewState.priceMin) / 0.25);

    if (fpRef.current) fpRef.current.updateViewState(viewState);
    if (domRef.current && featureSAB) updateDOMLadder(domRef.current, viewState, featureSAB);
  }, [viewState, featureSAB]);

  const handleMouseMove = useCallback((e) => {
    if (!crosshairRef.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    crosshairRef.current.setMousePosition(x, y);
    if (onMouseMove) onMouseMove(e);
  }, [onMouseMove]);

  const handleMouseLeave = useCallback(() => {
    if (crosshairRef.current) crosshairRef.current.setMousePosition(-1, -1);
  }, []);

  const handleChartClick = useCallback((e) => {
    if (!activeTool || !drawingManager || !viewState) return;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const price = yToPrice(y);

    if (activeTool === 'eraser') {
      const hit = drawingManager.hitTest(x, y);
      if (hit) drawingManager.removeDrawing(hit.id);
      return;
    }
    if (activeTool === 'clear_all') {
      drawingManager.clearAll();
      if (onToolSelect) onToolSelect(null);
      return;
    }

    const points = drawPointsRef.current;

    if (activeTool === 'horizontal_line') {
      drawingManager.addDrawing('horizontal_line', [{ price, x, y }], '#F2C94C');
      drawPointsRef.current = [];
    } else if (activeTool === 'trend_line' || activeTool === 'ray' || activeTool === 'fibonacci_retracement') {
      points.push({ price, x, y });
      if (points.length >= 2) {
        drawingManager.addDrawing(activeTool, [points[0], points[1]], '#F2C94C');
        drawPointsRef.current = [];
      }
    }
  }, [activeTool, drawingManager, viewState, yToPrice, onToolSelect]);

  const handleDOMClick = useCallback((price, side) => {
    const orderRouter = getOrderRouter();
    const orderId = orderRouter.submitLimitOrder('ES', side, price, 1);
    orderMarkersRef.current.push({ price, side, orderId });
    setOrderPopup({ price, side, orderId, x: 0, y: 0 });
    setTimeout(() => setOrderPopup(null), 2000);
  }, []);

  const cursorStyle = activeTool ? (CURSORS[activeTool] || 'crosshair') : 'default';

  const renderOrderMarkers = () => {
    if (!viewState) return null;
    return orderMarkersRef.current.map((marker, i) => {
      const y = ((viewState.priceMax - marker.price) / (viewState.priceMax - viewState.priceMin)) * 100;
      return (
        <div key={i} style={{
          position: 'absolute',
          left: 0,
          top: `${Math.max(0, Math.min(100, y))}%`,
          width: '100%',
          height: 2,
          background: marker.side === 'BUY' ? C.BULLISH : C.BEARISH,
          opacity: 0.6,
          pointerEvents: 'none',
        }} />
      );
    });
  };

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }} onWheel={handleWheel}>

        <div style={{ width: 180, background: C.BG_SURFACE, borderRight: `1px solid ${C.COLOR_BORDER}`, overflow: 'hidden', position: 'relative', flexShrink: 0 }}>
          <div style={{ position: 'sticky', top: 0, background: C.BG_SURFACE, borderBottom: `1px solid ${C.COLOR_BORDER}`, padding: '4px 8px', fontSize: 9, color: C.COLOR_TEXT_MUTED, fontFamily: 'monospace', letterSpacing: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <button onClick={() => handleDOMClick(viewState?.bestBid || 4500, 'BUY')} style={{ background: C.BULLISH, color: C.BG_PRIMARY, border: 'none', borderRadius: 2, padding: '2px 6px', cursor: 'pointer', fontSize: 9, fontFamily: "'Courier New', monospace", fontWeight: 'bold' }}>BUY</button>
            <span>PRICE</span>
            <button onClick={() => handleDOMClick(viewState?.bestAsk || 4500.25, 'SELL')} style={{ background: C.BEARISH, color: C.BG_PRIMARY, border: 'none', borderRadius: 2, padding: '2px 6px', cursor: 'pointer', fontSize: 9, fontFamily: "'Courier New', monospace", fontWeight: 'bold' }}>SELL</button>
          </div>
          <div ref={domRef} style={{ height: 'calc(100% - 28px)', overflow: 'hidden' }} />
        </div>

        <div ref={containerRef} style={{ flex: 1, position: 'relative', overflow: 'hidden', cursor: cursorStyle }}
          onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave}
          onClick={handleChartClick}>
          <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block', background: C.BG_PRIMARY }} />

          <canvas ref={indicatorCanvasRef} style={{
            position: 'absolute', top: 0, left: 0,
            width: '100%', height: '100%',
            pointerEvents: 'none', zIndex: 3,
          }} />

          <canvas ref={overlayCanvasRef} style={{
            position: 'absolute', top: 0, left: 0,
            width: '100%', height: '100%',
            pointerEvents: 'none', zIndex: 4,
          }} />

          <canvas ref={crosshairCanvasRef} style={{
            position: 'absolute', top: 0, left: 0,
            width: '100%', height: '100%',
            pointerEvents: 'none', zIndex: 5,
          }} />

          <DrawingToolbar activeTool={activeTool} onToolSelect={onToolSelect} />

          {renderOrderMarkers()}

          {orderPopup && (
            <div style={{
              position: 'absolute', top: '50%', left: '50%',
              transform: 'translate(-50%, -50%)',
              background: 'rgba(11,14,17,0.95)',
              border: `1px solid ${orderPopup.side === 'BUY' ? C.BULLISH : C.BEARISH}`,
              borderRadius: 4, padding: '8px 12px',
              fontFamily: "'Courier New', monospace", fontSize: 11,
              color: C.COLOR_TEXT_PRIMARY, zIndex: 50,
            }}>
              <div style={{ color: orderPopup.side === 'BUY' ? C.BULLISH : C.BEARISH, fontWeight: 'bold' }}>
                {orderPopup.side} LIMIT
              </div>
              <div>@ {orderPopup.price?.toFixed(2)}</div>
              <div style={{ color: C.COLOR_TEXT_MUTED, fontSize: 9 }}>ID: {orderPopup.orderId}</div>
            </div>
          )}
        </div>
      </div>

      {showRSI && (
        <div style={{ height: 100, borderTop: `1px solid ${C.COLOR_BORDER}`, flexShrink: 0 }}>
          <canvas ref={rsiCanvasRef} style={{ width: '100%', height: 100, display: 'block', background: C.BG_PRIMARY }} />
        </div>
      )}

      {showMACD && (
        <div style={{ height: 100, borderTop: `1px solid ${C.COLOR_BORDER}`, flexShrink: 0 }}>
          <canvas ref={macdCanvasRef} style={{ width: '100%', height: 100, display: 'block', background: C.BG_PRIMARY }} />
        </div>
      )}

      <div style={{ height: 80, borderTop: `1px solid ${C.COLOR_BORDER}`, display: 'flex' }}>
        <div style={{ width: 180, background: C.BG_SURFACE, borderRight: `1px solid ${C.COLOR_BORDER}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, color: C.COLOR_TEXT_MUTED, fontFamily: 'monospace', letterSpacing: 1 }}>CVD</div>
        <div style={{ flex: 1 }}>
          <CVDOscillator featureSAB={featureSAB} />
        </div>
      </div>
    </div>
  );
}

function buildDOMLadder(container, onClick) {
  for (let i = 0; i < DOM_ROW_COUNT; i++) {
    const row = document.createElement('div');
    row.style.cssText = `display:flex; align-items:center; justify-content:space-between; height:20px; padding:0 6px; font-family:'Courier New',monospace; font-size:10px; color:${C.COLOR_TEXT_MUTED}; border-bottom:1px solid ${C.COLOR_BORDER}; cursor:pointer; transition:background 0.05s;`;
    row.dataset.idx = i;

    const bidCol = document.createElement('span');
    bidCol.style.cssText = `color:${C.BEARISH}; min-width:40px; text-align:right;`;
    bidCol.className = 'dom-bid';

    const priceCol = document.createElement('span');
    priceCol.style.cssText = `color:${C.COLOR_TEXT_PRIMARY}; min-width:60px; text-align:center; font-weight:bold;`;
    priceCol.className = 'dom-price';

    const askCol = document.createElement('span');
    askCol.style.cssText = `color:${C.BULLISH}; min-width:40px; text-align:left;`;
    askCol.className = 'dom-ask';

    row.appendChild(bidCol);
    row.appendChild(priceCol);
    row.appendChild(askCol);

    row.addEventListener('mouseenter', () => { row.style.background = C.BG_SURFACE; });
    row.addEventListener('mouseleave', () => { row.style.background = 'transparent'; });
    row.addEventListener('click', () => {
      const priceText = priceCol.textContent;
      const price = parseFloat(priceText);
      if (!isNaN(price) && onClick) {
        const side = i < DOM_ROW_COUNT / 2 ? 'SELL' : 'BUY';
        onClick(price, side);
      }
    });

    container.appendChild(row);
  }
}

function updateDOMLadder(container, viewState, featureSAB) {
  const { priceMin, priceMax } = viewState;
  const rows = container.children;
  const numLevels = Math.min(DOM_ROW_COUNT, rows.length);
  const step = (priceMax - priceMin) / numLevels;

  let lobBidDepth, lobAskDepth;
  try {
    lobBidDepth = new Float64Array(featureSAB, FEATURE.LOB_BID_DEPTH_OFFSET, MAX_PRICE_LEVELS);
    lobAskDepth = new Float64Array(featureSAB, FEATURE.LOB_ASK_DEPTH_OFFSET, MAX_PRICE_LEVELS);
  } catch (e) {
    return;
  }

  for (let i = 0; i < numLevels; i++) {
    const price = priceMax - i * step;
    const row = rows[i];
    if (!row) continue;

    const priceCol = row.querySelector('.dom-price');
    const bidCol = row.querySelector('.dom-bid');
    const askCol = row.querySelector('.dom-ask');

    if (priceCol) priceCol.textContent = price.toFixed(2);

    const pIdx = Math.floor(price * 1000);
    const bidSize = (pIdx >= 0 && pIdx < MAX_PRICE_LEVELS) ? lobBidDepth[pIdx] : 0;
    const askSize = (pIdx >= 0 && pIdx < MAX_PRICE_LEVELS) ? lobAskDepth[pIdx] : 0;

    if (bidCol) bidCol.textContent = bidSize > 0 ? bidSize.toFixed(0) : '';
    if (askCol) askCol.textContent = askSize > 0 ? askSize.toFixed(0) : '';

    const bestBid = viewState.bestBid || 0;
    const bestAsk = viewState.bestAsk || 0;
    if (Math.abs(price - bestBid) < step * 0.5) {
      if (priceCol) { priceCol.style.color = C.BULLISH; priceCol.style.background = 'rgba(38,166,154,0.12)'; }
    } else if (Math.abs(price - bestAsk) < step * 0.5) {
      if (priceCol) { priceCol.style.color = C.BEARISH; priceCol.style.background = 'rgba(239,83,80,0.12)'; }
    } else {
      if (priceCol) { priceCol.style.color = C.COLOR_TEXT_MUTED; priceCol.style.background = 'transparent'; }
    }
  }
}
