import { initSpriteAtlas, blitText, blitTextBatch, formatVolume, formatDelta, getImbalanceTile } from './SpriteAtlas.js';
import { drawCandles } from './CandlestickRenderer.js';
import {
  FEATURE_SAB_SIZE, FEATURE, MAX_CANDLES, MAX_PRICE_LEVELS, CANDLE_PRICE_LEVELS,
} from '../types/MemoryLayout.js';
import TerminalConfig from '../config/TerminalConfig.js';
import { CustomVolumeProfile } from './CustomVolumeProfile.js';

const BG_DARK = TerminalConfig.BG_PRIMARY;
const BG_BID = TerminalConfig.COLOR_BID_DIM;
const BG_ASK = TerminalConfig.COLOR_ASK_DIM;
const COLOR_BID_TEXT = TerminalConfig.BEARISH;
const COLOR_ASK_TEXT = TerminalConfig.BULLISH;
const COLOR_NEUTRAL = TerminalConfig.COLOR_TEXT_MUTED;
const COLOR_VPOC = TerminalConfig.COLOR_POC;
const COLOR_DELTA_POS = TerminalConfig.BULLISH;
const COLOR_DELTA_NEG = TerminalConfig.BEARISH;
const COLOR_STACKED_ASK = TerminalConfig.COLOR_STACKED_ASK;
const COLOR_STACKED_BID = TerminalConfig.COLOR_STACKED_BID;
const COLOR_VA = TerminalConfig.COLOR_VA_FILL;
const COLOR_PROFILE_BAR = TerminalConfig.COLOR_PROFILE_BAR;
const COLOR_POC_LINE = TerminalConfig.COLOR_POC_LINE;
const COLOR_VAH_LINE = TerminalConfig.COLOR_VAH_LINE;
const COLOR_VAL_LINE = TerminalConfig.COLOR_VAL_LINE;
const COLOR_IMBALANCE = TerminalConfig.COLOR_IMBALANCE;
const COLOR_ABSORPTION = TerminalConfig.COLOR_ABSORPTION;
const COLOR_DIV_BULL = TerminalConfig.BULLISH;
const COLOR_DIV_BEAR = TerminalConfig.BEARISH;
const COLOR_VWAP = '#F2C94C';
const COLOR_BUY_VWAP = '#26A69A';
const COLOR_SELL_VWAP = '#EF5350';
const COLOR_IBR = 'rgba(242, 201, 76, 0.08)';
const COLOR_SINGLE_PRINT_DOT = '#F2C94C';
const COLOR_BUYING_TAIL = '#26A69A';
const COLOR_SELLING_TAIL = '#EF5350';
const COLOR_NAKED_POC = 'rgba(242, 201, 76, 0.6)';
const COLOR_EXHAUSTION_BULL = '#26A69A';
const COLOR_EXHAUSTION_BEAR = '#EF5350';
const COLOR_SWEEP_BUY = 'rgba(38, 166, 154, 0.4)';
const COLOR_SWEEP_SELL = 'rgba(239, 83, 80, 0.4)';
const COLOR_OFT_EXHAUSTION = 'rgba(239, 83, 80, 0.45)';
const COLOR_OFT_DEFENSE = 'rgba(38, 166, 154, 0.45)';
const COLOR_SLINGSHOT_BULL = '#26A69A';
const COLOR_SLINGSHOT_BEAR = '#EF5350';
const COLOR_WEAKNESS_BUY = '#EF5350';
const COLOR_WEAKNESS_SELL = '#26A69A';
const COLOR_SEQUENCE_BUY = '#26A69A';
const COLOR_SEQUENCE_SELL = '#EF5350';

const _textBuf = [];

