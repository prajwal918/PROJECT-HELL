import { RingBuffer, createSlot } from './memory/RingBuffer.js';

const SAB_SIZE = 512 * 1024 * 1024;
const HEADER_SIZE = 128;
const SLOT_SIZE = 128;
const SLOT_COUNT = Math.floor((SAB_SIZE - HEADER_SIZE) / SLOT_SIZE);
const CONTROL_WRITE_INDEX = 0;

const ACTION = { INSERT: 0, UPDATE: 1, DELETE: 2, TRADE: 3, TOP_OF_BOOK: 4 };
const SIDE = { BID: 0, ASK: 1 };
const FLAG_IS_BID = 1 << 0;
const FLAG_IS_TRADE = 1 << 1;
const FLAG_IS_ICEBERG = 1 << 2;
const FLAG_IS_ABSORPTION = 1 << 3;

const MAX_CANDLES = 8192;
const MAX_PRICE_LEVELS = 4096;
const MAX_TPO_SLOTS = 96;
const ICEBERG_POOL_SIZE = 65536;
const BBO_HISTORY_DEPTH = 216000;
const CANDLE_PRICE_LEVELS = 64;

const FEATURE = {
  HEADER_SIZE: 256,
  CVD_OFFSET: 256 + 8 * 8192,
  DELTA_OFFSET: 256 + 8 * 8192 * 2,
  IMBALANCE_MAP_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096,
  STACKED_IMBALANCE_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096,
  VPOC_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192,
  VOLUME_PROFILE_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096,
  TPO_MAP_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96,
  ICEBERG_MAP_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536,
  ABSORPTION_FLAGS_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096,
  BBO_BID_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000,
  BBO_ASK_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4092 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2,
  MAX_DELTA_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2,
  MIN_DELTA_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192,
  TOTAL_VOLUME_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 2,
  DIVERGENCE_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3,
  CANDLE_BID_VOL_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192,
  CANDLE_ASK_VOL_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64,
  LOB_BID_DEPTH_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2,
  LOB_ASK_DEPTH_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096,
  OHLC_OPEN_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2,
  OHLC_HIGH_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192,
  OHLC_LOW_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 2,
  OHLC_CLOSE_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 3,
  SESSION_VWAP_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4,
  BUY_VWAP_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16,
  SELL_VWAP_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 2,
  IBR_HIGH_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 3,
  IBR_LOW_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 3 + 8,
  SINGLE_PRINTS_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 3 + 8 * 2,
  BUYING_TAIL_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 3 + 8 * 2 + 1 * 4096,
  SELLING_TAIL_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 3 + 8 * 2 + 1 * 4096 + 8,
  NAKED_POC_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 3 + 8 * 2 + 1 * 4096 + 8 * 2,
  EXHAUSTION_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 3 + 8 * 2 + 1 * 4096 + 8 * 3,
  SWEEP_FLAGS_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 3 + 8 * 2 + 1 * 4096 + 8 * 3 + 1 * 8192,
  OFT_RATIO_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 3 + 8 * 2 + 1 * 4096 + 8 * 3 + 1 * 8192 * 2,
  OFT_SLINGSHOT_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 3 + 8 * 2 + 1 * 4096 + 8 * 3 + 1 * 8192 * 2 + 1 * 8192 * 64,
  OFT_WEAKNESS_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 3 + 8 * 2 + 1 * 4096 + 8 * 3 + 1 * 8192 * 2 + 1 * 8192 * 64 + 1 * 4096,
  OFT_SEQUENCING_OFFSET: 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3 + 1 * 8192 + 4 * 8192 * 64 * 2 + 8 * 4096 * 2 + 8 * 8192 * 4 + 16 * 3 + 8 * 2 + 1 * 4096 + 8 * 3 + 1 * 8192 * 2 + 1 * 8192 * 64 + 1 * 4096 * 2,
  CURRENT_CANDLE_IDX: 0,
  CURRENT_SLOT: 4,
  ALGO_WRITE_EPOCH: 8,
  CANDLE_COUNT: 12,
  TPO_SLOT_IDX: 16,
  SESSION_START_NS: 24,
  BID_COUNT: 28,
  ASK_COUNT: 32,
};

const IMBALANCE_THRESHOLD = 3.0;
const ABSORPTION_VOL_MULT = 3.0;
const ABSORPTION_BOOK_CHANGE_RATIO = 0.10;
const TPO_SLOT_DURATION_MS = 30000;

let tickSAB = null;
let featureSAB = null;
let ringBuffer = null;
let algoReadIdx = 0;

let cvd, delta, imbalanceMap, stackedImbalance, vpoc, volumeProfile, tpoMap, icebergMap;
let absorptionFlags, bboBid, bboAsk, maxDelta, minDelta, totalVolume, divergenceFlags, featureHeader;
let candleBidVolGrid, candleAskVolGrid;
let lobBidDepth, lobAskDepth;
let ohlcOpen, ohlcHigh, ohlcLow, ohlcClose;
let sessionVWAPData, buyVWAPData, sellVWAPData;
let ibrHigh, ibrLow, singlePrintsArr, buyingTailPrice, sellingTailPrice, nakedPOCPrice;
let exhaustionFlags, sweepFlags;
let oftRatioMap, oftSlingshotFlags, oftWeaknessFlags, oftSequencingFlags;

