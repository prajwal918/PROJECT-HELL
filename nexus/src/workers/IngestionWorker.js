import { RingBuffer, createSlot } from './memory/RingBuffer.js';

const SAB_SIZE = 512 * 1024 * 1024;
const HEADER_SIZE = 128;
const SLOT_SIZE = 128;
const SLOT_COUNT = Math.floor((SAB_SIZE - HEADER_SIZE) / SLOT_SIZE);
const CONTROL_WRITE_INDEX = 0;
const CONTROL_READ_INDEX = 4;
const CONTROL_TICK_COUNT = 24;

const ACTION = { INSERT: 0, UPDATE: 1, DELETE: 2, TRADE: 3, TOP_OF_BOOK: 4 };
const SIDE = { BID: 0, ASK: 1 };
const FLAG_IS_BID = 1 << 0;
const FLAG_IS_TRADE = 1 << 1;
const SLOT_ACTION_OFFSET = 60;

const LOB_DEPTH = 4096;
const TRADE_BUFFER_SIZE = 8192;

let ringBuffer = null;
let ws = null;
let reconnectAttempts = 0;
let maxReconnectAttempts = 10;
let lastSeqNum = 0;
let isReconnecting = false;

const bidBook = new Float64Array(LOB_DEPTH * 2);
const askBook = new Float64Array(LOB_DEPTH * 2);
const tradeBuffer = new Float64Array(TRADE_BUFFER_SIZE * 4);
let tradeBufferIdx = 0;

const bidPriceToIdx = new Map();
const askPriceToIdx = new Map();
let bidCount = 0;
let askCount = 0;
let bestBid = 0;
let bestAsk = 0;
let bestBidSizeVal = 0;
let bestAskSizeVal = 0;

function bestBidSizeFn() {
  for (let i = 0; i < bidCount; i++) {
    if (bidBook[i * 2] === bestBid) return bidBook[i * 2 + 1];
  }
  return 0;
}
function bestAskSizeFn() {
  for (let i = 0; i < askCount; i++) {
    if (askBook[i * 2] === bestAsk) return askBook[i * 2 + 1];
  }
  return 0;
}

let ticksPerSecond = 0;
let tickCounter = 0;
setInterval(() => {
  ticksPerSecond = tickCounter;
  tickCounter = 0;
}, 1000);

const slot = createSlot();

function decodeFlatBufferTick(buf, len) {
  const view = new DataView(buf, 0, len);
  let offset = 0;
  const tableOffset = offset;
  offset += 4;
  const vtableOffset = view.getInt32(tableOffset, true);
  const vtableLoc = tableOffset - vtableOffset;
  const vtableSize = view.getInt16(vtableLoc, true);
  const fieldCount = (vtableSize - 4) / 2;

  const result = {
    timestamp_ns: 0, price: 0, bid_size: 0, ask_size: 0,
    trade_size: 0, order_id: 0, action: 0, side: 0, flags: 0, seq_num: 0,
  };

  function getFieldOffset(fieldIdx) {
    if (fieldIdx >= fieldCount) return 0;
    const voff = vtableLoc + 4 + fieldIdx * 2;
    const rel = view.getInt16(voff, true);
    return rel !== 0 ? tableOffset + rel : 0;
  }

  const f0 = getFieldOffset(0); if (f0) result.timestamp_ns = Number(view.getBigUint64(f0, true));
  const f1 = getFieldOffset(1); if (f1) result.price = view.getFloat64(f1, true);
  const f2 = getFieldOffset(2); if (f2) result.bid_size = view.getFloat32(f2, true);
  const f3 = getFieldOffset(3); if (f3) result.ask_size = view.getFloat32(f3, true);
  const f4 = getFieldOffset(4); if (f4) result.trade_size = view.getFloat32(f4, true);
  const f5 = getFieldOffset(5); if (f5) result.order_id = view.getUint32(f5, true);
  const f6 = getFieldOffset(6); if (f6) result.action = view.getUint8(f6);
  const f7 = getFieldOffset(7); if (f7) result.side = view.getUint8(f7);
  const f8 = getFieldOffset(8); if (f8) result.flags = view.getUint8(f8);
  const f9 = getFieldOffset(9); if (f9) result.seq_num = Number(view.getBigUint64(f9, true));

  return result;
}

function priceToLevelIdx(price) {
  return (price * 1000) | 0;
}

