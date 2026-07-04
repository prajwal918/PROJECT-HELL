import TerminalConfig from '../config/TerminalConfig.js';

const STORAGE_KEY = 'nexus_alerts';

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
}

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveToStorage(alerts) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
  } catch {}
}

export class AlertManager {
  constructor(onTrigger) {
    this.alerts = loadFromStorage();
    this.onTrigger = onTrigger || null;
    this._pulsePhase = 0;
  }

  addAlert(price, direction) {
    const alert = {
      id: generateId(),
      price,
      direction,
      triggered: false,
      createdAt: Date.now(),
    };
    this.alerts.push(alert);
    saveToStorage(this.alerts);
    return alert;
  }

  removeAlert(id) {
    this.alerts = this.alerts.filter(a => a.id !== id);
    saveToStorage(this.alerts);
  }

  getAlerts() {
    return this.alerts;
  }

  checkAlerts(currentPrice) {
    for (const alert of this.alerts) {
      if (alert.triggered) continue;
      let triggered = false;
      if (alert.direction === 'above' && currentPrice >= alert.price) triggered = true;
      else if (alert.direction === 'below' && currentPrice <= alert.price) triggered = true;
      else if (alert.direction === 'cross' && Math.abs(currentPrice - alert.price) < 0.01) triggered = true;

      if (triggered) {
        alert.triggered = true;
        alert.triggeredAt = Date.now();
        saveToStorage(this.alerts);
        if (this.onTrigger) this.onTrigger(alert);
      }
    }
  }

  drawAlerts(ctx, viewState, chartWidth, priceToY) {
    this._pulsePhase += 0.05;
    const pulse = 0.5 + 0.5 * Math.sin(this._pulsePhase);

    for (const alert of this.alerts) {
      const y = priceToY(alert.price);
      if (y < -20 || y > ctx.canvas.height + 20) continue;

      ctx.save();

      if (alert.triggered) {
        ctx.strokeStyle = '#F2C94C';
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(chartWidth, y);
        ctx.stroke();

        ctx.globalAlpha = 0.3 + 0.3 * pulse;
        ctx.strokeStyle = '#F2C94C';
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(chartWidth, y);
        ctx.stroke();
        ctx.globalAlpha = 1;
      } else {
        ctx.strokeStyle = alert.direction === 'above' ? TerminalConfig.BULLISH : alert.direction === 'below' ? TerminalConfig.BEARISH : '#F2C94C';
        ctx.lineWidth = 1;
        ctx.setLineDash([6, 4]);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(chartWidth, y);
        ctx.stroke();
      }

      ctx.setLineDash([]);
      ctx.font = '10px Courier New';
      const dirSymbol = alert.direction === 'above' ? '\u2191' : alert.direction === 'below' ? '\u2193' : '\u2195';
      const bellIcon = '\uD83D\uDD14';
      const label = `${bellIcon} ${dirSymbol} ${alert.price.toFixed(2)}`;
      const tw = ctx.measureText(label).width + 12;

      ctx.fillStyle = alert.triggered ? 'rgba(242,201,76,0.18)' : 'rgba(11,14,17,0.88)';
      ctx.fillRect(4, y - 10, tw, 20);
      ctx.fillStyle = alert.triggered ? '#F2C94C' : TerminalConfig.COLOR_TEXT_PRIMARY;
      ctx.fillText(label, 8, y + 4);

      ctx.restore();
    }
  }

  clearTriggered() {
    this.alerts = this.alerts.filter(a => !a.triggered);
    saveToStorage(this.alerts);
  }
}
