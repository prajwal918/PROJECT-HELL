let wasmInstance = null;
let wasmMemory = null;
let decodeFn = null;
let inputPtr = 0;
let outputPtr = 0;
const WASM_INPUT_SIZE = 1024;
const WASM_OUTPUT_SIZE = 128;
let initialized = false;

const SLOT_POOL_SIZE = 1024;
const slotPool = new Array(SLOT_POOL_SIZE);
let slotPoolIdx = 0;

for (let i = 0; i < SLOT_POOL_SIZE; i++) {
  slotPool[i] = {
    timestamp_ns: 0,
    price: 0,
    bid_size: 0,
    ask_size: 0,
    trade_size: 0,
    order_id: 0,
    action: 0,
    side: 0,
    flags: 0,
    seq_num: 0,
  };
}

function getSlotFromPool() {
  const slot = slotPool[slotPoolIdx % SLOT_POOL_SIZE];
  slotPoolIdx++;
  return slot;
}

export async function initWasmDecoder() {
  if (initialized) return true;

  try {
    const wasmModule = await WebAssembly.compileStreaming(
      fetch(new URL('../wasm/nexus_flow_wasm_bg.wasm', import.meta.url))
    );

    const importObject = {
      env: {
        memory: new WebAssembly.Memory({ initial: 256, maximum: 512 }),
      },
    };

    wasmInstance = await WebAssembly.instantiate(wasmModule, importObject);
    wasmMemory = wasmInstance.exports.memory;
    decodeFn = wasmInstance.exports.decode_tick;
    inputPtr = wasmInstance.exports.INPUT_BUFFER_PTR || 0;
    outputPtr = wasmInstance.exports.OUTPUT_BUFFER_PTR || 65536;
    initialized = true;
    return true;
  } catch (e) {
    console.warn('[NEXUS] Wasm decoder not available, falling back to JS decoder:', e.message);
    return false;
  }
}

export function decodeWasm(uint8Array) {
  if (!initialized || !wasmMemory) return null;

  const src = new Uint8Array(wasmMemory.buffer, inputPtr, uint8Array.byteLength);
  src.set(uint8Array);

  const result = decodeFn(uint8Array.byteLength);

  if (result === 0) return null;

  const slot = getSlotFromPool();
  const outView = new DataView(wasmMemory.buffer, outputPtr, 62);

  slot.timestamp_ns = Number(outView.getBigUint64(0, true));
  slot.price = outView.getFloat64(8, true);
  slot.bid_size = outView.getFloat32(16, true);
  slot.ask_size = outView.getFloat32(20, true);
  slot.trade_size = outView.getFloat32(24, true);
  slot.order_id = outView.getUint32(28, true);
  slot.action = outView.getUint8(32);
  slot.side = outView.getUint8(33);
  slot.flags = outView.getUint8(34);
  slot.seq_num = Number(outView.getBigUint64(35, true));

  return slot;
}

export function isWasmReady() {
  return initialized;
}

export function fallbackDecodeJS(buf, len) {
  if (len < 14) return null;

  const view = new DataView(buf, 0, len);
  const slot = getSlotFromPool();

  let offset = 0;
  const tableOffset = offset;
  offset += 4;
  const vtableOffset = view.getInt32(tableOffset, true);
  const vtableLoc = tableOffset - vtableOffset;
  const vtableSize = view.getInt16(vtableLoc, true);
  const fieldCount = (vtableSize - 4) / 2;

  function getFieldOffset(fieldIdx) {
    if (fieldIdx >= fieldCount) return 0;
    const voff = vtableLoc + 4 + fieldIdx * 2;
    const rel = view.getInt16(voff, true);
    return rel !== 0 ? tableOffset + rel : 0;
  }

  const f0 = getFieldOffset(0);
  if (f0) slot.timestamp_ns = Number(view.getBigUint64(f0, true));
  const f1 = getFieldOffset(1);
  if (f1) slot.price = view.getFloat64(f1, true);
  const f2 = getFieldOffset(2);
  if (f2) slot.bid_size = view.getFloat32(f2, true);
  const f3 = getFieldOffset(3);
  if (f3) slot.ask_size = view.getFloat32(f3, true);
  const f4 = getFieldOffset(4);
  if (f4) slot.trade_size = view.getFloat32(f4, true);
  const f5 = getFieldOffset(5);
  if (f5) slot.order_id = view.getUint32(f5, true);
  const f6 = getFieldOffset(6);
  if (f6) slot.action = view.getUint8(f6);
  const f7 = getFieldOffset(7);
  if (f7) slot.side = view.getUint8(f7);
  const f8 = getFieldOffset(8);
  if (f8) slot.flags = view.getUint8(f8);
  const f9 = getFieldOffset(9);
  if (f9) slot.seq_num = Number(view.getBigUint64(f9, true));

  return slot;
}
