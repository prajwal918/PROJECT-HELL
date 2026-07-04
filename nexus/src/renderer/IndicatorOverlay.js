import TerminalConfig from '../config/TerminalConfig.js';

const COLOR_SMA = '#00BCD4';
const COLOR_EMA = '#FF9800';
const COLOR_BOLL_UPPER = '#2196F3';
const COLOR_BOLL_LOWER = '#2196F3';
const COLOR_BOLL_MIDDLE = '#2196F3';
const COLOR_BOLL_FILL = 'rgba(33,150,243,0.06)';
const COLOR_RSI = '#AB47BC';
const COLOR_RSI_OVERBOUGHT = 'rgba(239,83,80,0.3)';
const COLOR_RSI_OVERSOLD = 'rgba(38,166,154,0.3)';
const COLOR_MACD_LINE = '#2196F3';
const COLOR_MACD_SIGNAL = '#FF9800';
const COLOR_MACD_HIST_POS = '#26A69A';
const COLOR_MACD_HIST_NEG = '#EF5350';

function candleX(candleIdx, startCandle, endCandle, chartWidth, zoom) {
  return chartWidth - (candleIdx - startCandle + 1) * zoom + zoom / 2;
}

export function drawSMA(ctx, smaArr, startCandle, endCandle, chartWidth, viewState, color, priceToY) {
  _drawLineIndicator(ctx, smaArr, startCandle, endCandle, chartWidth, viewState, color || COLOR_SMA, priceToY);
}

export function drawEMA(ctx, emaArr, startCandle, endCandle, chartWidth, viewState, color, priceToY) {
  _drawLineIndicator(ctx, emaArr, startCandle, endCandle, chartWidth, viewState, color || COLOR_EMA, priceToY);
}