let currentCandleIdx = 0;
let candleIntervalMs = 60000;
let candleStartNs = 0;
let currentTPOSlot = 0;
let sessionStartNs = 0;

let barDeltaAccum = 0;
let barVolumeAccum = 0;
let barMaxDelta = 0;
let barMinDelta = 0;

let barOpen = 0;
let barHigh = 0;
let barLow = 0;
let barClose = 0;
let candleFirstTrade = true;

let sessionVWAPNotional = 0;
let sessionVWAPVolume = 0;
let buyVWAPNotional = 0;
let buyVWAPVolume = 0;
let sellVWAPNotional = 0;
let sellVWAPVolume = 0;

const IBR_PERIOD_COUNT = 2;
let ibrHighPrice = 0;
let ibrLowPrice = 0;
let ibrComputed = false;
let ibrSlotHigh = -Infinity;
let ibrSlotLow = Infinity;
let ibrSlotCount = 0;
let prevSessionPOC = 0;
let nakedPOCRetested = false;

const recentTradePrices = new Float64Array(5);
let recentTradeSide = new Uint8Array(5);
let recentTradeIdx = 0;
let recentTradeFill = 0;

let candleBidVol = new Float64Array(MAX_PRICE_LEVELS);
let candleAskVol = new Float64Array(MAX_PRICE_LEVELS);
let candleTotalVol = new Float64Array(MAX_PRICE_LEVELS);

let candleLocalBidVol = new Float32Array(CANDLE_PRICE_LEVELS);
let candleLocalAskVol = new Float32Array(CANDLE_PRICE_LEVELS);
let candleBasePrice = 0;

const icebergPool = new Float64Array(ICEBERG_POOL_SIZE * 4);
let icebergPoolCount = 0;
const icebergLookup = new Map();

const rollingTradeSizes = new Float64Array(1000);
let rollingTradeIdx = 0;
let rollingTradeCount = 0;
let rollingMeanTradeSize = 0;

const absorptionWindow = new Float64Array(MAX_PRICE_LEVELS * 3);
let bboSlotIdx = 0;
let previousCVD = 0;