export class FootprintCanvas {
  constructor(offscreenCanvas, featureSAB) {
    this.canvas = offscreenCanvas;
    this.ctx = offscreenCanvas.getContext('2d');
    this.featureSAB = featureSAB;
    this.width = offscreenCanvas.width;
    this.height = offscreenCanvas.height;

    this.featureHeader = new Int32Array(featureSAB, 0, FEATURE.HEADER_SIZE / 4);
    this.cvd = new Float64Array(featureSAB, FEATURE.CVD_OFFSET, MAX_CANDLES);
    this.delta = new Float64Array(featureSAB, FEATURE.DELTA_OFFSET, MAX_CANDLES);
    this.imbalanceMap = new Float32Array(featureSAB, FEATURE.IMBALANCE_MAP_OFFSET, MAX_PRICE_LEVELS);
    this.stackedImbalance = new Uint8Array(featureSAB, FEATURE.STACKED_IMBALANCE_OFFSET, MAX_PRICE_LEVELS);
    this.vpoc = new Float64Array(featureSAB, FEATURE.VPOC_OFFSET, MAX_CANDLES);
    this.volumeProfile = new Float64Array(featureSAB, FEATURE.VOLUME_PROFILE_OFFSET, MAX_PRICE_LEVELS);
    this.tpoMap = new Uint32Array(featureSAB, FEATURE.TPO_MAP_OFFSET, MAX_PRICE_LEVELS * 96);
    this.maxDelta = new Float64Array(featureSAB, FEATURE.MAX_DELTA_OFFSET, MAX_CANDLES);
    this.minDelta = new Float64Array(featureSAB, FEATURE.MIN_DELTA_OFFSET, MAX_CANDLES);
    this.totalVolume = new Float64Array(featureSAB, FEATURE.TOTAL_VOLUME_OFFSET, MAX_CANDLES);
    this.divergenceFlags = new Uint8Array(featureSAB, FEATURE.DIVERGENCE_OFFSET, MAX_CANDLES);
    this.absorptionFlags = new Uint8Array(featureSAB, FEATURE.ABSORPTION_FLAGS_OFFSET, MAX_PRICE_LEVELS);
    this.candleBidVolGrid = new Float32Array(featureSAB, FEATURE.CANDLE_BID_VOL_OFFSET, MAX_CANDLES * CANDLE_PRICE_LEVELS);
    this.candleAskVolGrid = new Float32Array(featureSAB, FEATURE.CANDLE_ASK_VOL_OFFSET, MAX_CANDLES * CANDLE_PRICE_LEVELS);
    this.ohlcOpen = new Float64Array(featureSAB, FEATURE.OHLC_OPEN_OFFSET, MAX_CANDLES);
    this.ohlcHigh = new Float64Array(featureSAB, FEATURE.OHLC_HIGH_OFFSET, MAX_CANDLES);
    this.ohlcLow = new Float64Array(featureSAB, FEATURE.OHLC_LOW_OFFSET, MAX_CANDLES);
    this.ohlcClose = new Float64Array(featureSAB, FEATURE.OHLC_CLOSE_OFFSET, MAX_CANDLES);
    this.sessionVWAPView = new Float64Array(featureSAB, FEATURE.SESSION_VWAP_OFFSET, 2);
    this.buyVWAPView = new Float64Array(featureSAB, FEATURE.BUY_VWAP_OFFSET, 2);
    this.sellVWAPView = new Float64Array(featureSAB, FEATURE.SELL_VWAP_OFFSET, 2);
    this.ibrHighView = new Float64Array(featureSAB, FEATURE.IBR_HIGH_OFFSET, 1);
    this.ibrLowView = new Float64Array(featureSAB, FEATURE.IBR_LOW_OFFSET, 1);
    this.singlePrintsView = new Uint8Array(featureSAB, FEATURE.SINGLE_PRINTS_OFFSET, MAX_PRICE_LEVELS);
    this.buyingTailView = new Float64Array(featureSAB, FEATURE.BUYING_TAIL_OFFSET, 1);
    this.sellingTailView = new Float64Array(featureSAB, FEATURE.SELLING_TAIL_OFFSET, 1);
    this.nakedPOCView = new Float64Array(featureSAB, FEATURE.NAKED_POC_OFFSET, 1);
    this.exhaustionFlags = new Uint8Array(featureSAB, FEATURE.EXHAUSTION_OFFSET, MAX_CANDLES);
    this.sweepFlags = new Uint8Array(featureSAB, FEATURE.SWEEP_FLAGS_OFFSET, MAX_CANDLES);
    this.oftRatioMap = new Uint8Array(featureSAB, FEATURE.OFT_RATIO_OFFSET, MAX_CANDLES * CANDLE_PRICE_LEVELS);
    this.oftSlingshotFlags = new Uint8Array(featureSAB, FEATURE.OFT_SLINGSHOT_OFFSET, MAX_CANDLES);
    this.oftWeaknessFlags = new Uint8Array(featureSAB, FEATURE.OFT_WEAKNESS_OFFSET, MAX_CANDLES);
    this.oftSequencingFlags = new Uint8Array(featureSAB, FEATURE.OFT_SEQUENCING_OFFSET, MAX_CANDLES);

  this.viewState = {
    scrollX: 0,
    zoom: 40,
    priceMin: 4490,
    priceMax: 4510,
    pixelsPerTick: 0,
    priceScaleMode: 'linear',
  };

  this.customVolumeProfile = new CustomVolumeProfile();
  this.tickSize = 0.25;
    this.candleIntervalMs = 60000;
    this.chartType = 'footprint';
    this.showTPO = false;
    this.showVolumeProfile = true;
    this.showImbalance = true;
    this.showStackedImbalance = true;
    this.showCellNumbers = true;
    this.showAbsorption = true;
    this.showDivergence = true;
    this.showVWAP = true;
    this.showTPOFeatures = true;
    this.showOrderflows = true;
    this.volumeProfileWidth = 80;

    initSpriteAtlas();
    this._running = false;
  }

  priceToY(price) {
    const { priceMin, priceMax, priceScaleMode } = this.viewState;
    if (priceScaleMode === 'log') {
      const logMin = Math.log(priceMin);
      const logMax = Math.log(priceMax);
      return this.height - ((Math.log(price) - logMin) / (logMax - logMin)) * this.height;
    }
    if (priceScaleMode === 'sqrt') {
      const sqrtMin = Math.sqrt(priceMin);
      const sqrtMax = Math.sqrt(priceMax);
      return this.height - ((Math.sqrt(price) - sqrtMin) / (sqrtMax - sqrtMin)) * this.height;
    }
    return this.height - ((price - priceMin) / (priceMax - priceMin)) * this.height;
  }

