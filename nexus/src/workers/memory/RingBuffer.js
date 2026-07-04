const SAB_SIZE = 512 * 1024 * 1024;
const HEADER_SIZE = 128;
const SLOT_SIZE = 128;
const SLOT_COUNT = Math.floor((SAB_SIZE - HEADER_SIZE) / SLOT_SIZE);
const CACHE_LINE_SIZE = 64;

const CONTROL = {
  WRITE_INDEX: 0,
  READ_INDEX: 4,
  BUFFER_CAPACITY: 8,
  PRODUCER_EPOCH: 12,
  CONSUMER_EPOCH: 16,
  FLAGS: 20,
  TICK_COUNT: 24,
  PAD_START: 32,
};

const SLOT_OFFSETS = {
  TIMESTAMP_NS: 0,
  PRICE: 8,
  BID_SIZE: 16,
  ASK_SIZE: 24,
  TRADE_SIZE: 32,
  ORDER_ID: 40,
  FLAGS: 44,
  PRICE_LEVEL_IDX: 48,
  CANDLE_IDX: 52,
  SEQ_NUM: 56,
  ACTION: 60,
  SIDE: 61,
};

const MASK = SLOT_COUNT - 1;

export class RingBuffer {
  constructor() {
    this.sab = null;
    this.controlView = null;
    this.dataView = null;
    this.float64View = null;
    this.int32View = null;
    this.uint32View = null;
  }

  static create(sab) {
    const rb = new RingBuffer();
    rb.sab = sab;
    rb.controlView = new Int32Array(sab, 0, HEADER_SIZE / 4);
    rb.dataView = new DataView(sab, HEADER_SIZE);
    rb.float64View = new Float64Array(sab, HEADER_SIZE);
    rb.int32View = new Int32Array(sab, HEADER_SIZE);
    rb.uint32View = new Uint32Array(sab, HEADER_SIZE);
    return rb;
  }

  static init(sab) {
    const control = new Int32Array(sab, 0, HEADER_SIZE / 4);
    control[0] = 0;
    control[1] = 0;
    control[2] = SLOT_COUNT;
    control[3] = 0;
    control[4] = 0;
    control[5] = 0;
    control[6] = 0;
  }

  push(slotData) {
    const writeIdx = Atomics.load(this.controlView, CONTROL.WRITE_INDEX / 4);
    const readIdx = Atomics.load(this.controlView, CONTROL.READ_INDEX / 4);
    const nextWrite = (writeIdx + 1) & MASK;
    if (nextWrite === readIdx) {
      const forcedRead = (readIdx + 1) & MASK;
      Atomics.store(this.controlView, CONTROL.READ_INDEX / 4, forcedRead);
    }
    const slotByteOffset = writeIdx * SLOT_SIZE;
    const slotFloatIdx = slotByteOffset / 8;
    const slotUint32Idx = slotByteOffset / 4;
    this.float64View[slotFloatIdx + 0] = slotData.timestamp_ns;
    this.float64View[slotFloatIdx + 1] = slotData.price;
    this.float64View[slotFloatIdx + 2] = slotData.bid_size;
    this.float64View[slotFloatIdx + 3] = slotData.ask_size;
    this.float64View[slotFloatIdx + 4] = slotData.trade_size;
    this.uint32View[slotUint32Idx + 10] = slotData.order_id;
    this.uint32View[slotUint32Idx + 11] = slotData.flags;
    this.uint32View[slotUint32Idx + 12] = slotData.price_level_idx;
    this.uint32View[slotUint32Idx + 13] = slotData.candle_idx;
    this.uint32View[slotUint32Idx + 14] = slotData.seq_num;
    const actionSideByteOffset = slotByteOffset + SLOT_OFFSETS.ACTION;
    this.dataView.setUint8(actionSideByteOffset, slotData.action);
    this.dataView.setUint8(actionSideByteOffset + 1, slotData.side);
    Atomics.store(this.controlView, CONTROL.WRITE_INDEX / 4, nextWrite);
    Atomics.add(this.controlView, CONTROL.TICK_COUNT / 4, 1);
    return writeIdx;
  }