function initFeatureArrays() {
  featureHeader = new Int32Array(featureSAB, 0, FEATURE.HEADER_SIZE / 4);
  cvd = new Float64Array(featureSAB, FEATURE.CVD_OFFSET, MAX_CANDLES);
  delta = new Float64Array(featureSAB, FEATURE.DELTA_OFFSET, MAX_CANDLES);
  imbalanceMap = new Float32Array(featureSAB, FEATURE.IMBALANCE_MAP_OFFSET, MAX_PRICE_LEVELS);
  stackedImbalance = new Uint8Array(featureSAB, FEATURE.STACKED_IMBALANCE_OFFSET, MAX_PRICE_LEVELS);
  vpoc = new Float64Array(featureSAB, FEATURE.VPOC_OFFSET, MAX_CANDLES);
  volumeProfile = new Float64Array(featureSAB, FEATURE.VOLUME_PROFILE_OFFSET, MAX_PRICE_LEVELS);
  tpoMap = new Uint32Array(featureSAB, FEATURE.TPO_MAP_OFFSET, MAX_PRICE_LEVELS * MAX_TPO_SLOTS);
  icebergMap = new Float32Array(featureSAB, FEATURE.ICEBERG_MAP_OFFSET, ICEBERG_POOL_SIZE);
  absorptionFlags = new Uint8Array(featureSAB, FEATURE.ABSORPTION_FLAGS_OFFSET, MAX_PRICE_LEVELS);
  bboBid = new Float64Array(featureSAB, FEATURE.BBO_BID_OFFSET, BBO_HISTORY_DEPTH);
  bboAsk = new Float64Array(featureSAB, FEATURE.BBO_ASK_OFFSET, BBO_HISTORY_DEPTH);
  maxDelta = new Float64Array(featureSAB, FEATURE.MAX_DELTA_OFFSET, MAX_CANDLES);
  minDelta = new Float64Array(featureSAB, FEATURE.MIN_DELTA_OFFSET, MAX_CANDLES);
  totalVolume = new Float64Array(featureSAB, FEATURE.TOTAL_VOLUME_OFFSET, MAX_CANDLES);
  divergenceFlags = new Uint8Array(featureSAB, FEATURE.DIVERGENCE_OFFSET, MAX_CANDLES);
  candleBidVolGrid = new Float32Array(featureSAB, FEATURE.CANDLE_BID_VOL_OFFSET, MAX_CANDLES * CANDLE_PRICE_LEVELS);
  candleAskVolGrid = new Float32Array(featureSAB, FEATURE.CANDLE_ASK_VOL_OFFSET, MAX_CANDLES * CANDLE_PRICE_LEVELS);
  lobBidDepth = new Float64Array(featureSAB, FEATURE.LOB_BID_DEPTH_OFFSET, MAX_PRICE_LEVELS);
  lobAskDepth = new Float64Array(featureSAB, FEATURE.LOB_ASK_DEPTH_OFFSET, MAX_PRICE_LEVELS);
  ohlcOpen = new Float64Array(featureSAB, FEATURE.OHLC_OPEN_OFFSET, MAX_CANDLES);
  ohlcHigh = new Float64Array(featureSAB, FEATURE.OHLC_HIGH_OFFSET, MAX_CANDLES);
  ohlcLow = new Float64Array(featureSAB, FEATURE.OHLC_LOW_OFFSET, MAX_CANDLES);
  ohlcClose = new Float64Array(featureSAB, FEATURE.OHLC_CLOSE_OFFSET, MAX_CANDLES);
  sessionVWAPData = new Float64Array(featureSAB, FEATURE.SESSION_VWAP_OFFSET, 2);
  buyVWAPData = new Float64Array(featureSAB, FEATURE.BUY_VWAP_OFFSET, 2);
  sellVWAPData = new Float64Array(featureSAB, FEATURE.SELL_VWAP_OFFSET, 2);
  ibrHigh = new Float64Array(featureSAB, FEATURE.IBR_HIGH_OFFSET, 1);
  ibrLow = new Float64Array(featureSAB, FEATURE.IBR_LOW_OFFSET, 1);
  singlePrintsArr = new Uint8Array(featureSAB, FEATURE.SINGLE_PRINTS_OFFSET, MAX_PRICE_LEVELS);
  buyingTailPrice = new Float64Array(featureSAB, FEATURE.BUYING_TAIL_OFFSET, 1);
  sellingTailPrice = new Float64Array(featureSAB, FEATURE.SELLING_TAIL_OFFSET, 1);
  nakedPOCPrice = new Float64Array(featureSAB, FEATURE.NAKED_POC_OFFSET, 1);
  exhaustionFlags = new Uint8Array(featureSAB, FEATURE.EXHAUSTION_OFFSET, MAX_CANDLES);
  sweepFlags = new Uint8Array(featureSAB, FEATURE.SWEEP_FLAGS_OFFSET, MAX_CANDLES);
  oftRatioMap = new Uint8Array(featureSAB, FEATURE.OFT_RATIO_OFFSET, MAX_CANDLES * CANDLE_PRICE_LEVELS);
  oftSlingshotFlags = new Uint8Array(featureSAB, FEATURE.OFT_SLINGSHOT_OFFSET, MAX_CANDLES);
  oftWeaknessFlags = new Uint8Array(featureSAB, FEATURE.OFT_WEAKNESS_OFFSET, MAX_CANDLES);
  oftSequencingFlags = new Uint8Array(featureSAB, FEATURE.OFT_SEQUENCING_OFFSET, MAX_CANDLES);
}

function priceToLevelIdx(price) { const idx = (price * 1000) | 0; return idx >= 0 && idx < MAX_PRICE_LEVELS ? idx : 0; }
function tickSizeFromPrice(price) { if (price > 1000) return 0.25; if (price > 100) return 0.01; return 0.0001; }

function priceToLocalIdx(price) {
  if (candleBasePrice === 0) return -1;
  const ts = tickSizeFromPrice(price);
  const idx = Math.round((price - candleBasePrice) / ts) + Math.floor(CANDLE_PRICE_LEVELS / 2);
  return idx >= 0 && idx < CANDLE_PRICE_LEVELS ? idx : -1;
}

function computeCVD(tradeSize, side) {
  const d = side === SIDE.ASK ? tradeSize : -tradeSize;
  barDeltaAccum += d;
  barVolumeAccum += tradeSize;
  if (barDeltaAccum > barMaxDelta) barMaxDelta = barDeltaAccum;
  if (barDeltaAccum < barMinDelta) barMinDelta = barDeltaAccum;
}

