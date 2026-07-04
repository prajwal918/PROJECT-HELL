import TerminalConfig from '../config/TerminalConfig.js';

const MAX_BARS = 512;

export class VolumeBarOverlay {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.bars = new Array(MAX_BARS);
    for (let i = 0; i < MAX_BARS; i++) {
      this.bars[i] = { buyVol: 0, sellVol: 0, totalVol: 0 };
    }
    this.barIndex = 0;
    this.maxVolume = 1;
    this.width = canvas.width;
    this.height = canvas.height;
    this.viewState = { priceMin: 4490, priceMax: 4510 };
  }

  resetCurrentBar() {
    const idx = this.barIndex % MAX_BARS;
    this.bars[idx] = { buyVol: 0, sellVol: 0, totalVol: 0 };
  }

  addTrade(side, size) {
    const idx = this.barIndex % MAX_BARS;
    const bar = this.bars[idx];
    if (side === 'ASK' || side === 1) {
      bar.buyVol += size;
    } else {
      bar.sellVol += size;
    }
    bar.totalVol += size;
    if (bar.totalVol > this.maxVolume) {
      this.maxVolume = bar.totalVol;
    }
  }

  advanceBar() {
    this.barIndex++;
    this.resetCurrentBar();
  }

  updateViewState(vs) {
    this.viewState = { ...this.viewState, ...vs };
  }

  resize(width, height) {
    this.width = width;
    this.height = height;
    this.canvas.width = width;
    this.canvas.height = height;
  }

  render() {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    if (w === 0 || h === 0) return;

    ctx.fillStyle = 'rgba(11, 14, 17, 0.85)';
    ctx.fillRect(0, 0, w, h);

    const currentIdx = this.barIndex % MAX_BARS;
    const barCount = Math.min(this.barIndex, MAX_BARS);
    if (barCount === 0) return;

    const barWidth = Math.max(1, w / barCount);
    let globalMax = 1;
    for (let i = 0; i < barCount; i++) {
      const bar = this.bars[(currentIdx - barCount + i + MAX_BARS) % MAX_BARS];
      if (bar && bar.totalVol > globalMax) globalMax = bar.totalVol;
    }

    for (let i = 0; i < barCount; i++) {
      const bar = this.bars[(currentIdx - barCount + i + MAX_BARS) % MAX_BARS];
      if (!bar || bar.totalVol === 0) continue;

      const x = i * barWidth;
      const barH = (bar.totalVol / globalMax) * (h - 4);
      const aggressorRatio = bar.buyVol / Math.max(bar.totalVol, 1);

      const grad = ctx.createLinearGradient(x, h - barH, x, h);
      grad.addColorStop(0, `rgba(38, 166, 154, ${aggressorRatio})`);
      grad.addColorStop(1, `rgba(239, 83, 80, ${1 - aggressorRatio})`);
      ctx.fillStyle = grad;
      ctx.fillRect(x, h - barH, Math.max(1, barWidth - 1), barH);
    }

    ctx.strokeStyle = '#1E222D';
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(w, 0);
    ctx.stroke();

    ctx.font = '9px Courier New';
    ctx.fillStyle = '#787B86';
    ctx.fillText('VOL', 4, 12);
  }
}