  yToPrice(y) {
    const { priceMin, priceMax, priceScaleMode } = this.viewState;
    if (priceScaleMode === 'log') {
      const logMin = Math.log(priceMin);
      const logMax = Math.log(priceMax);
      const logPrice = logMin + ((this.height - y) / this.height) * (logMax - logMin);
      return Math.exp(logPrice);
    }
    if (priceScaleMode === 'sqrt') {
      const sqrtMin = Math.sqrt(priceMin);
      const sqrtMax = Math.sqrt(priceMax);
      const sqrtPrice = sqrtMin + ((this.height - y) / this.height) * (sqrtMax - sqrtMin);
      return sqrtPrice * sqrtPrice;
    }
    return priceMin + ((this.height - y) / this.height) * (priceMax - priceMin);
  }

  updateViewState(vs) {
    this.viewState = { ...this.viewState, ...vs };
    this.viewState.pixelsPerTick =
      this.height / ((this.viewState.priceMax - this.viewState.priceMin) / this.tickSize);
  }

  start() {
    this._running = true;
    this._renderLoop();
  }

  stop() {
    this._running = false;
  }

  _renderLoop() {
    if (!this._running) return;
    this.render();
    requestAnimationFrame(() => this._renderLoop());
  }

  render() {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;

    ctx.fillStyle = BG_DARK;
    ctx.fillRect(0, 0, w, h);

    const chartWidth = w - this.volumeProfileWidth;
    const candleCount = this.featureHeader[FEATURE.CANDLE_COUNT / 4] || 0;
    if (candleCount === 0) return;

    const visibleCandles = Math.max(1, Math.floor(chartWidth / this.viewState.zoom));
    const startCandle = Math.max(0, candleCount - visibleCandles - this.viewState.scrollX);
    const endCandle = Math.min(candleCount, startCandle + visibleCandles);

    this._drawGrid(ctx, chartWidth);

    if (this.chartType === 'candlestick') {
      drawCandles(ctx, this.ohlcOpen, this.ohlcHigh, this.ohlcLow, this.ohlcClose, startCandle, endCandle, chartWidth, this.viewState, this.tickSize);
    } else {
      this._drawCandles(ctx, startCandle, endCandle, chartWidth);
    }

    this._drawStackedImbalanceZones(ctx, startCandle, endCandle, chartWidth);

    if (this.showVWAP) {
      this._drawVWAP(ctx, chartWidth);
    }

    if (this.showTPOFeatures) {
      this._drawIBR(ctx, startCandle, endCandle, chartWidth);
      this._drawSinglePrints(ctx, startCandle, endCandle, chartWidth);
      this._drawTails(ctx, chartWidth);
      this._drawNakedPOC(ctx, chartWidth);
    }

    if (this.showOrderflows) {
      this._drawExhaustion(ctx, startCandle, endCandle, chartWidth);
      this._drawSweeps(ctx, startCandle, endCandle, chartWidth);
      this._drawOFTRatio(ctx, startCandle, endCandle, chartWidth);
      this._drawPOCSlingshot(ctx, startCandle, endCandle, chartWidth);
      this._drawMarketWeakness(ctx, startCandle, endCandle, chartWidth);
      this._drawSequencing(ctx, startCandle, endCandle, chartWidth);
    }

    if (this.showVolumeProfile) {
      this._drawVolumeProfile(ctx, chartWidth);
    }

    if (this.showVolumeProfile && this.customVolumeProfile.profiles.length > 0) {
      this.customVolumeProfile.render(
        ctx,
        (price) => this.priceToY(price),
        chartWidth,
        this.volumeProfileWidth,
        this.viewState.pixelsPerTick
      );
    }

    if (this.customVolumeProfile.previewActive) {
      this.customVolumeProfile.render(
        ctx,
        (price) => this.priceToY(price),
        chartWidth,
        this.volumeProfileWidth,
        this.viewState.pixelsPerTick
      );
    }

    if (this.showTPO) {
      this._drawTPOProfile(ctx, chartWidth);
    }

    this._drawBarStats(ctx, startCandle, endCandle, chartWidth);
    this._drawPriceAxis(ctx, chartWidth);
  }

  _drawGrid(ctx, chartWidth) {
    const { priceMin, priceMax } = this.viewState;
    const step = this.tickSize * 4;

    ctx.strokeStyle = '#1E222D';
    ctx.lineWidth = 0.5;

    for (let price = priceMin; price <= priceMax; price += step) {
      const y = this.priceToY(price);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(chartWidth, y);
      ctx.stroke();
    }
  }