function commitCandle() {
  const idx = currentCandleIdx % MAX_CANDLES;
  delta[idx] = barDeltaAccum;
  cvd[idx] = previousCVD + barDeltaAccum;
  previousCVD = cvd[idx];
  maxDelta[idx] = barMaxDelta;
  minDelta[idx] = barMinDelta;
  totalVolume[idx] = barVolumeAccum;

  ohlcOpen[idx] = barOpen;
  ohlcHigh[idx] = barHigh;
  ohlcLow[idx] = barLow;
  ohlcClose[idx] = barClose;

  if (sessionVWAPVolume > 0) sessionVWAPData[0] = sessionVWAPNotional / sessionVWAPVolume;
  sessionVWAPData[1] = sessionVWAPVolume;
  if (buyVWAPVolume > 0) buyVWAPData[0] = buyVWAPNotional / buyVWAPVolume;
  buyVWAPData[1] = buyVWAPVolume;
  if (sellVWAPVolume > 0) sellVWAPData[0] = sellVWAPNotional / sellVWAPVolume;
  sellVWAPData[1] = sellVWAPVolume;

  ibrHigh[0] = ibrHighPrice;
  ibrLow[0] = ibrLowPrice;

  detectTPOStructuralFeatures();
  detectExhaustion(idx);
  detectOFTRatio(idx);
  detectPOCSlingshot(currentCandleIdx);
  detectMarketWeakness(currentCandleIdx);

  let maxVolPrice = 0, maxVol = 0;
  for (let p = 0; p < MAX_PRICE_LEVELS; p++) {
    if (candleTotalVol[p] > maxVol) { maxVol = candleTotalVol[p]; maxVolPrice = p; }
  }
  vpoc[idx] = maxVolPrice / 1000;

  const gridOff = idx * CANDLE_PRICE_LEVELS;
  for (let p = 0; p < CANDLE_PRICE_LEVELS; p++) {
    candleBidVolGrid[gridOff + p] = candleLocalBidVol[p];
    candleAskVolGrid[gridOff + p] = candleLocalAskVol[p];
  }

  barDeltaAccum = 0;
  barMaxDelta = 0;
  barMinDelta = 0;
  barVolumeAccum = 0;
  barOpen = 0;
  barHigh = 0;
  barLow = 0;
  barClose = 0;
  candleFirstTrade = true;
  ibrSlotHigh = -Infinity;
  ibrSlotLow = Infinity;
  ibrSlotCount++;
  candleBidVol.fill(0);
  candleAskVol.fill(0);
  candleTotalVol.fill(0);
  candleLocalBidVol.fill(0);
  candleLocalAskVol.fill(0);
  candleBasePrice = 0;
  currentCandleIdx++;
  featureHeader[FEATURE.CANDLE_COUNT / 4] = currentCandleIdx;
}

function computeImbalance(price, tradeSize, side) {
  const pIdx = priceToLevelIdx(price);
  if (pIdx <= 0 || pIdx >= MAX_PRICE_LEVELS) return;
  if (side === SIDE.ASK) candleAskVol[pIdx] += tradeSize;
  else candleBidVol[pIdx] += tradeSize;
  candleTotalVol[pIdx] += tradeSize;

  const localIdx = priceToLocalIdx(price);
  if (localIdx >= 0) {
    if (side === SIDE.ASK) candleLocalAskVol[localIdx] += tradeSize;
    else candleLocalBidVol[localIdx] += tradeSize;
  }

  const ts = tickSizeFromPrice(price);
  const pMinusOneIdx = priceToLevelIdx(price - ts);
  const askVol = candleAskVol[pIdx];
  const bidVolBelow = candleBidVol[pMinusOneIdx];
  if (askVol > 0 && bidVolBelow > 0 && askVol / bidVolBelow >= IMBALANCE_THRESHOLD) imbalanceMap[pIdx] = askVol / bidVolBelow;
  const bidVol = candleBidVol[pIdx];
  const askVolAbove = candleAskVol[pMinusOneIdx];
  if (bidVol > 0 && askVolAbove > 0 && bidVol / askVolAbove >= IMBALANCE_THRESHOLD) imbalanceMap[pIdx] = -(bidVol / askVolAbove);
}

function detectStackedImbalance() {
  let consecutive = 0;
  for (let p = 0; p < MAX_PRICE_LEVELS; p++) {
    if (imbalanceMap[p] !== 0) {
      consecutive++;
      if (consecutive >= 3) {
        stackedImbalance[p] = 1;
        if (p >= 1) stackedImbalance[p - 1] = 1;
        if (p >= 2) stackedImbalance[p - 2] = 1;
      }
    } else {
      consecutive = 0;
    }
  }
}

function updateVolumeProfile(price, tradeSize) { const pIdx = priceToLevelIdx(price); if (pIdx < MAX_PRICE_LEVELS) volumeProfile[pIdx] += tradeSize; }

function updateTPO(timestamp_ns, price) {
  if (sessionStartNs === 0) sessionStartNs = timestamp_ns;
  const slotIdx = Math.floor((timestamp_ns - sessionStartNs) / (TPO_SLOT_DURATION_MS * 1e6));
  if (slotIdx >= 0 && slotIdx < MAX_TPO_SLOTS) {
    const pIdx = priceToLevelIdx(price);
    if (pIdx < MAX_PRICE_LEVELS) tpoMap[pIdx * MAX_TPO_SLOTS + slotIdx]++;
    currentTPOSlot = slotIdx;
  }
}

