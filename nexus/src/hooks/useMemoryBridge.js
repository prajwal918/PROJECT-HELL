import { useRef, useEffect, useCallback } from 'react';
import { SAB_SIZE, FEATURE_SAB_SIZE, CONTROL, SLOT_SIZE, ACTION, SIDE, FLAG_IS_TRADE, FLAG_IS_BID, FEATURE, MAX_PRICE_LEVELS } from '../types/MemoryLayout.js';
import { RingBuffer, createSlot } from '../workers/memory/RingBuffer.js';
import { tradeBus } from '../trading/TradeBus.js';

const DEFAULT_WS_URL = 'ws://localhost:9001';
const BUBBLE_TRADE_THRESHOLD = 10;

export function useMemoryBridge(options = {}) {
  const {
    wsUrl = DEFAULT_WS_URL,
    useMock = true,
    mockRate = 10000,
  } = options;

  const sabRef = useRef(null);
  const featureSABRef = useRef(null);
  const ringBufferRef = useRef(null);
  const workerRef = useRef(null);
  const algoWorkerRef = useRef(null);
  const rafIdRef = useRef(null);
  const statsRef = useRef({
    ticksPerSecond: 0,
    frameTimeMs: 0,
    gcPauseCount: 0,
    ringBufferFill: 0,
    wsStatus: 'INIT',
    bestBidSize: 0,
    bestAskSize: 0,
  });
  const outSlotRef = useRef(createSlot());
  const lastFrameTimeRef = useRef(0);
  const viewStateRef = useRef({
    scrollX: 0,
    zoom: 40,
    priceMin: 4490,
    priceMax: 4510,
    pixelsPerTick: 0,
    bestBid: 4500.0,
    bestAsk: 4500.25,
    bestBidSize: 0,
    bestAskSize: 0,
  });
  const heatmapRef = useRef(null);
  const footprintRef = useRef(null);
  const domRef = useRef(null);

  useEffect(() => {
    const sab = new SharedArrayBuffer(SAB_SIZE);
    sabRef.current = sab;

    const featureSAB = new SharedArrayBuffer(FEATURE_SAB_SIZE);
    featureSABRef.current = featureSAB;

    const rb = RingBuffer.create(sab);
    RingBuffer.init(sab);
    ringBufferRef.current = rb;

    const ingestionWorker = new Worker(
      new URL('../workers/IngestionWorker.js', import.meta.url),
      { type: 'module' }
    );
    workerRef.current = ingestionWorker;

    ingestionWorker.onerror = (e) => {
      console.error('IngestionWorker Error:', e.message, 'at', e.filename, ':', e.lineno);
    };

    ingestionWorker.postMessage({
      type: 'init',
      data: { sab, wsUrl, useMock, mockRate },
    });

    ingestionWorker.onmessage = (e) => {
      if (e.data.type === 'status') {
        statsRef.current.wsStatus = e.data.status;
      }
      if (e.data.type === 'stats') {
        statsRef.current.ticksPerSecond = e.data.data.ticksPerSecond;
        statsRef.current.ringBufferFill = e.data.data.ringBufferFill;
        viewStateRef.current.bestBid = e.data.data.bestBid;
        viewStateRef.current.bestAsk = e.data.data.bestAsk;
        viewStateRef.current.bestBidSize = e.data.data.bestBidSize || 0;
        viewStateRef.current.bestAskSize = e.data.data.bestAskSize || 0;
        statsRef.current.bestBidSize = e.data.data.bestBidSize || 0;
        statsRef.current.bestAskSize = e.data.data.bestAskSize || 0;
      }
    };

    let algoWorker = null;
    try {
      algoWorker = new Worker(
        new URL('../workers/AlgorithmWorker.js', import.meta.url),
        { type: 'module' }
      );
      algoWorkerRef.current = algoWorker;
      algoWorker.postMessage({ type: 'init', data: { sab, featureSAB } });
    } catch (e) {
      console.warn('AlgorithmWorker not available:', e.message);
    }

    const lobBidDepth = new Float64Array(featureSAB, FEATURE.LOB_BID_DEPTH_OFFSET, MAX_PRICE_LEVELS);
    const lobAskDepth = new Float64Array(featureSAB, FEATURE.LOB_ASK_DEPTH_OFFSET, MAX_PRICE_LEVELS);

    const rafLoop = (timestamp) => {
      const lastTime = lastFrameTimeRef.current;
      const frameDelta = lastTime ? timestamp - lastTime : 16.67;
      lastFrameTimeRef.current = timestamp;

      if (frameDelta > 20) statsRef.current.gcPauseCount++;
      statsRef.current.frameTimeMs = frameDelta;

      const outSlot = outSlotRef.current;
      let drainCount = 0;
      const maxDrain = 8192;
      let gotTopOfBook = false;
      let lastTradePrice = 0;
      let lastTradeSize = 0;
      let lastTradeSide = SIDE.BID;

      while (rb.available() > 0 && drainCount < maxDrain) {
        if (rb.pop(outSlot)) {
          drainCount++;

          if (heatmapRef.current && outSlot.action === ACTION.TOP_OF_BOOK) {
            gotTopOfBook = true;
          }

          if (outSlot.action === ACTION.TRADE || (outSlot.flags & FLAG_IS_TRADE)) {
            lastTradePrice = outSlot.price;
            lastTradeSize = outSlot.trade_size;
            lastTradeSide = outSlot.side;
            tradeBus.publish({ price: outSlot.price, size: outSlot.trade_size, side: outSlot.side });
          }
        } else {
          break;
        }
      }

      if (gotTopOfBook && heatmapRef.current) {
        heatmapRef.current.advanceHeatmapColumn();
      }

      if (heatmapRef.current && lastTradePrice > 0 && lastTradeSize > BUBBLE_TRADE_THRESHOLD) {
        const w = heatmapRef.current.canvas.width;
        const x = w;
        const y = lastTradePrice;
        const maxRadius = Math.min(lastTradeSize / 50, 15);
        const radius = Math.max(3, maxRadius);
        if (lastTradeSide === SIDE.ASK) {
          heatmapRef.current.addBubble(x, y, radius, 0.149, 0.651, 0.604, 0.8, 0);
        } else {
          heatmapRef.current.addBubble(x, y, radius, 0.937, 0.325, 0.314, 0.8, 0);
        }
      }

      if (heatmapRef.current) heatmapRef.current.render(timestamp);
      if (footprintRef.current) footprintRef.current.render();

      if (frameDelta > 14) {
        console.warn(`[NEXUS] Frame budget exceeded: ${frameDelta.toFixed(2)}ms`);
      }

      rafIdRef.current = requestAnimationFrame(rafLoop);
    };

    rafIdRef.current = requestAnimationFrame(rafLoop);

    return () => {
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
      ingestionWorker.postMessage({ type: 'disconnect' });
      ingestionWorker.terminate();
      if (algoWorker) algoWorker.terminate();
    };
  }, []);

  const getStats = useCallback(() => ({ ...statsRef.current }), []);
  const startMock = useCallback((rate) => {
    if (workerRef.current) workerRef.current.postMessage({ type: 'start-mock', data: { rate } });
  }, []);
  const stopMock = useCallback(() => {
    if (workerRef.current) workerRef.current.postMessage({ type: 'stop-mock', data: {} });
  }, []);
  const connect = useCallback((url) => {
    if (workerRef.current) workerRef.current.postMessage({ type: 'connect', data: { wsUrl: url || wsUrl } });
  }, [wsUrl]);
  const setCandleInterval = useCallback((intervalMs) => {
    if (algoWorkerRef.current) algoWorkerRef.current.postMessage({ type: 'set-candle-interval', data: { intervalMs } });
  }, []);

  return {
    sab: sabRef,
    featureSAB: featureSABRef,
    ringBuffer: ringBufferRef,
    worker: workerRef,
    algoWorker: algoWorkerRef,
    viewState: viewStateRef,
    heatmapRef,
    footprintRef,
    domRef,
    getStats,
    startMock,
    stopMock,
    connect,
    setCandleInterval,
  };
}
