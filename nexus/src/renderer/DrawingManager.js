import TerminalConfig from '../config/TerminalConfig.js';

const STORAGE_KEY = 'nexus_drawings';
const HIT_TOLERANCE = 6;

const FIB_LEVELS = [0, 23.6, 38.2, 50, 61.8, 78.6, 100];

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

function saveToStorage(drawings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(drawings));
  } catch {}
}

export class DrawingManager {
  constructor() {
    this.drawings = loadFromStorage();
    this.onAddColor = '#F2C94C';
  }

  addDrawing(type, points, color) {
    const drawing = {
      id: generateId(),
      type,
      points,
      color: color || this.onAddColor,
    };
    this.drawings.push(drawing);
    saveToStorage(this.drawings);
    return drawing;
  }

  removeDrawing(id) {
    this.drawings = this.drawings.filter(d => d.id !== id);
    saveToStorage(this.drawings);
  }

  getDrawings() {
    return this.drawings;
  }

  clearAll() {
    this.drawings = [];
    saveToStorage(this.drawings);
  }

  hitTest(x, y) {
    for (let i = this.drawings.length - 1; i >= 0; i--) {
      const d = this.drawings[i];
      if (d.type === 'horizontal_line') {
        if (Math.abs(y - d.points[0].y) < HIT_TOLERANCE) return d;
      } else if (d.type === 'trend_line' || d.type === 'ray') {
        const p0 = d.points[0];
        const p1 = d.points[1];
        if (!p0 || !p1) continue;
        const dx = p1.x - p0.x;
        const dy = p1.y - p0.y;
        const len2 = dx * dx + dy * dy;
        if (len2 === 0) continue;
        const t = Math.max(0, Math.min(1, ((x - p0.x) * dx + (y - p0.y) * dy) / len2));
        const px = p0.x + t * dx;
        const py = p0.y + t * dy;
        const dist = Math.sqrt((x - px) * (x - px) + (y - py) * (y - py));
        if (dist < HIT_TOLERANCE) return d;
      } else if (d.type === 'fibonacci_retracement') {
        if (Math.abs(y - d.points[0].y) < HIT_TOLERANCE || Math.abs(y - d.points[1].y) < HIT_TOLERANCE) return d;
        const priceRange = d.points[1].price - d.points[0].price;
        for (const level of FIB_LEVELS) {
          const levelPrice = d.points[0].price + priceRange * (level / 100);
          const levelY = d.points[0].y + (d.points[1].y - d.points[0].y) * (level / 100);
          if (Math.abs(y - levelY) < HIT_TOLERANCE) return d;
        }
      }
    }
    return null;
  }

  drawAll(ctx, viewState, chartWidth, height, priceToY, yToPrice) {
    for (const d of this.drawings) {
      ctx.save();
      ctx.strokeStyle = d.color;
      ctx.fillStyle = d.color;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([]);

      if (d.type === 'horizontal_line') {
        const price = d.points[0].price;
        const y = priceToY(price);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(chartWidth, y);
        ctx.stroke();
        ctx.font = 'bold 10px Courier New';
        const label = price.toFixed(2);
        const tw = ctx.measureText(label).width + 8;
        ctx.fillStyle = 'rgba(11,14,17,0.85)';
        ctx.fillRect(chartWidth - tw - 4, y - 9, tw, 18);
        ctx.fillStyle = d.color;
        ctx.fillText(label, chartWidth - tw, y + 4);
      } else if (d.type === 'trend_line') {
        const p0 = d.points[0];
        const p1 = d.points[1];
        const y0 = priceToY(p0.price);
        const y1 = priceToY(p1.price);
        const x0 = p0.x;
        const x1 = p1.x;
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(x1, y1);
        ctx.stroke();
      } else if (d.type === 'ray') {
        const p0 = d.points[0];
        const p1 = d.points[1];
        const y0 = priceToY(p0.price);
        const y1 = priceToY(p1.price);
        const x0 = p0.x;
        const x1 = p1.x;
        const dx = x1 - x0;
        const dy = y1 - y0;
        if (dx !== 0) {
          const t = (chartWidth - x0) / dx;
          const endY = y0 + t * dy;
          ctx.beginPath();
          ctx.moveTo(x0, y0);
          ctx.lineTo(chartWidth, endY);
          ctx.stroke();
          const arrowX = chartWidth - 8;
          const arrowT = (arrowX - x0) / dx;
          const arrowY = y0 + arrowT * dy;
          ctx.beginPath();
          ctx.moveTo(chartWidth, endY);
          ctx.lineTo(arrowX, arrowY - 4);
          ctx.lineTo(arrowX, arrowY + 4);
          ctx.closePath();
          ctx.fill();
        } else {
          ctx.beginPath();
          ctx.moveTo(x0, y0);
          ctx.lineTo(x0, y1);
          ctx.stroke();
        }
      } else if (d.type === 'fibonacci_retracement') {
        const price0 = d.points[0].price;
        const price1 = d.points[1].price;
        const priceRange = price1 - price0;
        ctx.font = '10px Courier New';
        for (const level of FIB_LEVELS) {
          const levelPrice = price0 + priceRange * (level / 100);
          const y = priceToY(levelPrice);
          if (y < 0 || y > height) continue;
          ctx.setLineDash(level === 0 || level === 100 ? [] : [4, 4]);
          ctx.globalAlpha = level === 50 ? 0.8 : 0.5;
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(chartWidth, y);
          ctx.stroke();
          ctx.globalAlpha = 1;
          const label = `${level}% — ${levelPrice.toFixed(2)}`;
          ctx.fillStyle = d.color;
          ctx.fillText(label, 4, y - 4);
        }
        ctx.setLineDash([]);
      }
      ctx.restore();
    }
  }
}