function detectIceberg(orderId, newSize, oldSize, price) {
  if (orderId === 0) return;
  const sizeIncrease = newSize - oldSize;
  if (sizeIncrease > 0 && oldSize > 0) {
    if (icebergLookup.has(orderId)) {
      const poolIdx = icebergLookup.get(orderId);
      icebergPool[poolIdx * 4 + 2] += sizeIncrease;
      icebergPool[poolIdx * 4 + 3] += 1;
      const hitCount = icebergPool[poolIdx * 4 + 3];
      const survivalProb = hitCount / (hitCount + 1);
      if (orderId < ICEBERG_POOL_SIZE) icebergMap[orderId] = icebergPool[poolIdx * 4 + 2] * survivalProb;
    } else if (icebergPoolCount < ICEBERG_POOL_SIZE) {
      const poolIdx = icebergPoolCount;
      icebergPool[poolIdx * 4 + 0] = orderId;
      icebergPool[poolIdx * 4 + 1] = newSize;
      icebergPool[poolIdx * 4 + 2] = sizeIncrease;
      icebergPool[poolIdx * 4 + 3] = 1;
      icebergLookup.set(orderId, poolIdx);
      icebergPoolCount++;
      if (orderId < ICEBERG_POOL_SIZE) icebergMap[orderId] = sizeIncrease * 0.5;
    }
  }
}

function updateRollingMeanTradeSize(tradeSize) {
  rollingTradeSizes[rollingTradeIdx % 1000] = tradeSize;
  rollingTradeIdx++;
  rollingTradeCount = Math.min(rollingTradeCount + 1, 1000);
  let sum = 0;
  for (let i = 0; i < rollingTradeCount; i++) sum += rollingTradeSizes[i];
  rollingMeanTradeSize = sum / rollingTradeCount;
}

function detectAbsorption(price, tradeSize, bookDepth) {
  const pIdx = priceToLevelIdx(price);
  if (pIdx >= MAX_PRICE_LEVELS) return;
  const w = pIdx * 3;
  if (absorptionWindow[w] === 0 && bookDepth > 0) {
    absorptionWindow[w] = bookDepth;
  }
  absorptionWindow[w + 1] += tradeSize;
  absorptionWindow[w + 2] += 1;
  const threshold = ABSORPTION_VOL_MULT * rollingMeanTradeSize;
  if (absorptionWindow[w + 1] > threshold && absorptionWindow[w] > 0) {
    const depthOld = absorptionWindow[w];
    const depthChange = Math.abs(bookDepth - depthOld);
    if (depthChange < ABSORPTION_BOOK_CHANGE_RATIO * depthOld) {
      absorptionFlags[pIdx] = 1;
    }
  }
}

function updateBBO(bidPrice, askPrice) {
  const slot = bboSlotIdx % BBO_HISTORY_DEPTH;
  bboBid[slot] = bidPrice;
  bboAsk[slot] = askPrice;
  bboSlotIdx++;
}

function updateLOBDepth(bidPrice, bidSize, askPrice, askSize) {
  const bidIdx = priceToLevelIdx(bidPrice);
  const askIdx = priceToLevelIdx(askPrice);
  if (bidIdx < MAX_PRICE_LEVELS) lobBidDepth[bidIdx] = bidSize;
  if (askIdx < MAX_PRICE_LEVELS) lobAskDepth[askIdx] = askSize;
}

function detectCVDDivergence(lookback = 10) {
  if (currentCandleIdx < lookback + 1) return;
  const half = Math.floor(lookback / 2);
  let maxP1 = -Infinity, minP1 = Infinity, maxC1 = -Infinity, minC1 = Infinity;
  let maxP2 = -Infinity, minP2 = Infinity, maxC2 = -Infinity, minC2 = Infinity;
  for (let i = 0; i < half; i++) {
    const idx = (currentCandleIdx - lookback + i) % MAX_CANDLES;
    if (totalVolume[idx] > 0) {
      const v = vpoc[idx];
      if (v > maxP1) maxP1 = v; if (v < minP1) minP1 = v;
      if (cvd[idx] > maxC1) maxC1 = cvd[idx]; if (cvd[idx] < minC1) minC1 = cvd[idx];
    }
  }
  for (let i = half; i < lookback; i++) {
    const idx = (currentCandleIdx - lookback + i) % MAX_CANDLES;
    if (totalVolume[idx] > 0) {
      const v = vpoc[idx];
      if (v > maxP2) maxP2 = v; if (v < minP2) minP2 = v;
      if (cvd[idx] > maxC2) maxC2 = cvd[idx]; if (cvd[idx] < minC2) minC2 = cvd[idx];
    }
  }
  const end = currentCandleIdx % MAX_CANDLES;
  if (maxP2 > maxP1 && maxC2 < maxC1) divergenceFlags[end] = 1;
  if (minP2 < minP1 && minC2 > minC1) divergenceFlags[end] = 2;
}