function applyLOBInsert(price, size, side) {
  if (side === SIDE.BID) {
    if (bidPriceToIdx.has(price)) { bidBook[bidPriceToIdx.get(price) * 2 + 1] = size; return; }
    if (bidCount >= LOB_DEPTH) return;
    const idx = bidCount++;
    bidBook[idx * 2] = price; bidBook[idx * 2 + 1] = size;
    bidPriceToIdx.set(price, idx);
    if (price > bestBid) { bestBid = price; bestBidSizeVal = size; }
  } else {
    if (askPriceToIdx.has(price)) { askBook[askPriceToIdx.get(price) * 2 + 1] = size; return; }
    if (askCount >= LOB_DEPTH) return;
    const idx = askCount++;
    askBook[idx * 2] = price; askBook[idx * 2 + 1] = size;
    askPriceToIdx.set(price, idx);
    if (bestAsk === 0 || price < bestAsk) { bestAsk = price; bestAskSizeVal = size; }
  }
}

function applyLOBUpdate(price, size, side) {
  if (size === 0) { applyLOBDelete(price, side); return; }
  if (side === SIDE.BID) {
    const idx = bidPriceToIdx.get(price);
    if (idx !== undefined) bidBook[idx * 2 + 1] = size;
    else applyLOBInsert(price, size, side);
  } else {
    const idx = askPriceToIdx.get(price);
    if (idx !== undefined) askBook[idx * 2 + 1] = size;
    else applyLOBInsert(price, size, side);
  }
}

function applyLOBDelete(price, side) {
  if (side === SIDE.BID) {
    const idx = bidPriceToIdx.get(price);
    if (idx !== undefined) {
      const lastIdx = bidCount - 1;
      if (idx !== lastIdx) {
        bidBook[idx * 2] = bidBook[lastIdx * 2]; bidBook[idx * 2 + 1] = bidBook[lastIdx * 2 + 1];
        bidPriceToIdx.set(bidBook[lastIdx * 2], idx);
      }
      bidPriceToIdx.delete(price); bidCount--;
      if (price === bestBid) { bestBid = 0; for (let i = 0; i < bidCount; i++) if (bidBook[i * 2] > bestBid) bestBid = bidBook[i * 2]; }
    }
  } else {
    const idx = askPriceToIdx.get(price);
    if (idx !== undefined) {
      const lastIdx = askCount - 1;
      if (idx !== lastIdx) {
        askBook[idx * 2] = askBook[lastIdx * 2]; askBook[idx * 2 + 1] = askBook[lastIdx * 2 + 1];
        askPriceToIdx.set(askBook[lastIdx * 2], idx);
      }
      askPriceToIdx.delete(price); askCount--;
      if (price === bestAsk) { bestAsk = 0; for (let i = 0; i < askCount; i++) { const p = askBook[i * 2]; if (bestAsk === 0 || p < bestAsk) bestAsk = p; } }
    }
  }
}

function recordTrade(price, size, side, timestamp_ns) {
  const idx = tradeBufferIdx % TRADE_BUFFER_SIZE;
  tradeBuffer[idx * 4] = price; tradeBuffer[idx * 4 + 1] = size;
  tradeBuffer[idx * 4 + 2] = side; tradeBuffer[idx * 4 + 3] = timestamp_ns;
  tradeBufferIdx++;
}

function processTick(tick) {
  const now = Date.now() * 1e6;
  slot.timestamp_ns = tick.timestamp_ns || now;
  slot.price = tick.price; slot.bid_size = tick.bid_size; slot.ask_size = tick.ask_size;
  slot.trade_size = tick.trade_size; slot.order_id = tick.order_id;
  slot.seq_num = tick.seq_num; slot.action = tick.action; slot.side = tick.side;
  slot.flags = 0; slot.price_level_idx = priceToLevelIdx(tick.price);

  switch (tick.action) {
    case ACTION.INSERT: applyLOBInsert(tick.price, tick.side === SIDE.BID ? tick.bid_size : tick.ask_size, tick.side); break;
    case ACTION.UPDATE: applyLOBUpdate(tick.price, tick.side === SIDE.BID ? tick.bid_size : tick.ask_size, tick.side); break;
    case ACTION.DELETE: applyLOBDelete(tick.price, tick.side); break;
    case ACTION.TRADE:
      slot.flags |= FLAG_IS_TRADE;
      if (tick.side === SIDE.BID) slot.flags |= FLAG_IS_BID;
      recordTrade(tick.price, tick.trade_size, tick.side, slot.timestamp_ns);
      break;
    case ACTION.TOP_OF_BOOK:
      if (tick.side === SIDE.BID) { bestBid = tick.price; bestBidSizeVal = tick.bid_size; }
      else { bestAsk = tick.price; bestAskSizeVal = tick.ask_size; }
      slot.bid_size = bestBidSizeVal;
      slot.ask_size = bestAskSizeVal;
      break;
  }

  ringBuffer.push(slot);
  tickCounter++;
  lastSeqNum = tick.seq_num;
}

