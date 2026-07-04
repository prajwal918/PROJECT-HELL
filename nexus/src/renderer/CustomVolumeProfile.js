import { MAX_PRICE_LEVELS } from '../types/MemoryLayout.js';
import TerminalConfig from '../config/TerminalConfig.js';

const COLOR_CUSTOM_BAR = 'rgba(242, 177, 56, 0.45)';
const COLOR_CUSTOM_VA = 'rgba(242, 177, 56, 0.15)';
const COLOR_CUSTOM_POC = '#F2B138';
const COLOR_CUSTOM_VAH = 'rgba(242, 177, 56, 0.6)';
const COLOR_CUSTOM_VAL = 'rgba(242, 177, 56, 0.6)';
const COLOR_PREVIEW = 'rgba(242, 177, 56, 0.12)';
const COLOR_PREVIEW_BORDER = 'rgba(242, 177, 56, 0.5)';

const MAX_CUSTOM_PROFILES = 5;

export class CustomVolumeProfile {
  constructor() {
    this.profiles = [];
    this.isDragging = false;
    this.dragStartPrice = 0;
    this.dragEndPrice = 0;
    this.previewActive = false;
  }

  startDrag(price) {
    if (this.profiles.length >= MAX_CUSTOM_PROFILES) return false;
    this.isDragging = true;
    this.dragStartPrice = price;
    this.dragEndPrice = price;
    this.previewActive = true;
    return true;
  }

  updateDrag(price) {
    if (!this.isDragging) return;
    this.dragEndPrice = price;
  }

  endDrag(volumeProfileData, tickSize) {
    if (!this.isDragging) return null;
    this.isDragging = false;
    this.previewActive = false;

    const lo = Math.min(this.dragStartPrice, this.dragEndPrice);
    const hi = Math.max(this.dragStartPrice, this.dragEndPrice);

    if (hi - lo < tickSize) return null;

    const profile = this._computeProfile(lo, hi, volumeProfileData, tickSize);
    this.profiles.push(profile);
    return profile;
  }

  cancelDrag() {
    this.isDragging = false;
    this.previewActive = false;
  }

  removeProfile(index) {
    if (index >= 0 && index < this.profiles.length) {
      this.profiles.splice(index, 1);
      return true;
    }
    return false;
  }

  getProfileAtPrice(price, tickSize) {
    for (let i = this.profiles.length - 1; i >= 0; i--) {
      const p = this.profiles[i];
      if (price >= p.startPrice - tickSize && price <= p.endPrice + tickSize) {
        return i;
      }
    }
    return -1;
  }

  _computeProfile(startPrice, endPrice, volumeProfileData, tickSize) {
    const lo = Math.min(startPrice, endPrice);
    const hi = Math.max(startPrice, endPrice);
    const bars = [];
    let maxVol = 0;
    let totalVol = 0;
    let pocPrice = lo;

    for (let price = lo; price <= hi; price += tickSize) {
      const pIdx = Math.floor(price * 1000);
      if (pIdx < 0 || pIdx >= MAX_PRICE_LEVELS) continue;
      const vol = volumeProfileData[pIdx] || 0;
      bars.push({ price, volume: vol });
      if (vol > maxVol) {
        maxVol = vol;
        pocPrice = price;
      }
      totalVol += vol;
    }

    const vaTarget = totalVol * TerminalConfig.VALUE_AREA_PERCENT;
    let vaCount = 0;
    let vah = pocPrice;
    let val = pocPrice;
    let goUp = true, goDown = true;
    let upIdx = 1, downIdx = 1;

    while (vaCount < vaTarget && (goUp || goDown)) {
      const priceUp = pocPrice + upIdx * tickSize;
      const priceDown = pocPrice - downIdx * tickSize;
      const idxUp = Math.floor(priceUp * 1000);
      const idxDown = Math.floor(priceDown * 1000);
      let volUp = 0, volDown = 0;
      if (idxUp >= 0 && idxUp < MAX_PRICE_LEVELS && goUp && priceUp <= hi) {
        volUp = volumeProfileData[idxUp] || 0;
      } else {
        goUp = false;
      }
      if (idxDown >= 0 && idxDown < MAX_PRICE_LEVELS && goDown && priceDown >= lo) {
        volDown = volumeProfileData[idxDown] || 0;
      } else {
        goDown = false;
      }
      if (volUp >= volDown && goUp) {
        vah = priceUp;
        vaCount += volUp;
        upIdx++;
      } else if (goDown) {
        val = priceDown;
        vaCount += volDown;
        downIdx++;
      } else {
        break;
      }
    }

    return { startPrice: lo, endPrice: hi, pocPrice, vah, val, bars, maxVol, totalVol };
  }

