const COLOR_UP = '#26A69A';
const COLOR_DOWN = '#EF5350';
const WICK_WIDTH = 1;
const MIN_BODY_WIDTH = 2;

function priceToY(price, priceMin, priceMax, height) {
  return height - ((price - priceMin) / (priceMax - priceMin)) * height;
}

export function drawCandles(ctx, open, high, low, close, startCandle, endCandle, chartWidth, viewState, tickSize) {
  const { zoom, priceMin, priceMax } = viewState;
  const h = ctx.canvas.height || viewState.canvasHeight || 600;
  const candleSpacing = 2;
  const bodyWidth = Math.max(MIN_BODY_WIDTH, zoom - candleSpacing);

  for (let c = startCandle; c < endCandle; c++) {
    const o = open[c];
    const hi = high[c];
    const lo = low[c];
    const cl = close[c];
    if (o === 0 && cl === 0) continue;

    const isUp = cl >= o;
    const bodyColor = isUp ? COLOR_UP : COLOR_DOWN;
    const wickColor = isUp ? COLOR_UP : COLOR_DOWN;

    const x = chartWidth - (c - startCandle + 1) * zoom + candleSpacing / 2;
    if (x + bodyWidth < 0) continue;

    const yHigh = priceToY(hi, priceMin, priceMax, h);
    const yLow = priceToY(lo, priceMin, priceMax, h);
    const yOpen = priceToY(o, priceMin, priceMax, h);
    const yClose = priceToY(cl, priceMin, priceMax, h);

    const bodyTop = Math.min(yOpen, yClose);
    const bodyBottom = Math.max(yOpen, yClose);
    const bodyHeight = Math.max(1, bodyBottom - bodyTop);
    const centerX = x + bodyWidth / 2;

    ctx.strokeStyle = wickColor;
    ctx.lineWidth = WICK_WIDTH;
    ctx.beginPath();
    ctx.moveTo(centerX, yHigh);
    ctx.lineTo(centerX, yLow);
    ctx.stroke();

    ctx.fillStyle = bodyColor;
    if (!isUp) {
      ctx.fillRect(x, bodyTop, bodyWidth, bodyHeight);
    } else {
      ctx.fillRect(x, bodyTop, bodyWidth, bodyHeight);
    }
  }
}
