import { useRef, useEffect } from 'react';
import TerminalConfig from '../config/TerminalConfig.js';

const C = TerminalConfig;
const MAX_CANDLES = 8192;
const FEATURE_CVD_OFFSET = 256;
const FEATURE_DELTA_OFFSET = 256 + 8 * 8192;
const FEATURE_CANDLE_COUNT = 12;
const FEATURE_DIVERGENCE_OFFSET = 256 + 8 * 8192 * 2 + 4 * 4096 + 1 * 4096 + 8 * 8192 + 8 * 4096 + 4 * 4096 * 96 + 4 * 65536 + 1 * 4096 + 8 * 216000 * 2 + 8 * 8192 * 3;

export default function CVDOscillator({ featureSAB }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!featureSAB) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const featureHeader = new Int32Array(featureSAB, 0, 256 / 4);
    const cvdArr = new Float64Array(featureSAB, FEATURE_CVD_OFFSET, MAX_CANDLES);
    const deltaArr = new Float64Array(featureSAB, FEATURE_DELTA_OFFSET, MAX_CANDLES);
    let divArr;
    try {
      divArr = new Uint8Array(featureSAB, FEATURE_DIVERGENCE_OFFSET, MAX_CANDLES);
    } catch (e) {
      divArr = new Uint8Array(MAX_CANDLES);
    }

    const render = () => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const w = Math.floor(rect.width);
      const h = Math.floor(rect.height);
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }

      ctx.fillStyle = C.BG_PRIMARY;
      ctx.fillRect(0, 0, w, h);

      ctx.strokeStyle = '#1E222D';
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(w, 0);
      ctx.stroke();

      const candleCount = featureHeader[FEATURE_CANDLE_COUNT / 4] || 0;
      if (candleCount < 2) return;

      const visibleCount = Math.min(candleCount, Math.floor(w / 3));
      const startIdx = Math.max(0, candleCount - visibleCount);

      let minCVD = Infinity, maxCVD = -Infinity;
      for (let i = startIdx; i < candleCount; i++) {
        const v = cvdArr[i];
        if (v < minCVD) minCVD = v;
        if (v > maxCVD) maxCVD = v;
      }
      const range = Math.max(maxCVD - minCVD, 1);

      const midY = h / 2;
      const zeroY = midY - ((0 - minCVD) / range) * (h - 4) + 2;

      ctx.strokeStyle = '#1E222D';
      ctx.lineWidth = 0.5;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(0, zeroY);
      ctx.lineTo(w, zeroY);
      ctx.stroke();
      ctx.setLineDash([]);

      const barW = Math.max(1, w / visibleCount - 1);
      for (let i = startIdx; i < candleCount; i++) {
        const x = ((i - startIdx) / visibleCount) * w;
        const delta = deltaArr[i];
        const maxDelta = range * 0.5;
        const barH = Math.min((Math.abs(delta) / Math.max(maxDelta, 1)) * (h * 0.4), h * 0.45);
        const barY = delta >= 0 ? midY - barH : midY;

        const div = divArr[i] || 0;
        if (div === 1) {
          ctx.fillStyle = 'rgba(38,166,154,0.35)';
          ctx.fillRect(x - 1, 0, barW + 2, h);
        } else if (div === 2) {
          ctx.fillStyle = 'rgba(239,83,80,0.35)';
          ctx.fillRect(x - 1, 0, barW + 2, h);
        }

        ctx.fillStyle = delta >= 0 ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)';
        ctx.fillRect(x, barY, barW, barH);
      }

      ctx.strokeStyle = C.BULLISH;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let firstPoint = true;
      for (let i = startIdx; i < candleCount; i++) {
        const x = ((i - startIdx) / visibleCount) * w;
        const cvd = cvdArr[i];
        const y = h - ((cvd - minCVD) / range) * (h - 4) - 2;
        if (firstPoint) { ctx.moveTo(x, y); firstPoint = false; }
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      ctx.font = 'bold 10px Courier New';
      ctx.fillStyle = C.BULLISH;
      ctx.fillText(`CVD ${(cvdArr[candleCount - 1] || 0).toFixed(0)}`, 4, 14);
      ctx.fillStyle = deltaArr[candleCount - 1] >= 0 ? C.BULLISH : C.BEARISH;
      ctx.fillText(`\u0394 ${(deltaArr[candleCount - 1] || 0).toFixed(0)}`, 4, 28);

      const lastDiv = divArr[candleCount - 1] || 0;
      if (lastDiv === 1) {
        ctx.fillStyle = C.BULLISH;
        ctx.fillText('BULL DIV', 80, 14);
      } else if (lastDiv === 2) {
        ctx.fillStyle = C.BEARISH;
        ctx.fillText('BEAR DIV', 80, 14);
      }
    };

    const interval = setInterval(render, 100);
    return () => clearInterval(interval);
  }, [featureSAB]);

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
      <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block', background: C.BG_PRIMARY }} />
    </div>
  );
}