  render(ctx, priceToY, chartWidth, profileWidth, pixelsPerTick) {
    const profileX = chartWidth;

    for (let pi = 0; pi < this.profiles.length; pi++) {
      const prof = this.profiles[pi];
      if (prof.maxVol === 0) continue;

      const offsetX = profileX + pi * 16;

      for (const bar of prof.bars) {
        if (bar.volume === 0) continue;
        const y = priceToY(bar.price);
        const rowHeight = Math.max(1, pixelsPerTick);
        const barWidth = (bar.volume / prof.maxVol) * (profileWidth - 4);
        const inVA = bar.price >= prof.val && bar.price <= prof.vah;
        ctx.fillStyle = inVA ? COLOR_CUSTOM_VA : COLOR_CUSTOM_BAR;
        ctx.fillRect(offsetX + 2, y - rowHeight / 2, barWidth, rowHeight);
      }

      const pocY = priceToY(prof.pocPrice);
      ctx.strokeStyle = COLOR_CUSTOM_POC;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(offsetX, pocY);
      ctx.lineTo(offsetX + profileWidth, pocY);
      ctx.stroke();

      ctx.strokeStyle = COLOR_CUSTOM_POC;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(0, pocY);
      ctx.lineTo(chartWidth, pocY);
      ctx.stroke();

      ctx.strokeStyle = COLOR_CUSTOM_VAH;
      ctx.beginPath();
      ctx.moveTo(offsetX, priceToY(prof.vah));
      ctx.lineTo(offsetX + profileWidth, priceToY(prof.vah));
      ctx.stroke();

      ctx.strokeStyle = COLOR_CUSTOM_VAH;
      ctx.beginPath();
      ctx.moveTo(0, priceToY(prof.vah));
      ctx.lineTo(chartWidth, priceToY(prof.vah));
      ctx.stroke();

      ctx.strokeStyle = COLOR_CUSTOM_VAL;
      ctx.beginPath();
      ctx.moveTo(offsetX, priceToY(prof.val));
      ctx.lineTo(offsetX + profileWidth, priceToY(prof.val));
      ctx.stroke();

      ctx.strokeStyle = COLOR_CUSTOM_VAL;
      ctx.beginPath();
      ctx.moveTo(0, priceToY(prof.val));
      ctx.lineTo(chartWidth, priceToY(prof.val));
      ctx.stroke();

      ctx.setLineDash([]);

      ctx.font = '9px monospace';
      ctx.fillStyle = COLOR_CUSTOM_POC;
      ctx.fillText(`C${pi + 1}`, offsetX + 2, priceToY(prof.endPrice) - 4);
    }

    if (this.previewActive) {
      const lo = Math.min(this.dragStartPrice, this.dragEndPrice);
      const hi = Math.max(this.dragStartPrice, this.dragEndPrice);
      const yTop = priceToY(hi);
      const yBot = priceToY(lo);

      ctx.fillStyle = COLOR_PREVIEW;
      ctx.fillRect(0, yTop, chartWidth, yBot - yTop);

      ctx.strokeStyle = COLOR_PREVIEW_BORDER;
      ctx.lineWidth = 1;
      ctx.setLineDash([6, 3]);
      ctx.strokeRect(0, yTop, chartWidth, yBot - yTop);
      ctx.setLineDash([]);

      ctx.font = '10px monospace';
      ctx.fillStyle = COLOR_CUSTOM_POC;
      ctx.fillText(`Custom: ${lo.toFixed(2)} - ${hi.toFixed(2)}`, 4, yTop - 4);
    }
  }
}