  _drawCandles(ctx, startCandle, endCandle, chartWidth) {
    const { zoom } = this.viewState;
    const candleSpacing = 2;
    const candleWidth = zoom - candleSpacing;
    const { priceMin, priceMax } = this.viewState;
    const numLevels = Math.ceil((priceMax - priceMin) / this.tickSize);
    const rowHeight = Math.max(1, this.viewState.pixelsPerTick);
    const halfWidth = candleWidth / 2;
    const canShowNumbers = this.showCellNumbers && halfWidth >= 10 && rowHeight >= 8;

    for (let c = startCandle; c < endCandle; c++) {
      const x = chartWidth - (c - startCandle + 1) * zoom + candleSpacing / 2;
      if (x + candleWidth < 0) continue;

      const candleDelta = this.delta[c] || 0;
      const candleTotal = this.totalVolume[c] || 0;
      const vpocPrice = this.vpoc[c] || 0;
      const divFlag = this.divergenceFlags[c] || 0;
      const gridOff = c * CANDLE_PRICE_LEVELS;

      if (this.showDivergence && divFlag > 0) {
        ctx.fillStyle = divFlag === 1 ? 'rgba(38,166,154,0.15)' : 'rgba(239,83,80,0.15)';
        ctx.fillRect(x, 0, candleWidth, this.height);
      }

      _textBuf.length = 0;

      for (let p = 0; p < numLevels; p++) {
        const price = priceMin + p * this.tickSize;
        const y = this.priceToY(price);
        if (y < 0 || y > this.height) continue;
        const boxY = y - rowHeight / 2;

        ctx.fillStyle = BG_BID;
        ctx.fillRect(x, boxY, halfWidth, rowHeight);

        ctx.fillStyle = BG_ASK;
        ctx.fillRect(x + halfWidth, boxY, halfWidth, rowHeight);

        if (this.showImbalance) {
          const pIdx = Math.floor(price * 1000);
          if (pIdx >= 0 && pIdx < MAX_PRICE_LEVELS) {
            const imbVal = this.imbalanceMap[pIdx];
            if (imbVal > 0) {
              ctx.fillStyle = COLOR_STACKED_ASK;
              ctx.fillRect(x, boxY, candleWidth, rowHeight);
              ctx.fillStyle = COLOR_IMBALANCE;
              ctx.beginPath();
              ctx.moveTo(x + candleWidth - 6, boxY + 2);
              ctx.lineTo(x + candleWidth - 2, boxY + rowHeight / 2);
              ctx.lineTo(x + candleWidth - 6, boxY + rowHeight - 2);
              ctx.fill();
            } else if (imbVal < 0) {
              ctx.fillStyle = COLOR_STACKED_BID;
              ctx.fillRect(x, boxY, candleWidth, rowHeight);
              ctx.fillStyle = COLOR_IMBALANCE;
              ctx.beginPath();
              ctx.moveTo(x + 2, boxY + 2);
              ctx.lineTo(x + 6, boxY + rowHeight / 2);
              ctx.lineTo(x + 2, boxY + rowHeight - 2);
              ctx.fill();
            }
          }
        }

        if (this.showAbsorption) {
          const pIdx = Math.floor(price * 1000);
          if (pIdx >= 0 && pIdx < MAX_PRICE_LEVELS && this.absorptionFlags[pIdx]) {
            ctx.fillStyle = COLOR_ABSORPTION;
            ctx.globalAlpha = 0.6;
            ctx.fillRect(x, boxY, candleWidth, rowHeight);
            ctx.globalAlpha = 1.0;
          }
        }

        if (vpocPrice > 0 && Math.abs(price - vpocPrice) < this.tickSize * 0.5) {
          ctx.fillStyle = COLOR_VPOC;
          ctx.fillRect(x, boxY, candleWidth, 2);
        }

        if (canShowNumbers) {
          const ts = this.tickSize;
          const localIdx = Math.round((price - vpocPrice) / ts) + Math.floor(CANDLE_PRICE_LEVELS / 2);
          const li = localIdx >= 0 && localIdx < CANDLE_PRICE_LEVELS ? localIdx : -1;

          let bidVol = 0;
          let askVol = 0;
          if (li >= 0) {
            bidVol = this.candleBidVolGrid[gridOff + li] || 0;
            askVol = this.candleAskVolGrid[gridOff + li] || 0;
          }

          if (bidVol > 0) {
            _textBuf.push({ text: formatVolume(bidVol), x: x + 1, y: boxY + 1, size: 12, color: COLOR_BID_TEXT });
          }
          if (askVol > 0) {
            _textBuf.push({ text: formatVolume(askVol), x: x + halfWidth + 1, y: boxY + 1, size: 12, color: COLOR_ASK_TEXT });
          }
        }
      }

      if (candleTotal > 0) {
        const deltaStr = formatDelta(candleDelta);
        const color = candleDelta >= 0 ? COLOR_DELTA_POS : COLOR_DELTA_NEG;
        _textBuf.push({ text: deltaStr, x: x + 2, y: this.height - 18, size: 12, color });

        const volStr = formatVolume(candleTotal);
        _textBuf.push({ text: volStr, x: x + 2, y: this.height - 32, size: 12, color: COLOR_NEUTRAL });
      }

      if (this.showDivergence && divFlag > 0) {
        const divColor = divFlag === 1 ? COLOR_DIV_BULL : COLOR_DIV_BEAR;
        ctx.fillStyle = divColor;
        ctx.globalAlpha = 0.4;
        ctx.fillRect(x, 0, 2, this.height);
        ctx.globalAlpha = 1.0;
      }

      if (_textBuf.length > 0) {
        blitTextBatch(ctx, _textBuf);
        _textBuf.length = 0;
      }
    }
  }

  _drawStackedImbalanceZones(ctx, startCandle, endCandle, chartWidth) {
    if (!this.showStackedImbalance) return;

    const { priceMin, priceMax } = this.viewState;
    const numLevels = Math.ceil((priceMax - priceMin) / this.tickSize);

    for (let p = 0; p < numLevels; p++) {
      const price = priceMin + p * this.tickSize;
      const pIdx = Math.floor(price * 1000);
      if (pIdx >= 0 && pIdx < MAX_PRICE_LEVELS && this.stackedImbalance[pIdx]) {
        const y = this.priceToY(price);
        const rowHeight = Math.max(1, this.viewState.pixelsPerTick);

        const isAsk = this.imbalanceMap[pIdx] > 0;
        ctx.fillStyle = isAsk ? COLOR_STACKED_ASK : COLOR_STACKED_BID;
        ctx.fillRect(0, y - rowHeight / 2, chartWidth, 3);

        ctx.fillStyle = COLOR_IMBALANCE;
        ctx.fillRect(0, y - 1, chartWidth, 2);
      }
    }
  }