  pop(outSlot) {
    const readIdx = Atomics.load(this.controlView, CONTROL.READ_INDEX / 4);
    const writeIdx = Atomics.load(this.controlView, CONTROL.WRITE_INDEX / 4);
    if (readIdx === writeIdx) return false;
    const slotByteOffset = readIdx * SLOT_SIZE;
    const slotFloatIdx = slotByteOffset / 8;
    const slotUint32Idx = slotByteOffset / 4;
    outSlot.timestamp_ns = this.float64View[slotFloatIdx + 0];
    outSlot.price = this.float64View[slotFloatIdx + 1];
    outSlot.bid_size = this.float64View[slotFloatIdx + 2];
    outSlot.ask_size = this.float64View[slotFloatIdx + 3];
    outSlot.trade_size = this.float64View[slotFloatIdx + 4];
    outSlot.order_id = this.uint32View[slotUint32Idx + 10];
    outSlot.flags = this.uint32View[slotUint32Idx + 11];
    outSlot.price_level_idx = this.uint32View[slotUint32Idx + 12];
    outSlot.candle_idx = this.uint32View[slotUint32Idx + 13];
    outSlot.seq_num = this.uint32View[slotUint32Idx + 14];
    const actionSideByteOffset = slotByteOffset + SLOT_OFFSETS.ACTION;
    outSlot.action = this.dataView.getUint8(actionSideByteOffset);
    outSlot.side = this.dataView.getUint8(actionSideByteOffset + 1);
    const nextRead = (readIdx + 1) & MASK;
    Atomics.store(this.controlView, CONTROL.READ_INDEX / 4, nextRead);
    return true;
  }

  available() {
    const writeIdx = Atomics.load(this.controlView, CONTROL.WRITE_INDEX / 4);
    const readIdx = Atomics.load(this.controlView, CONTROL.READ_INDEX / 4);
    return (writeIdx - readIdx + SLOT_COUNT) & MASK;
  }

  isFull() {
    const writeIdx = Atomics.load(this.controlView, CONTROL.WRITE_INDEX / 4);
    const readIdx = Atomics.load(this.controlView, CONTROL.READ_INDEX / 4);
    return ((writeIdx + 1) & MASK) === readIdx;
  }

  isEmpty() {
    const writeIdx = Atomics.load(this.controlView, CONTROL.WRITE_INDEX / 4);
    const readIdx = Atomics.load(this.controlView, CONTROL.READ_INDEX / 4);
    return writeIdx === readIdx;
  }

  writeIndex() {
    return Atomics.load(this.controlView, CONTROL.WRITE_INDEX / 4);
  }

  readIndex() {
    return Atomics.load(this.controlView, CONTROL.READ_INDEX / 4);
  }

  tickCount() {
    return Atomics.load(this.controlView, CONTROL.TICK_COUNT / 4);
  }

  readSlotAt(index, outSlot) {
    const slotByteOffset = index * SLOT_SIZE;
    const slotFloatIdx = slotByteOffset / 8;
    const slotUint32Idx = slotByteOffset / 4;
    outSlot.timestamp_ns = this.float64View[slotFloatIdx + 0];
    outSlot.price = this.float64View[slotFloatIdx + 1];
    outSlot.bid_size = this.float64View[slotFloatIdx + 2];
    outSlot.ask_size = this.float64View[slotFloatIdx + 3];
    outSlot.trade_size = this.float64View[slotFloatIdx + 4];
    outSlot.order_id = this.uint32View[slotUint32Idx + 10];
    outSlot.flags = this.uint32View[slotUint32Idx + 11];
    outSlot.price_level_idx = this.uint32View[slotUint32Idx + 12];
    outSlot.candle_idx = this.uint32View[slotUint32Idx + 13];
    outSlot.seq_num = this.uint32View[slotUint32Idx + 14];
    const actionSideByteOffset = slotByteOffset + SLOT_OFFSETS.ACTION;
    outSlot.action = this.dataView.getUint8(actionSideByteOffset);
    outSlot.side = this.dataView.getUint8(actionSideByteOffset + 1);
  }

  fillPercent() {
    return (this.available() / SLOT_COUNT) * 100;
  }
}

export function createSlot() {
  return {
    timestamp_ns: 0,
    price: 0,
    bid_size: 0,
    ask_size: 0,
    trade_size: 0,
    order_id: 0,
    flags: 0,
    price_level_idx: 0,
    candle_idx: 0,
    seq_num: 0,
    action: 0,
    side: 0,
  };
}
