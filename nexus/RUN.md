# Nexus Flow Terminal — Run Guide

## Quick Start (Development)

```bash
cd /home/jogi999/Desktop/nexus-flow-terminal
npm run dev
```

Open `http://localhost:5173` in Chrome/Edge (SharedArrayBuffer requires Chromium).

## Production Build

```bash
npm run build
npm run preview
```

## Full Stack (Frontend + Rust Backend)

```bash
# Terminal 1 — Frontend
cd /home/jogi999/Desktop/nexus-flow-terminal
npm run dev

# Terminal 2 — Rust Backend (requires Rust installed)
cd /home/jogi999/Desktop/nexus-flow-terminal/rust-backend
cargo run --release
```

## Browser Requirements

- Chrome 92+ or Edge 92+ (SharedArrayBuffer support)
- Cross-Origin Isolation headers are configured in `vite.config.js`
- Verify SAB is active: open DevTools Console → type `typeof SharedArrayBuffer` → should return `"function"`

## Mock Data Mode

The terminal starts in mock mode by default (10,000 ticks/sec simulated feed).

Controls in the toolbar:
- **START MOCK / STOP MOCK** — Toggle simulated market data
- **CONNECT** — Connect to live Rust backend at `ws://localhost:9001`

## Layout — Tab-Based Full-Page Views

Switch between two full-page views via toolbar tabs:

```
┌──────────────────────────────────────────────────────┐
│ NEXUS FLOW │ [HEATMAP] [FOOTPRINT] │ ES │ 1m │ ●    │
├──────────────────────────────────────────────────────┤
│                                                      │
│  HEATMAP TAB (full page):                            │
│  ┌─────────────────────────────────┬────────┐        │
│  │                                 │ PRICE  │        │
│  │  WebGL2 Heatmap                 │ LADDER │        │
│  │  (Bookmap — 85%)               │ (15%)  │        │
│  │                                 │        │        │
│  │  BBO overlay + Legend           │        │        │
│  └─────────────────────────────────┴────────┘        │
│                                                      │
│  FOOTPRINT TAB (full page):                          │
│  ┌──────┬────────────────────────────────────┐       │
│  │PRICE │  Canvas2D Footprint                │       │
│  │      │  (GoCharting — 88%)                │       │
│  │      │  + Volume Profile + Imbalance      │       │
│  ├──────┼────────────────────────────────────┤       │
│  │ CVD  │  CVD Oscillator (80px)             │       │
│  └──────┴────────────────────────────────────┘       │
│                                                      │
├──────────────────────────────────────────────────────┤
│ NEXUS FLOW │ v0.2.0 │ Bid/Ask │ Status              │
└──────────────────────────────────────────────────────┘
```

## Project Structure

```
nexus-flow-terminal/
├── vite.config.js              # COOP/COEP headers for SAB
├── src/
│   ├── App.jsx                 # Tab-based layout: HEATMAP / FOOTPRINT pages
│   ├── config/TerminalConfig.js
│   ├── types/MemoryLayout.js   # SAB byte offsets, flag bitmasks
│   ├── hooks/useMemoryBridge.js
│   ├── workers/
│   │   ├── memory/RingBuffer.js
│   │   ├── IngestionWorker.js  # WebSocket + FlatBuffer + LOB
│   │   ├── AlgorithmWorker.js  # CVD, Imbalance, VPOC, TPO, Iceberg, Absorption
│   │   └── WasmDecoder.js
│   ├── renderer/
│   │   ├── SpriteAtlas.js
│   │   ├── FootprintCanvas.js  # Canvas2D (GoCharting clone)
│   │   └── WebGLHeatmap.js     # WebGL2 (Bookmap clone)
│   ├── shaders/
│   │   ├── heatmap.vert/frag
│   │   ├── bubble.vert/frag
│   │   └── bbo.vert/frag
│   ├── components/
│   │   ├── HeatmapPage.jsx     # Full-page Bookmap (WebGL + DOM ladder)
│   │   ├── FootprintPage.jsx   # Full-page GoCharting (Canvas2D + DOM + CVD)
│   │   ├── CVDOscillator.jsx   # CVD line + delta bar sub-panel
│   │   ├── LeftViewport.jsx    # (Legacy — WebGL canvas shell)
│   │   ├── CenterDOM.jsx       # (Legacy — DOM ladder component)
│   │   └── RightViewport.jsx   # (Legacy — Canvas2D shell)
│   └── trading/OrderRouter.js
├── schemas/tick.fbs
├── rust-backend/
│   └── src/main.rs + state_recovery.rs
└── schemas/tick.fbs
```

## Keyboard / Mouse Controls

| Action | Control |
|--------|---------|
| Scroll price axis | Mouse wheel on any viewport |
| Zoom candle width | Ctrl + Mouse wheel |
| Place limit order | Click a price row on DOM ladder |
| Switch view | Click HEATMAP / FOOTPRINT tab |