  _drawBarStats(ctx, startCandle, endCandle, chartWidth) {
    const { zoom } = this.viewState;
    _textBuf.length = 0;

    for (let c = startCandle; c < endCandle; c++) {
      const x = chartWidth - (c - startCandle + 1) * zoom;
      if (x + zoom < 0) continue;

      const md = this.maxDelta[c];
      const mid = this.minDelta[c];
      const tv = this.totalVolume[c];
      const cvdVal = this.cvd[c] || 0;
      const vpocVal = this.vpoc[c] || 0;
      if (tv === 0) continue;

      const statsY = this.height - 64;

      ctx.fillStyle = 'rgba(11, 14, 17, 0.90)';
      ctx.fillRect(x, statsY - 2, zoom - 2, 62);

      _textBuf.push({ text: 'D:', x: x + 2, y: statsY, size: 12, color: COLOR_NEUTRAL });
      _textBuf.push({ text: formatDelta(md), x: x + 16, y: statsY, size: 12, color: md >= 0 ? COLOR_DELTA_POS : COLOR_DELTA_NEG });

      _textBuf.push({ text: 'd:', x: x + 2, y: statsY + 12, size: 12, color: COLOR_NEUTRAL });
      _textBuf.push({ text: formatDelta(mid), x: x + 16, y: statsY + 12, size: 12, color: mid >= 0 ? COLOR_DELTA_POS : COLOR_DELTA_NEG });

      _textBuf.push({ text: 'V:', x: x + 2, y: statsY + 24, size: 12, color: COLOR_NEUTRAL });
      _textBuf.push({ text: formatVolume(tv), x: x + 14, y: statsY + 24, size: 12, color: '#E1E4E8' });

      _textBuf.push({ text: 'C:', x: x + 2, y: statsY + 36, size: 12, color: COLOR_NEUTRAL });
      _textBuf.push({ text: formatDelta(cvdVal), x: x + 14, y: statsY + 36, size: 12, color: cvdVal >= 0 ? COLOR_DELTA_POS : COLOR_DELTA_NEG });

      if (vpocVal > 0) {
        _textBuf.push({ text: 'P:', x: x + 2, y: statsY + 48, size: 12, color: COLOR_NEUTRAL });
        _textBuf.push({ text: vpocVal.toFixed(2), x: x + 14, y: statsY + 48, size: 12, color: COLOR_VPOC });
      }
    }

    if (_textBuf.length > 0) {
      blitTextBatch(ctx, _textBuf);
      _textBuf.length = 0;
    }
  }

  _drawVolumeProfile(ctx, chartWidth) {
    const { priceMin, priceMax } = this.viewState;
    const profileX = chartWidth;
    const profileWidth = this.volumeProfileWidth;
    const numLevels = Math.ceil((priceMax - priceMin) / this.tickSize);

    let maxVol = 0;
    let totalVol = 0;
    let pocPrice = 0;

    for (let p = 0; p < numLevels; p++) {
      const price = priceMin + p * this.tickSize;
      const pIdx = Math.floor(price * 1000);
      if (pIdx >= 0 && pIdx < MAX_PRICE_LEVELS) {
        const vol = this.volumeProfile[pIdx];
        if (vol > maxVol) { maxVol = vol; pocPrice = price; }
        totalVol += vol;
      }
    }

    if (maxVol === 0) return;

    const vaTarget = totalVol * TerminalConfig.VALUE_AREA_PERCENT;
    let vaCount = 0;
    let vah = pocPrice;
    let val = pocPrice;
    let goUp = true, goDown = true;
    let upIdx = 1, downIdx = 1;

    while (vaCount < vaTarget && (goUp || goDown)) {
      const priceUp = pocPrice + upIdx * this.tickSize;
      const priceDown = pocPrice - downIdx * this.tickSize;
      const idxUp = Math.floor(priceUp * 1000);
      const idxDown = Math.floor(priceDown * 1000);
      let volUp = 0, volDown = 0;
      if (idxUp >= 0 && idxUp < MAX_PRICE_LEVELS && goUp) volUp = this.volumeProfile[idxUp]; else goUp = false;
      if (idxDown >= 0 && idxDown < MAX_PRICE_LEVELS && goDown) volDown = this.volumeProfile[idxDown]; else goDown = false;
      if (volUp >= volDown && goUp) { vah = priceUp; vaCount += volUp; upIdx++; }
      else if (goDown) { val = priceDown; vaCount += volDown; downIdx++; }
      else break;
    }

    ctx.fillStyle = 'rgba(11, 14, 17, 0.6)';
    ctx.fillRect(profileX, 0, profileWidth, this.height);

    const lobBidDepth = new Float64Array(this.featureSAB, FEATURE.LOB_BID_DEPTH_OFFSET, MAX_PRICE_LEVELS);
    const lobAskDepth = new Float64Array(this.featureSAB, FEATURE.LOB_ASK_DEPTH_OFFSET, MAX_PRICE_LEVELS);

    for (let p = 0; p < numLevels; p++) {
      const price = priceMin + p * this.tickSize;
      const pIdx = Math.floor(price * 1000);
      if (pIdx < 0 || pIdx >= MAX_PRICE_LEVELS) continue;
      const vol = this.volumeProfile[pIdx];
      if (vol === 0) continue;
      const y = this.priceToY(price);
      const rowHeight = Math.max(1, this.viewState.pixelsPerTick);
      const barWidth = (vol / maxVol) * (profileWidth - 4);
      const inVA = price >= val && price <= vah;
      ctx.fillStyle = inVA ? COLOR_VA : COLOR_PROFILE_BAR;
      ctx.fillRect(profileX + 2, y - rowHeight / 2, barWidth, rowHeight);

      const bidD = lobBidDepth[pIdx];
      const askD = lobAskDepth[pIdx];
      if (bidD > 0 && maxVol > 0) {
        const bw = (bidD / (maxVol * 2)) * (profileWidth - 4);
        ctx.fillStyle = 'rgba(239,83,80,0.25)';
        ctx.fillRect(profileX + 2, y - rowHeight / 2, Math.min(bw, profileWidth - 4), rowHeight * 0.4);
      }
      if (askD > 0 && maxVol > 0) {
        const aw = (askD / (maxVol * 2)) * (profileWidth - 4);
        ctx.fillStyle = 'rgba(38,166,154,0.25)';
        ctx.fillRect(profileX + 2, y, Math.min(aw, profileWidth - 4), rowHeight * 0.4);
      }
    }

    const pocY = this.priceToY(pocPrice);
    ctx.strokeStyle = COLOR_POC_LINE;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(profileX, pocY);
    ctx.lineTo(profileX + profileWidth, pocY);
    ctx.stroke();

    ctx.strokeStyle = COLOR_POC_LINE;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, pocY);
    ctx.lineTo(chartWidth, pocY);
    ctx.stroke();

    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = COLOR_VAH_LINE;
    ctx.beginPath();
    ctx.moveTo(profileX, this.priceToY(vah));
    ctx.lineTo(profileX + profileWidth, this.priceToY(vah));
    ctx.stroke();