function detectTPOStructuralFeatures() {
  singlePrintsArr.fill(0);
  const currentTPOSlotVal = currentTPOSlot;
  for (let p = 0; p < MAX_PRICE_LEVELS; p++) {
    let count = 0;
    for (let s = 0; s <= currentTPOSlotVal && s < MAX_TPO_SLOTS; s++) {
      if (tpoMap[p * MAX_TPO_SLOTS + s] > 0) count++;
    }
    if (count === 1) singlePrintsArr[p] = 1;
  }

  let bottomConsecutive = 0;
  let bottomSinglePrice = 0;
  let topConsecutive = 0;
  let topSinglePrice = 0;
  for (let p = 0; p < MAX_PRICE_LEVELS; p++) {
    if (singlePrintsArr[p]) {
      bottomConsecutive++;
      bottomSinglePrice = p / 1000;
    } else {
      break;
    }
  }
  if (bottomConsecutive >= 3) buyingTailPrice[0] = bottomSinglePrice;

  for (let p = MAX_PRICE_LEVELS - 1; p >= 0; p--) {
    if (singlePrintsArr[p]) {
      topConsecutive++;
      topSinglePrice = p / 1000;
    } else {
      break;
    }
  }
  if (topConsecutive >= 3) sellingTailPrice[0] = topSinglePrice;

  if (prevSessionPOC > 0 && !nakedPOCRetested) {
    const pocIdx = priceToLevelIdx(prevSessionPOC);
    for (let s = 0; s <= currentTPOSlotVal && s < MAX_TPO_SLOTS; s++) {
      if (tpoMap[pocIdx * MAX_TPO_SLOTS + s] > 0) {
        nakedPOCRetested = true;
        nakedPOCPrice[0] = 0;
        break;
      }
    }
    if (!nakedPOCRetested) nakedPOCPrice[0] = prevSessionPOC;
  }
}

function detectExhaustion(candleIdx) {
  const gridOff = candleIdx * CANDLE_PRICE_LEVELS;
  const top3 = [0, 0, 0];
  const bottom3 = [0, 0, 0];
  let topCount = 0;
  let bottomCount = 0;
  for (let p = CANDLE_PRICE_LEVELS - 1; p >= 0 && topCount < 3; p--) {
    const vol = candleLocalBidVol[p] + candleLocalAskVol[p];
    if (vol > 0) { top3[topCount++] = vol; }
  }
  for (let p = 0; p < CANDLE_PRICE_LEVELS && bottomCount < 3; p++) {
    const vol = candleLocalBidVol[p] + candleLocalAskVol[p];
    if (vol > 0) { bottom3[bottomCount++] = vol; }
  }
  if (topCount === 3 && top3[0] <= top3[1] && top3[1] <= top3[2] && top3[0] === 0) {
    exhaustionFlags[candleIdx] = 2;
  }
  if (bottomCount === 3 && bottom3[0] <= bottom3[1] && bottom3[1] <= bottom3[2] && bottom3[0] === 0) {
    exhaustionFlags[candleIdx] = 1;
  }
}

function detectSweep(candleIdx) {
  const prices = recentTradePrices;
  const sides = recentTradeSide;
  let minP = Infinity, maxP = -Infinity;
  let allSameDir = true;
  const firstSide = sides[0];
  for (let i = 0; i < recentTradeFill; i++) {
    const p = prices[i];
    if (p < minP) minP = p;
    if (p > maxP) maxP = p;
    if (sides[i] !== firstSide) allSameDir = false;
  }
  const range = maxP - minP;
  const ts = tickSizeFromPrice(maxP);
  if (allSameDir && range >= 3 * ts) {
    sweepFlags[candleIdx] = firstSide === SIDE.ASK ? 1 : 2;
  }
}

function detectOFTRatio(candleIdx) {
  const gridOff = candleIdx * CANDLE_PRICE_LEVELS;
  for (let p = 0; p < CANDLE_PRICE_LEVELS; p++) {
    const bidVol = candleLocalBidVol[p];
    const askVol = candleLocalAskVol[p];
    if (bidVol === 0 && askVol === 0) {
      oftRatioMap[gridOff + p] = 0;
      continue;
    }
    if (askVol > 0 && bidVol > 0) {
      const ratio = askVol / bidVol;
      if (ratio >= 30) oftRatioMap[gridOff + p] = 1;
      else if (ratio <= 0.0333) oftRatioMap[gridOff + p] = 2;
      else oftRatioMap[gridOff + p] = 0;
    } else if (askVol > 0 && bidVol === 0) {
      oftRatioMap[gridOff + p] = 1;
    } else if (bidVol > 0 && askVol === 0) {
      oftRatioMap[gridOff + p] = 2;
    } else {
      oftRatioMap[gridOff + p] = 0;
    }
  }
}

function detectPOCSlingshot(candleIdx) {
  if (candleIdx < 3) return;
  const curVpoc = vpoc[candleIdx % MAX_CANDLES];
  if (curVpoc === 0) return;
  const hi = ohlcHigh[candleIdx % MAX_CANDLES];
  const lo = ohlcLow[candleIdx % MAX_CANDLES];
  if (hi === 0 || lo === 0) return;
  const mid = (hi + lo) / 2;
  const curBelowMid = curVpoc < mid;
  let prevBelowCount = 0;
  let prevAboveCount = 0;
  for (let i = 1; i <= 2; i++) {
    const prevIdx = (candleIdx - i) % MAX_CANDLES;
    const prevPoc = vpoc[prevIdx];
    const prevHi = ohlcHigh[prevIdx];
    const prevLo = ohlcLow[prevIdx];
    if (prevHi === 0 || prevLo === 0 || prevPoc === 0) return;
    const prevMid = (prevHi + prevLo) / 2;
    if (prevPoc < prevMid) prevBelowCount++;
    else prevAboveCount++;
  }
  if (prevBelowCount >= 2 && !curBelowMid) {
    oftSlingshotFlags[candleIdx % MAX_CANDLES] = 1;
  } else if (prevAboveCount >= 2 && curBelowMid) {
    oftSlingshotFlags[candleIdx % MAX_CANDLES] = 2;
  }
}