function _drawLineIndicator(ctx, arr, startCandle, endCandle, chartWidth, viewState, color, priceToY) {
  const { zoom } = viewState;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.setLineDash([]);
  ctx.beginPath();
  let started = false;

  for (let i = startCandle; i < endCandle; i++) {
    if (i >= arr.length || isNaN(arr[i])) continue;
    const x = candleX(i, startCandle, endCandle, chartWidth, zoom);
    const y = priceToY(arr[i]);
    if (!started) { ctx.moveTo(x, y); started = true; }
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.restore();
}

export function drawBollinger(ctx, upper, middle, lower, startCandle, endCandle, chartWidth, viewState, priceToY) {
  const { zoom } = viewState;
  ctx.save();

  ctx.beginPath();
  let started = false;
  const upperPoints = [];
  const lowerPoints = [];

  for (let i = startCandle; i < endCandle; i++) {
    if (i >= upper.length || isNaN(upper[i])) continue;
    const x = candleX(i, startCandle, endCandle, chartWidth, zoom);
    const yUp = priceToY(upper[i]);
    const yLo = priceToY(lower[i]);
    upperPoints.push({ x, y: yUp });
    lowerPoints.push({ x, y: yLo });
  }

  if (upperPoints.length > 1) {
    ctx.beginPath();
    ctx.moveTo(upperPoints[0].x, upperPoints[0].y);
    for (let i = 1; i < upperPoints.length; i++) ctx.lineTo(upperPoints[i].x, upperPoints[i].y);
    for (let i = lowerPoints.length - 1; i >= 0; i--) ctx.lineTo(lowerPoints[i].x, lowerPoints[i].y);
    ctx.closePath();
    ctx.fillStyle = COLOR_BOLL_FILL;
    ctx.fill();
  }

  _drawPoints(ctx, upperPoints, COLOR_BOLL_UPPER, 1);
  _drawPoints(ctx, lowerPoints, COLOR_BOLL_LOWER, 1);

  ctx.strokeStyle = COLOR_BOLL_MIDDLE;
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  started = false;
  for (let i = startCandle; i < endCandle; i++) {
    if (i >= middle.length || isNaN(middle[i])) continue;
    const x = candleX(i, startCandle, endCandle, chartWidth, zoom);
    const y = priceToY(middle[i]);
    if (!started) { ctx.moveTo(x, y); started = true; }
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();
}

function _drawPoints(ctx, points, color, width) {
  if (points.length < 2) return;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y);
  ctx.stroke();
  ctx.restore();
}

export function drawRSI(ctx, rsiArr, startCandle, endCandle, chartWidth, viewState, panelHeight) {
  const { zoom } = viewState;
  const h = panelHeight || 100;

  ctx.save();

  ctx.fillStyle = 'rgba(11,14,17,0.95)';
  ctx.fillRect(0, 0, chartWidth, h);

  ctx.strokeStyle = TerminalConfig.COLOR_BORDER;
  ctx.lineWidth = 0.5;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(chartWidth, 0);
  ctx.stroke();

  ctx.fillStyle = 'rgba(239,83,80,0.08)';
  ctx.fillRect(0, 0, chartWidth, h * 0.3);
  ctx.fillStyle = 'rgba(38,166,154,0.08)';
  ctx.fillRect(0, h * 0.7, chartWidth, h * 0.3);

  ctx.strokeStyle = COLOR_RSI_OVERBOUGHT;
  ctx.lineWidth = 0.5;
  ctx.setLineDash([2, 2]);
  ctx.beginPath();
  ctx.moveTo(0, h * 0.3);
  ctx.lineTo(chartWidth, h * 0.3);
  ctx.stroke();

  ctx.strokeStyle = COLOR_RSI_OVERSOLD;
  ctx.beginPath();
  ctx.moveTo(0, h * 0.7);
  ctx.lineTo(chartWidth, h * 0.7);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.font = '9px Courier New';
  ctx.fillStyle = TerminalConfig.COLOR_TEXT_MUTED;
  ctx.fillText('70', 4, h * 0.3 + 10);
  ctx.fillText('30', 4, h * 0.7 + 10);
  ctx.fillText('RSI', 4, 12);

  ctx.strokeStyle = COLOR_RSI;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  let started = false;
  for (let i = startCandle; i < endCandle; i++) {
    if (i >= rsiArr.length || isNaN(rsiArr[i])) continue;
    const x = candleX(i, startCandle, endCandle, chartWidth, zoom);
    const y = h - (rsiArr[i] / 100) * h;
    if (!started) { ctx.moveTo(x, y); started = true; }
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.restore();
}

export function drawMACD(ctx, macdLine, signalLine, histogram, startCandle, endCandle, chartWidth, viewState, panelHeight) {
  const { zoom } = viewState;
  const h = panelHeight || 100;

  ctx.save();

  ctx.fillStyle = 'rgba(11,14,17,0.95)';
  ctx.fillRect(0, 0, chartWidth, h);

  ctx.strokeStyle = TerminalConfig.COLOR_BORDER;
  ctx.lineWidth = 0.5;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(chartWidth, 0);
  ctx.stroke();

  let maxVal = 0;
  for (let i = startCandle; i < endCandle; i++) {
    if (i < histogram.length && !isNaN(histogram[i])) maxVal = Math.max(maxVal, Math.abs(histogram[i]));
    if (i < macdLine.length && !isNaN(macdLine[i])) maxVal = Math.max(maxVal, Math.abs(macdLine[i]));
    if (i < signalLine.length && !isNaN(signalLine[i])) maxVal = Math.max(maxVal, Math.abs(signalLine[i]));
  }
  maxVal = maxVal || 1;

  const midY = h / 2;
  const scale = (h / 2 - 8) / maxVal;

  ctx.strokeStyle = TerminalConfig.COLOR_BORDER;
  ctx.lineWidth = 0.5;
  ctx.setLineDash([2, 2]);
  ctx.beginPath();
  ctx.moveTo(0, midY);
  ctx.lineTo(chartWidth, midY);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.font = '9px Courier New';
  ctx.fillStyle = TerminalConfig.COLOR_TEXT_MUTED;
  ctx.fillText('MACD', 4, 12);
  ctx.fillText('0', 4, midY - 3);

  for (let i = startCandle; i < endCandle; i++) {
    if (i >= histogram.length || isNaN(histogram[i])) continue;
    const x = candleX(i, startCandle, endCandle, chartWidth, zoom);
    const barH = histogram[i] * scale;
    ctx.fillStyle = histogram[i] >= 0 ? COLOR_MACD_HIST_POS : COLOR_MACD_HIST_NEG;
    ctx.fillRect(x - zoom * 0.3, midY - Math.max(0, barH), zoom * 0.6, Math.abs(barH));
  }

  ctx.strokeStyle = COLOR_MACD_LINE;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  let started = false;
  for (let i = startCandle; i < endCandle; i++) {
    if (i >= macdLine.length || isNaN(macdLine[i])) continue;
    const x = candleX(i, startCandle, endCandle, chartWidth, zoom);
    const y = midY - macdLine[i] * scale;
    if (!started) { ctx.moveTo(x, y); started = true; }
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  ctx.strokeStyle = COLOR_MACD_SIGNAL;
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  started = false;
  for (let i = startCandle; i < endCandle; i++) {
    if (i >= signalLine.length || isNaN(signalLine[i])) continue;
    const x = candleX(i, startCandle, endCandle, chartWidth, zoom);
    const y = midY - signalLine[i] * scale;
    if (!started) { ctx.moveTo(x, y); started = true; }
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();
}
