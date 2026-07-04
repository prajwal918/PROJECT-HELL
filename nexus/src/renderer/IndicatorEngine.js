export function sma(data, period) {
  const out = new Float64Array(data.length);
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    sum += data[i];
    if (i >= period) {
      sum -= data[i - period];
      out[i] = sum / period;
    } else if (i === period - 1) {
      out[i] = sum / period;
    } else {
      out[i] = NaN;
    }
  }
  return { name: `SMA(${period})`, data: out };
}

export function ema(data, period) {
  const out = new Float64Array(data.length);
  const k = 2 / (period + 1);
  let prev = NaN;

  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      out[i] = NaN;
    } else if (i === period - 1) {
      let sum = 0;
      for (let j = 0; j < period; j++) sum += data[j];
      prev = sum / period;
      out[i] = prev;
    } else {
      prev = data[i] * k + prev * (1 - k);
      out[i] = prev;
    }
  }
  return { name: `EMA(${period})`, data: out };
}

export function rsi(closes, period = 14) {
  const out = new Float64Array(closes.length);
  let avgGain = 0;
  let avgLoss = 0;

  for (let i = 1; i <= period && i < closes.length; i++) {
    const change = closes[i] - closes[i - 1];
    if (change > 0) avgGain += change;
    else avgLoss += Math.abs(change);
  }
  avgGain /= period;
  avgLoss /= period;

  if (period < closes.length) {
    out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }

  for (let i = period + 1; i < closes.length; i++) {
    const change = closes[i] - closes[i - 1];
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? Math.abs(change) : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }

  for (let i = 0; i < Math.min(period, closes.length); i++) {
    out[i] = NaN;
  }

  return { name: `RSI(${period})`, data: out };
}

export function macd(closes, fast = 12, slow = 26, signal = 9) {
  const emaFast = ema(closes, fast);
  const emaSlow = ema(closes, slow);

  const macdLine = new Float64Array(closes.length);
  for (let i = 0; i < closes.length; i++) {
    if (isNaN(emaFast.data[i]) || isNaN(emaSlow.data[i])) {
      macdLine[i] = NaN;
    } else {
      macdLine[i] = emaFast.data[i] - emaSlow.data[i];
    }
  }

  const signalLine = new Float64Array(closes.length);
  let validStart = -1;
  for (let i = 0; i < closes.length; i++) {
    if (!isNaN(macdLine[i])) {
      validStart = i;
      break;
    }
  }

  if (validStart >= 0) {
    const k = 2 / (signal + 1);
    let sum = 0;
    let count = 0;
    for (let i = validStart; i < closes.length && count < signal; i++) {
      if (!isNaN(macdLine[i])) {
        sum += macdLine[i];
        count++;
      }
    }
    if (count === signal) {
      let prev = sum / signal;
      signalLine[validStart + signal - 1] = prev;
      for (let i = validStart + signal; i < closes.length; i++) {
        if (!isNaN(macdLine[i])) {
          prev = macdLine[i] * k + prev * (1 - k);
          signalLine[i] = prev;
        }
      }
    }
  }

  const histogram = new Float64Array(closes.length);
  for (let i = 0; i < closes.length; i++) {
    if (isNaN(macdLine[i]) || isNaN(signalLine[i])) {
      histogram[i] = NaN;
    } else {
      histogram[i] = macdLine[i] - signalLine[i];
    }
  }

  return {
    name: `MACD(${fast},${slow},${signal})`,
    macdLine,
    signalLine,
    histogram,
  };
}

export function bollinger(closes, period = 20, stdDev = 2) {
  const middle = sma(closes, period);
  const upper = new Float64Array(closes.length);
  const lower = new Float64Array(closes.length);

  for (let i = period - 1; i < closes.length; i++) {
    let sumSq = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const diff = closes[j] - middle.data[i];
      sumSq += diff * diff;
    }
    const std = Math.sqrt(sumSq / period);
    upper[i] = middle.data[i] + stdDev * std;
    lower[i] = middle.data[i] - stdDev * std;
  }

  return {
    name: `BOLL(${period},${stdDev})`,
    upper,
    middle: middle.data,
    lower,
  };
}

export function atr(highs, lows, closes, period = 14) {
  const out = new Float64Array(highs.length);
  const tr = new Float64Array(highs.length);

  tr[0] = highs[0] - lows[0];
  for (let i = 1; i < highs.length; i++) {
    const hl = highs[i] - lows[i];
    const hc = Math.abs(highs[i] - closes[i - 1]);
    const lc = Math.abs(lows[i] - closes[i - 1]);
    tr[i] = Math.max(hl, hc, lc);
  }

  let sum = 0;
  for (let i = 0; i < period && i < tr.length; i++) {
    sum += tr[i];
  }

  if (period <= tr.length) {
    out[period - 1] = sum / period;
    for (let i = period; i < tr.length; i++) {
      out[i] = (out[i - 1] * (period - 1) + tr[i]) / period;
    }
  }

  return { name: `ATR(${period})`, data: out };
}

export function vwap(highs, lows, closes, volumes) {
  const out = new Float64Array(highs.length);
  let cumVol = 0;
  let cumTPV = 0;

  for (let i = 0; i < highs.length; i++) {
    const tp = (highs[i] + lows[i] + closes[i]) / 3;
    cumTPV += tp * volumes[i];
    cumVol += volumes[i];
    out[i] = cumVol > 0 ? cumTPV / cumVol : NaN;
  }

  return { name: 'VWAP', data: out };
}
