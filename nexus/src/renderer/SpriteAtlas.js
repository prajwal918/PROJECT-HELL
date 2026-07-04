const ATLAS_WIDTH = 512;
const ATLAS_HEIGHT = 512;
const GLYPH_SIZE_12 = 12;
const GLYPH_SIZE_16 = 16;
const PADDING = 2;

const CHARS = '0123456789KMB.+-:,▲▼●';
const GLYPH_SIZES = [GLYPH_SIZE_12, GLYPH_SIZE_16];

let atlasCanvas = null;
let atlasCtx = null;
let glyphLookup = {};
let initialized = false;

let tintCanvas = null;
let tintCtx = null;

export function initSpriteAtlas() {
  if (initialized) return atlasCanvas;

  atlasCanvas = new OffscreenCanvas(ATLAS_WIDTH, ATLAS_HEIGHT);
  atlasCtx = atlasCanvas.getContext('2d');

  atlasCtx.fillStyle = '#000000';
  atlasCtx.fillRect(0, 0, ATLAS_WIDTH, ATLAS_HEIGHT);

  atlasCtx.textBaseline = 'top';

  let currentX = PADDING;
  let currentY = PADDING;

  for (let s = 0; s < GLYPH_SIZES.length; s++) {
    const size = GLYPH_SIZES[s];
    const fontStr = `bold ${size}px "Courier New", monospace`;
    atlasCtx.font = fontStr;

    for (let c = 0; c < CHARS.length; c++) {
      const char = CHARS[c];
      const metrics = atlasCtx.measureText(char);
      const charWidth = Math.ceil(metrics.width) + PADDING;
      const charHeight = size + PADDING;

      if (currentX + charWidth > ATLAS_WIDTH) {
        currentX = PADDING;
        currentY += charHeight + PADDING;
      }

      atlasCtx.fillStyle = '#ffffff';
      atlasCtx.font = fontStr;
      atlasCtx.fillText(char, currentX, currentY);

      const key = `${char}_${size}`;
      glyphLookup[key] = {
        sx: currentX,
        sy: currentY,
        sw: charWidth,
        sh: charHeight,
      };

      currentX += charWidth + PADDING;
    }

    currentX = PADDING;
    currentY += size + PADDING * 2;
  }

  const tileSizes = [
    { suffix: '12', height: GLYPH_SIZE_12, width: 6 },
    { suffix: '16', height: GLYPH_SIZE_16, width: 8 },
  ];

  for (const ts of tileSizes) {
    for (const color of ['#00C851', '#FF4444']) {
      const tileW = ts.width;
      const tileH = ts.height;

      if (currentX + tileW > ATLAS_WIDTH) {
        currentX = PADDING;
        currentY += tileH + PADDING;
      }

      atlasCtx.fillStyle = color;
      atlasCtx.fillRect(currentX, currentY, tileW, tileH);

      const key = color === '#00C851' ? `imb_ask_${ts.suffix}` : `imb_bid_${ts.suffix}`;
      glyphLookup[key] = {
        sx: currentX,
        sy: currentY,
        sw: tileW,
        sh: tileH,
      };

      currentX += tileW + PADDING;
    }
  }

  tintCanvas = new OffscreenCanvas(ATLAS_WIDTH, ATLAS_HEIGHT);
  tintCtx = tintCanvas.getContext('2d');

  initialized = true;
  return atlasCanvas;
}

function hexToRgb(hex) {
  if (!hex || hex.charAt(0) !== '#') return { r: 255, g: 255, b: 255 };
  let h = hex.slice(1);
  if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
  return {
    r: parseInt(h.slice(0,2), 16),
    g: parseInt(h.slice(2,4), 16),
    b: parseInt(h.slice(4,6), 16),
  };
}

export function getGlyph(char, size) {
  const key = `${char}_${size}`;
  const glyph = glyphLookup[key];
  if (!glyph) {
    return { sx: 0, sy: 0, sw: size, sh: size };
  }
  return glyph;
}