function connectWebSocket(url) {
  if (isReconnecting) return;
  ws = new WebSocket(url);
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => { self.postMessage({ type: 'status', status: 'CONNECTED' }); reconnectAttempts = 0; isReconnecting = false; };
  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      const tick = decodeFlatBufferTick(event.data, event.data.byteLength);
      processTick(tick);
    }
  };
  ws.onclose = () => {
    self.postMessage({ type: 'status', status: 'DISCONNECTED' });
    if (reconnectAttempts < maxReconnectAttempts) {
      isReconnecting = true; reconnectAttempts++;
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
      setTimeout(() => { isReconnecting = false; connectWebSocket(url); }, delay);
    }
  };
  ws.onerror = () => { self.postMessage({ type: 'status', status: 'ERROR' }); };
}

function generateMockTick() {
  const basePrice = 4500.25; const spread = 0.25; const now = Date.now() * 1e6;
  const side = Math.random() > 0.5 ? SIDE.BID : SIDE.ASK;
  const actionRoll = Math.random();
  let action;
  if (actionRoll < 0.3) action = ACTION.INSERT;
  else if (actionRoll < 0.55) action = ACTION.UPDATE;
  else if (actionRoll < 0.75) action = ACTION.DELETE;
  else action = ACTION.TRADE;
  const price = basePrice + (Math.random() * 20 - 10) * spread;
  const size = Math.random() * 500 + 1;
  return {
    timestamp_ns: now, price,
    bid_size: side === SIDE.BID ? size : Math.random() * 200,
    ask_size: side === SIDE.ASK ? size : Math.random() * 200,
    trade_size: action === ACTION.TRADE ? size : 0,
    order_id: (Math.random() * 1000000) | 0, action, side, flags: 0, seq_num: lastSeqNum + 1,
  };
}

let mockInterval = null;
function startMockFeed(ticksPerSec = 10000) {
  const batchSize = 100;
  const intervalMs = 1000 / (ticksPerSec / batchSize);
  mockInterval = setInterval(() => { for (let i = 0; i < batchSize; i++) processTick(generateMockTick()); }, intervalMs);
}
function stopMockFeed() { if (mockInterval) { clearInterval(mockInterval); mockInterval = null; } }

self.onmessage = (e) => {
  const { type, data } = e.data;
  switch (type) {
    case 'init': {
      ringBuffer = RingBuffer.create(data.sab);
      RingBuffer.init(data.sab);
      if (data.useMock) startMockFeed(data.mockRate || 10000);
      else connectWebSocket(data.wsUrl || 'ws://localhost:9001');
      break;
    }
    case 'start-mock': startMockFeed(data.rate || 10000); break;
    case 'stop-mock': stopMockFeed(); break;
    case 'connect': stopMockFeed(); connectWebSocket(data.wsUrl || 'ws://localhost:9001'); break;
    case 'disconnect': if (ws) ws.close(); stopMockFeed(); break;
    case 'get-stats': {
      bestBidSizeVal = bestBidSizeFn();
      bestAskSizeVal = bestAskSizeFn();
      self.postMessage({
        type: 'stats', data: {
          ticksPerSecond, bidCount, askCount, bestBid, bestAsk, lastSeqNum,
          bestBidSize: bestBidSizeVal, bestAskSize: bestAskSizeVal,
          ringBufferFill: ringBuffer ? ringBuffer.fillPercent() : 0,
        },
      });
      break;
    }
    case 'request-recovery': {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(new TextEncoder().encode(JSON.stringify({ type: 'RECOVERY_REQUEST', last_seq_num: lastSeqNum })).buffer);
      }
      break;
    }
  }
};

setInterval(() => {
  if (ringBuffer) {
    self.postMessage({
      type: 'stats', data: {
        ticksPerSecond, bidCount, askCount, bestBid, bestAsk, lastSeqNum,
        bestBidSize: bestBidSizeFn(), bestAskSize: bestAskSizeFn(),
        ringBufferFill: ringBuffer ? ringBuffer.fillPercent() : 0,
      },
    });
  }
}, 1000);
