import TerminalConfig from '../config/TerminalConfig.js';

export class CrosshairOverlay {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.mouseX = -1;
    this.mouseY = -1;
    this.visible = false;
    this.width = canvas.width;
    this.height = canvas.height;
    this.viewState = { priceMin: 4490, priceMax: 4510 };
  }

  setMousePosition(x, y) {
    this.mouseX = x;
    this.mouseY = y;
    this.visible = x >= 0 && y >= 0;
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

  yToPrice(y) {
    const { priceMin, priceMax } = this.viewState;
    return priceMin + ((this.height - y) / this.height) * (priceMax - priceMin);
  }

  xToTime(x) {
    const now = Date.now();
    const msPerPixel = 500;
    return new Date(now - (this.width - x) * msPerPixel);
  }

  formatPrice(price) {
    if (price >= 1000) return price.toFixed(2);
    if (price >= 100) return price.toFixed(2);
    return price.toFixed(4);
  }

  formatTime(date) {
    const h = String(date.getHours()).padStart(2, '0');
    const m = String(date.getMinutes()).padStart(2, '0');
    const s = String(date.getSeconds()).padStart(2, '0');
    return `${h}:${m}:${s}`;
  }

  render() {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    if (w === 0 || h === 0) return;

    ctx.clearRect(0, 0, w, h);

    if (!this.visible || this.mouseX < 0 || this.mouseY < 0) return;

    const mx = this.mouseX;
    const my = this.mouseY;

    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
    ctx.lineWidth = 1;

    ctx.beginPath();
    ctx.moveTo(0, my);
    ctx.lineTo(w, my);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(mx, 0);
    ctx.lineTo(mx, h);
    ctx.stroke();

    ctx.setLineDash([]);

    const price = this.yToPrice(my);
    const priceLabel = this.formatPrice(price);

    ctx.font = 'bold 10px Courier New';
    const priceTextWidth = ctx.measureText(priceLabel).width + 8;
    ctx.fillStyle = 'rgba(11, 14, 17, 0.90)';
    ctx.fillRect(0, my - 9, priceTextWidth, 18);
    ctx.strokeStyle = '#1E222D';
    ctx.lineWidth = 1;
    ctx.strokeRect(0, my - 9, priceTextWidth, 18);
    ctx.fillStyle = '#E1E4E8';
    ctx.fillText(priceLabel, 4, my + 4);

    const timeDate = this.xToTime(mx);
    const timeLabel = this.formatTime(timeDate);

    const timeTextWidth = ctx.measureText(timeLabel).width + 8;
    ctx.fillStyle = 'rgba(11, 14, 17, 0.90)';
    ctx.fillRect(mx - timeTextWidth / 2, h - 18, timeTextWidth, 18);
    ctx.strokeStyle = '#1E222D';
    ctx.strokeRect(mx - timeTextWidth / 2, h - 18, timeTextWidth, 18);
    ctx.fillStyle = '#E1E4E8';
    ctx.textAlign = 'center';
    ctx.fillText(timeLabel, mx, h - 5);
    ctx.textAlign = 'left';
  }
}