function detectMarketWeakness(candleIdx) {
  if (candleIdx < 2) return;
  const curIdx = candleIdx % MAX_CANDLES;
  const prevIdx = (candleIdx - 1) % MAX_CANDLES;
  const curDelta = delta[curIdx];
  const prevDelta = delta[prevIdx];
  const curTotal = totalVolume[curIdx];
  const prevTotal = totalVolume[prevIdx];
  if (curTotal === 0 || prevTotal === 0) return;
  const curAggBuy = curDelta > 0 ? curDelta : 0;
  const curAggSell = curDelta < 0 ? -curDelta : 0;
  const prevAggBuy = prevDelta > 0 ? prevDelta : 0;
  const prevAggSell = prevDelta < 0 ? -prevDelta : 0;
  const curHi = ohlcHigh[curIdx];
  const curLo = ohlcLow[curIdx];
  const prevHi = ohlcHigh[prevIdx];
  const prevLo = ohlcLow[prevIdx];
  if (prevAggBuy > 0 && curAggBuy / prevAggBuy < 0.6 && curHi > prevHi) {
    oftWeaknessFlags[curIdx] = 1;
  }
  if (prevAggSell > 0 && curAggSell / prevAggSell < 0.6 && curLo < prevLo) {
    oftWeaknessFlags[curIdx] = 2;
  }
}

let sequencingTradeDir = 0;
let sequencingConsecutive = 0;

function detectSequencing(tradeSide, tradeSize, price) {
  const pIdx = priceToLevelIdx(price);
  const restingDepth = tradeSide === SIDE.ASK ? lobBidDepth[pIdx] : lobAskDepth[pIdx];
  if (tradeSize > restingDepth && restingDepth > 0) {
    const dir = tradeSide === SIDE.ASK ? 1 : 2;
    if (dir === sequencingTradeDir) {
      sequencingConsecutive++;
    } else {
      sequencingTradeDir = dir;
      sequencingConsecutive = 1;
    }
    if (sequencingConsecutive >= 3) {
      const idx = currentCandleIdx % MAX_CANDLES;
      oftSequencingFlags[idx] = dir;
    }
  } else {
    if (sequencingConsecutive > 0) {
      sequencingConsecutive = 0;
      sequencingTradeDir = 0;
    }
  }
}