export function getImbalanceTile(side, size) {
  const key = side === 'ask' ? `imb_ask_${size}` : `imb_bid_${size}`;
  const tile = glyphLookup[key];
  if (!tile) {
    return { sx: 0, sy: 0, sw: 6, sh: size };
  }
  return tile;
}

export function blitText(ctx, text, x, y, size, color) {
  if (!initialized) return;

  if (!color || color === '#ffffff' || color === '#fff' || color === 'white') {
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      const glyph = getGlyph(char, size);
      ctx.drawImage(
        atlasCanvas,
        glyph.sx, glyph.sy, glyph.sw, glyph.sh,
        x, y, glyph.sw, glyph.sh
      );
      x += glyph.sw;
    }
    return;
  }

  tintCtx.clearRect(0, 0, ATLAS_WIDTH, ATLAS_HEIGHT);
  tintCtx.drawImage(atlasCanvas, 0, 0);
  tintCtx.globalCompositeOperation = 'source-atop';
  tintCtx.fillStyle = color;
  tintCtx.fillRect(0, 0, ATLAS_WIDTH, ATLAS_HEIGHT);
  tintCtx.globalCompositeOperation = 'destination-in';
  tintCtx.drawImage(atlasCanvas, 0, 0);
  tintCtx.globalCompositeOperation = 'source-over';

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const glyph = getGlyph(char, size);
    ctx.drawImage(
      tintCanvas,
      glyph.sx, glyph.sy, glyph.sw, glyph.sh,
      x, y, glyph.sw, glyph.sh
    );
    x += glyph.sw;
  }
}

export function blitTextBatch(ctx, items) {
  if (!initialized || items.length === 0) return;

  const colorGroups = new Map();
  for (const item of items) {
    const c = item.color || '#ffffff';
    if (!colorGroups.has(c)) colorGroups.set(c, []);
    colorGroups.get(c).push(item);
  }

  for (const [color, group] of colorGroups) {
    if (color === '#ffffff' || color === '#fff' || color === 'white') {
      for (const item of group) {
        let x = item.x;
        for (let i = 0; i < item.text.length; i++) {
          const glyph = getGlyph(item.text[i], item.size);
          ctx.drawImage(atlasCanvas, glyph.sx, glyph.sy, glyph.sw, glyph.sh, x, item.y, glyph.sw, glyph.sh);
          x += glyph.sw;
        }
      }
    } else {
      tintCtx.clearRect(0, 0, ATLAS_WIDTH, ATLAS_HEIGHT);
      tintCtx.drawImage(atlasCanvas, 0, 0);
      tintCtx.globalCompositeOperation = 'source-atop';
      tintCtx.fillStyle = color;
      tintCtx.fillRect(0, 0, ATLAS_WIDTH, ATLAS_HEIGHT);
      tintCtx.globalCompositeOperation = 'destination-in';
      tintCtx.drawImage(atlasCanvas, 0, 0);
      tintCtx.globalCompositeOperation = 'source-over';

      for (const item of group) {
        let x = item.x;
        for (let i = 0; i < item.text.length; i++) {
          const glyph = getGlyph(item.text[i], item.size);
          ctx.drawImage(tintCanvas, glyph.sx, glyph.sy, glyph.sw, glyph.sh, x, item.y, glyph.sw, glyph.sh);
          x += glyph.sw;
        }
      }
    }
  }
}

export function formatVolume(vol) {
  if (vol >= 1e9) return (vol / 1e9).toFixed(1) + 'B';
  if (vol >= 1e6) return (vol / 1e6).toFixed(1) + 'M';
  if (vol >= 1e3) return (vol / 1e3).toFixed(1) + 'K';
  if (vol === 0) return '0';
  return vol.toFixed(0);
}

export function formatDelta(delta) {
  const sign = delta >= 0 ? '+' : '';
  return sign + formatVolume(Math.abs(delta));
}

export function getAtlasCanvas() {
  return atlasCanvas;
}

export function isInitialized() {
  return initialized;
}