    ctx.strokeStyle = COLOR_VAH_LINE;
    ctx.beginPath();
    ctx.moveTo(0, this.priceToY(vah));
    ctx.lineTo(chartWidth, this.priceToY(vah));
    ctx.stroke();

    ctx.strokeStyle = COLOR_VAL_LINE;
    ctx.beginPath();
    ctx.moveTo(profileX, this.priceToY(val));
    ctx.lineTo(profileX + profileWidth, this.priceToY(val));
    ctx.stroke();

    ctx.strokeStyle = COLOR_VAL_LINE;
    ctx.beginPath();
    ctx.moveTo(0, this.priceToY(val));
    ctx.lineTo(chartWidth, this.priceToY(val));
    ctx.stroke();

    ctx.setLineDash([]);
  }

  _drawTPOProfile(ctx, chartWidth) {
    const currentTPOSlot = this.featureHeader[FEATURE.TPO_SLOT_IDX / 4] || 0;
    const { priceMin, priceMax } = this.viewState;
    const numLevels = Math.ceil((priceMax - priceMin) / this.tickSize);
    const tpoLetters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    for (let p = 0; p < numLevels; p++) {
      const price = priceMin + p * this.tickSize;
      const pIdx = Math.floor(price * 1000);
      if (pIdx < 0 || pIdx >= MAX_PRICE_LEVELS) continue;
      const y = this.priceToY(price);
      const rowHeight = Math.max(1, this.viewState.pixelsPerTick);
      for (let s = 0; s <= currentTPOSlot && s < 96; s++) {
        if (this.tpoMap[pIdx * 96 + s] > 0) {
          const letter = s < 26 ? tpoLetters[s] : tpoLetters[s % 26];
          blitText(ctx, letter, chartWidth + s * 8, y - rowHeight / 2, 12, '#26A69A');
        }
      }
    }
  }

  _drawPriceAxis(ctx, chartWidth) {
    const { priceMin, priceMax } = this.viewState;
    const step = this.tickSize * 4;

    ctx.fillStyle = 'rgba(19, 23, 34, 0.95)';
    ctx.fillRect(chartWidth - 62, 0, 62, this.height);

    ctx.strokeStyle = '#1E222D';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(chartWidth - 62, 0);
    ctx.lineTo(chartWidth - 62, this.height);
    ctx.stroke();

    for (let price = priceMin; price <= priceMax; price += step) {
      const y = this.priceToY(price);
      if (y < 10 || y > this.height - 10) continue;

      ctx.strokeStyle = '#1E222D';
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(chartWidth - 62, y);
      ctx.lineTo(chartWidth, y);
      ctx.stroke();

      blitText(ctx, price.toFixed(2), chartWidth - 60, y - 6, 12, '#787B86');
    }
  }

  _drawVWAP(ctx, chartWidth) {
    const vwap = this.sessionVWAPView[0];
    const buyVwap = this.buyVWAPView[0];
    const sellVwap = this.sellVWAPView[0];

    if (vwap > 0) {
      const y = this.priceToY(vwap);
      ctx.strokeStyle = COLOR_VWAP;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(chartWidth, y);
      ctx.stroke();
      blitText(ctx, 'VWAP', chartWidth - 45, y - 14, 12, COLOR_VWAP);
    }
    if (buyVwap > 0) {
      const y = this.priceToY(buyVwap);
      ctx.strokeStyle = COLOR_BUY_VWAP;
      ctx.lineWidth = 1;
      ctx.setLineDash([6, 3]);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(chartWidth, y);
      ctx.stroke();
      blitText(ctx, 'BVWAP', chartWidth - 50, y - 14, 12, COLOR_BUY_VWAP);
    }
    if (sellVwap > 0) {
      const y = this.priceToY(sellVwap);
      ctx.strokeStyle = COLOR_SELL_VWAP;
      ctx.lineWidth = 1;
      ctx.setLineDash([6, 3]);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(chartWidth, y);
      ctx.stroke();
      blitText(ctx, 'SVWAP', chartWidth - 50, y - 14, 12, COLOR_SELL_VWAP);
    }
    ctx.setLineDash([]);
  }

  _drawIBR(ctx, startCandle, endCandle, chartWidth) {
    const ibrH = this.ibrHighView[0];
    const ibrL = this.ibrLowView[0];
    if (ibrH === 0 && ibrL === 0) return;

    const { zoom } = this.viewState;
    const ibrWidth = zoom * 2;
    const ibrX = chartWidth - ibrWidth;

    const yHigh = this.priceToY(ibrH);
    const yLow = this.priceToY(ibrL);
    ctx.fillStyle = COLOR_IBR;
    ctx.fillRect(ibrX, yHigh, ibrWidth, yLow - yHigh);

    ctx.strokeStyle = 'rgba(242, 201, 76, 0.25)';
    ctx.lineWidth = 0.5;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(0, yHigh);
    ctx.lineTo(chartWidth, yHigh);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, yLow);
    ctx.lineTo(chartWidth, yLow);
    ctx.stroke();
    ctx.setLineDash([]);

    blitText(ctx, 'IBH', 4, yHigh + 2, 12, COLOR_SINGLE_PRINT_DOT);
    blitText(ctx, 'IBL', 4, yLow - 14, 12, COLOR_SINGLE_PRINT_DOT);
  }

  _drawSinglePrints(ctx, startCandle, endCandle, chartWidth) {
    const { priceMin, priceMax, zoom } = this.viewState;
    const numLevels = Math.ceil((priceMax - priceMin) / this.tickSize);
    const rowHeight = Math.max(1, this.viewState.pixelsPerTick);

    for (let c = startCandle; c < endCandle; c++) {
      const x = chartWidth - (c - startCandle + 1) * zoom;
      for (let p = 0; p < numLevels; p++) {
        const price = priceMin + p * this.tickSize;
        const pIdx = Math.floor(price * 1000);
        if (pIdx < 0 || pIdx >= MAX_PRICE_LEVELS) continue;
        if (this.singlePrintsView[pIdx]) {
          const y = this.priceToY(price);
          ctx.fillStyle = COLOR_SINGLE_PRINT_DOT;
          ctx.beginPath();
          ctx.arc(x + zoom / 2, y, 2, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
  }

  _drawTails(ctx, chartWidth) {
    const buyTail = this.buyingTailView[0];
    const sellTail = this.sellingTailView[0];

    if (buyTail > 0) {
      const y = this.priceToY(buyTail);
      ctx.fillStyle = COLOR_BUYING_TAIL;
      ctx.beginPath();
      ctx.moveTo(chartWidth / 2, y + 8);
      ctx.lineTo(chartWidth / 2 - 5, y);
      ctx.lineTo(chartWidth / 2 + 5, y);
      ctx.closePath();
      ctx.fill();
      blitText(ctx, 'BT', chartWidth / 2 + 8, y - 6, 12, COLOR_BUYING_TAIL);
    }
    if (sellTail > 0) {
      const y = this.priceToY(sellTail);
      ctx.fillStyle = COLOR_SELLING_TAIL;
      ctx.beginPath();
      ctx.moveTo(chartWidth / 2, y - 8);
      ctx.lineTo(chartWidth / 2 - 5, y);
      ctx.lineTo(chartWidth / 2 + 5, y);
      ctx.closePath();
      ctx.fill();
      blitText(ctx, 'ST', chartWidth / 2 + 8, y - 6, 12, COLOR_SELLING_TAIL);
    }
  }

  _drawNakedPOC(ctx, chartWidth) {
    const nPOC = this.nakedPOCView[0];
    if (nPOC <= 0) return;
    const y = this.priceToY(nPOC);

    ctx.strokeStyle = COLOR_NAKED_POC;
    ctx.lineWidth = 1;
    ctx.setLineDash([8, 4]);
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(chartWidth, y);
    ctx.stroke();
    ctx.setLineDash([]);

    blitText(ctx, 'nPOC', 4, y - 14, 12, COLOR_NAKED_POC);
  }

  _drawExhaustion(ctx, startCandle, endCandle, chartWidth) {
    const { zoom } = this.viewState;
    const { priceMin, priceMax } = this.viewState;

    for (let c = startCandle; c < endCandle; c++) {
      const flag = this.exhaustionFlags[c] || 0;
      if (flag === 0) continue;

      const x = chartWidth - (c - startCandle + 1) * zoom + zoom / 2;
      const hi = this.ohlcHigh[c];
      const lo = this.ohlcLow[c];
      if (hi === 0 && lo === 0) continue;

      if (flag === 2) {
        const y = this.priceToY(hi);
        ctx.fillStyle = COLOR_EXHAUSTION_BEAR;
        ctx.font = 'bold 10px monospace';
        ctx.fillText('E', x - 3, y - 4);
      } else if (flag === 1) {
        const y = this.priceToY(lo);
        ctx.fillStyle = COLOR_EXHAUSTION_BULL;
        ctx.font = 'bold 10px monospace';
        ctx.fillText('E', x - 3, y + 12);
      }
    }
  }

  _drawSweeps(ctx, startCandle, endCandle, chartWidth) {
    const { zoom } = this.viewState;
    const { priceMin, priceMax } = this.viewState;

    for (let c = startCandle; c < endCandle; c++) {
      const flag = this.sweepFlags[c] || 0;
      if (flag === 0) continue;

      const x = chartWidth - (c - startCandle + 1) * zoom;
      const hi = this.ohlcHigh[c];
      const lo = this.ohlcLow[c];
      if (hi === 0 && lo === 0) continue;

      const yTop = this.priceToY(hi);
      const yBot = this.priceToY(lo);
      ctx.fillStyle = flag === 1 ? COLOR_SWEEP_BUY : COLOR_SWEEP_SELL;
      ctx.fillRect(x + zoom / 2 - 2, yTop, 4, yBot - yTop);
    }
  }

  _drawOFTRatio(ctx, startCandle, endCandle, chartWidth) {
    const { zoom } = this.viewState;
    const { priceMin, priceMax } = this.viewState;
    const numLevels = Math.ceil((priceMax - priceMin) / this.tickSize);
    const rowHeight = Math.max(1, this.viewState.pixelsPerTick);
    const candleSpacing = 2;
    const candleWidth = zoom - candleSpacing;

    for (let c = startCandle; c < endCandle; c++) {
      const x = chartWidth - (c - startCandle + 1) * zoom + candleSpacing / 2;
      if (x + candleWidth < 0) continue;

      const gridOff = c * CANDLE_PRICE_LEVELS;
      const vpocPrice = this.vpoc[c] || 0;

      for (let p = 0; p < numLevels; p++) {
        const price = priceMin + p * this.tickSize;
        const y = this.priceToY(price);
        if (y < 0 || y > this.height) continue;

        const ts = this.tickSize;
        const localIdx = Math.round((price - vpocPrice) / ts) + Math.floor(CANDLE_PRICE_LEVELS / 2);
        if (localIdx < 0 || localIdx >= CANDLE_PRICE_LEVELS) continue;

        const flag = this.oftRatioMap[gridOff + localIdx];
        if (flag === 1) {
          ctx.fillStyle = COLOR_OFT_EXHAUSTION;
          ctx.fillRect(x, y - rowHeight / 2, candleWidth, rowHeight);
        } else if (flag === 2) {
          ctx.fillStyle = COLOR_OFT_DEFENSE;
          ctx.fillRect(x, y - rowHeight / 2, candleWidth, rowHeight);
        }
      }
    }
  }

  _drawPOCSlingshot(ctx, startCandle, endCandle, chartWidth) {
    const { zoom } = this.viewState;

    for (let c = startCandle; c < endCandle; c++) {
      const flag = this.oftSlingshotFlags[c] || 0;
      if (flag === 0) continue;

      const vpocPrice = this.vpoc[c] || 0;
      if (vpocPrice === 0) continue;

      const x = chartWidth - (c - startCandle + 1) * zoom + zoom / 2;
      const y = this.priceToY(vpocPrice);

      ctx.font = 'bold 10px monospace';
      ctx.fillStyle = flag === 1 ? COLOR_SLINGSHOT_BULL : COLOR_SLINGSHOT_BEAR;
      ctx.fillText('S', x - 3, y - 4);
    }
  }

  _drawMarketWeakness(ctx, startCandle, endCandle, chartWidth) {
    const { zoom } = this.viewState;

    for (let c = startCandle; c < endCandle; c++) {
      const flag = this.oftWeaknessFlags[c] || 0;
      if (flag === 0) continue;

      const x = chartWidth - (c - startCandle + 1) * zoom;
      const hi = this.ohlcHigh[c];
      const lo = this.ohlcLow[c];
      if (hi === 0 && lo === 0) continue;

      const y = flag === 1 ? this.priceToY(hi) : this.priceToY(lo);
      ctx.font = 'bold 10px monospace';
      ctx.fillStyle = flag === 1 ? COLOR_WEAKNESS_BUY : COLOR_WEAKNESS_SELL;
      ctx.fillText('W', x + 2, flag === 1 ? y - 4 : y + 12);
    }
  }

  _drawSequencing(ctx, startCandle, endCandle, chartWidth) {
    const { zoom } = this.viewState;

    for (let c = startCandle; c < endCandle; c++) {
      const flag = this.oftSequencingFlags[c] || 0;
      if (flag === 0) continue;

      const x = chartWidth - (c - startCandle + 1) * zoom;
      const hi = this.ohlcHigh[c];
      const lo = this.ohlcLow[c];
      if (hi === 0 && lo === 0) continue;

      const yTop = this.priceToY(hi);
      const yBot = this.priceToY(lo);
      ctx.fillStyle = flag === 1 ? COLOR_SEQUENCE_BUY : COLOR_SEQUENCE_SELL;
      ctx.fillRect(x, yTop, 4, yBot - yTop);
    }
  }

  resize(width, height) {
    this.width = width;
    this.height = height;
    this.canvas.width = width;
    this.canvas.height = height;
  }
}