function processSlot(slot) {
  const ts = slot.timestamp_ns;
  if (candleStartNs === 0) candleStartNs = ts;
  if (candleBasePrice === 0 && slot.price > 0) candleBasePrice = slot.price;

  if (ts - candleStartNs >= candleIntervalMs * 1e6) {
    detectStackedImbalance();
    detectCVDDivergence();
    commitCandle();
    candleStartNs = ts;
    candleBasePrice = slot.price;
    candleFirstTrade = true;
    ibrSlotHigh = -Infinity;
    ibrSlotLow = Infinity;
  }

  if (slot.action === ACTION.TRADE || (slot.flags & FLAG_IS_TRADE)) {
    const tradePrice = slot.price;
    const tradeSize = slot.trade_size;
    const tradeSide = slot.side;

    if (candleFirstTrade) {
      barOpen = tradePrice;
      barHigh = tradePrice;
      barLow = tradePrice;
      barClose = tradePrice;
      candleFirstTrade = false;
    } else {
      if (tradePrice > barHigh) barHigh = tradePrice;
      if (tradePrice < barLow) barLow = tradePrice;
      barClose = tradePrice;
    }

    sessionVWAPNotional += tradePrice * tradeSize;
    sessionVWAPVolume += tradeSize;
    if (tradeSide === SIDE.ASK) {
      buyVWAPNotional += tradePrice * tradeSize;
      buyVWAPVolume += tradeSize;
    } else {
      sellVWAPNotional += tradePrice * tradeSize;
      sellVWAPVolume += tradeSize;
    }

    if (!ibrComputed && ibrSlotCount < IBR_PERIOD_COUNT) {
      if (tradePrice > ibrSlotHigh) ibrSlotHigh = tradePrice;
      if (tradePrice < ibrSlotLow) ibrSlotLow = tradePrice;
    }
    if (ibrSlotCount >= IBR_PERIOD_COUNT && !ibrComputed) {
      ibrHighPrice = ibrSlotHigh;
      ibrLowPrice = ibrSlotLow;
      ibrComputed = true;
    }

    recentTradePrices[recentTradeIdx % 5] = tradePrice;
    recentTradeSide[recentTradeIdx % 5] = tradeSide;
    recentTradeIdx++;
    recentTradeFill = Math.min(recentTradeFill + 1, 5);
    if (recentTradeFill >= 5) detectSweep(currentCandleIdx % MAX_CANDLES);

  computeCVD(tradeSize, tradeSide);
  computeImbalance(tradePrice, tradeSize, tradeSide);
  updateVolumeProfile(tradePrice, tradeSize);
  updateTPO(ts, tradePrice);
  updateRollingMeanTradeSize(tradeSize);
  const bookDepth = tradeSide === SIDE.BID ? slot.ask_size : slot.bid_size;
  detectAbsorption(tradePrice, tradeSize, bookDepth || 0);
  detectSequencing(tradeSide, tradeSize, tradePrice);
}

  if (slot.action === ACTION.UPDATE && slot.order_id > 0) {
    detectIceberg(slot.order_id, slot.side === SIDE.BID ? slot.bid_size : slot.ask_size, 0, slot.price);
  }

  if (slot.action === ACTION.TOP_OF_BOOK) {
    const prevBid = bboBid[(bboSlotIdx - 1 + BBO_HISTORY_DEPTH) % BBO_HISTORY_DEPTH] || slot.price - tickSizeFromPrice(slot.price);
    const prevAsk = bboAsk[(bboSlotIdx - 1 + BBO_HISTORY_DEPTH) % BBO_HISTORY_DEPTH] || slot.price + tickSizeFromPrice(slot.price);
    const bidP = slot.side === SIDE.BID ? slot.price : prevBid;
    const askP = slot.side === SIDE.ASK ? slot.price : prevAsk;
    updateBBO(bidP, askP);
    updateLOBDepth(bidP, slot.bid_size || 0, askP, slot.ask_size || 0);
  }

  if (slot.action === ACTION.INSERT || slot.action === ACTION.UPDATE) {
    const pIdx = priceToLevelIdx(slot.price);
    if (pIdx < MAX_PRICE_LEVELS) {
      if (slot.side === SIDE.BID) lobBidDepth[pIdx] = slot.bid_size;
      else lobAskDepth[pIdx] = slot.ask_size;
    }
  }

  if (slot.action === ACTION.DELETE) {
    const pIdx = priceToLevelIdx(slot.price);
    if (pIdx < MAX_PRICE_LEVELS) {
      if (slot.side === SIDE.BID) lobBidDepth[pIdx] = 0;
      else lobAskDepth[pIdx] = 0;
    }
  }

  featureHeader[FEATURE.CURRENT_SLOT / 4] = algoReadIdx;
}

const outSlot = createSlot();

function processLoop() {
  if (!ringBuffer) return;
  const writeIdx = Atomics.load(ringBuffer.controlView, CONTROL_WRITE_INDEX / 4);
  let readIdx = algoReadIdx;
  let processed = 0;
  const maxProcess = 8192;
  while (readIdx !== writeIdx && processed < maxProcess) {
    ringBuffer.readSlotAt(readIdx, outSlot);
    processSlot(outSlot);
    readIdx = (readIdx + 1) & (SLOT_COUNT - 1);
    processed++;
  }
  algoReadIdx = readIdx;
  setTimeout(processLoop, 0);
}

self.onmessage = (e) => {
  const { type, data } = e.data;
  switch (type) {
    case 'init': {
      tickSAB = data.sab;
      featureSAB = data.featureSAB;
      ringBuffer = RingBuffer.create(tickSAB);
      initFeatureArrays();
      sessionStartNs = 0;
      currentCandleIdx = 0;
      previousCVD = 0;
      bboSlotIdx = 0;
      algoReadIdx = 0;
      barOpen = 0;
      barHigh = 0;
      barLow = 0;
      barClose = 0;
      candleFirstTrade = true;
      sessionVWAPNotional = 0;
      sessionVWAPVolume = 0;
      buyVWAPNotional = 0;
      buyVWAPVolume = 0;
      sellVWAPNotional = 0;
      sellVWAPVolume = 0;
      ibrHighPrice = 0;
      ibrLowPrice = 0;
      ibrComputed = false;
      ibrSlotHigh = -Infinity;
      ibrSlotLow = Infinity;
      ibrSlotCount = 0;
      prevSessionPOC = 0;
      nakedPOCRetested = false;
      recentTradeIdx = 0;
      recentTradeFill = 0;
      candleBidVol.fill(0);
      candleAskVol.fill(0);
      candleTotalVol.fill(0);
      candleLocalBidVol.fill(0);
      candleLocalAskVol.fill(0);
      processLoop();
      self.postMessage({ type: 'algo-ready' });
      break;
    }
    case 'set-candle-interval':
      candleIntervalMs = data.intervalMs;
      break;
    case 'get-cvd': {
      const result = [];
      const count = Math.min(currentCandleIdx, MAX_CANDLES);
      for (let i = 0; i < count; i++) result.push(cvd[i]);
      self.postMessage({ type: 'cvd-data', data: result });
      break;
    }
  }
};
