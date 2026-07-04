# AGENTS.md — Nexus Flow Terminal Agent Context

> Complete reference for any AI agent working on this codebase. Read this file first.

---

## Project Identity

**Name:** Nexus Flow Terminal
**Type:** Browser-based institutional HFT Order Flow Terminal
**Goal:** 100% feature parity with **Bookmap Desktop** (WebGL Heatmap) + **GoCharting Web** (Canvas2D Footprint) running simultaneously in a single React application with a shared synchronized Y-axis (Price Ladder).

**Location:** `/home/jogi999/Desktop/nexus-flow-terminal`
**Stack:** Vite + React 18 + WebGL2 + Canvas2D + SharedArrayBuffer + Web Workers + Rust (tokio)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│ BROWSER (Main Thread)                                        │
│                                                              │
│  ┌─────────────────── TAB LAYOUT ──────────────────────┐    │
│  │ [HEATMAP]                      [FOOTPRINT]          │    │
│  │                                                      │    │
│  │  ┌────────────────────┬──────┐  ┌─────┬───────────┐ │    │
│  │  │  WebGL2 Heatmap    │ DOM  │  │ DOM │ Canvas2D  │ │    │
│  │  │  (Bookmap — 85%)  │Ladder│  │Ladd │ Footprint │ │    │
│  │  │  + BBO + Legend   │(15%) │  │(12%)│ (88%)     │ │    │
│  │  └────────────────────┴──────┘  ├─────┼───────────┤ │    │
│  │                                 │ CVD │ Oscillator│ │    │
│  │                                 │     │  (80px)   │ │    │
│  │                                 └─────┴───────────┘ │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌──────────┐  ┌──────────────────────────────────────┐     │
│  │useMemory │  │ Shared viewState object               │     │
│  │Bridge.js │  │ (priceMin, priceMax, zoom, scrollX)  │     │
│  └────┬─────┘  └──────────────────────────────────────┘     │
│       │                                                      │
│  ┌────▼──────────┐                                           │
│  │SharedArrayBuffer│ ← 512MB SPSC Ring Buffer               │
│  │(Tick Data SAB) │                                          │
│  └────▲──────────┘                                           │
│       │                                                      │
│  ┌────┴──────────────────┐                                  │
│  │ IngestionWorker       │                                  │
│  │ - WebSocket → FlatBuf │                                  │
│  │ - LOB state           │                                  │
│  │ - Push via Atomics    │                                  │
│  │ - Mock 10K ticks/sec  │                                  │
│  └────┬──────────────────┘                                  │
│       │                                                      │
│  ┌────▼──────────────────┐                                  │
│  │ AlgorithmWorker       │                                  │
│  │ - Reads SAB (2nd con) │                                  │
│  │ - Writes FeatureSAB   │                                  │
│  │ - CVD, Imbalance,     │                                  │
│  │   VPOC, TPO, Iceberg, │                                  │
│  │   Absorption, BBO     │                                  │
│  └───────────────────────┘                                  │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ RUST BACKEND (tokio)                                         │
│ - Rithmic R|Protocol (Protobuf) ingestion                    │
│ - FXCM Socket.io ingestion                                  │
│ - FlatBuffers serialization → WebSocket broadcast            │
│ - State Recovery (delta sync / full snapshot)                │
│ - Broadcast channel: 65536 capacity                          │
│ - Binds: 0.0.0.0:9001                                       │
└──────────────────────────────────────────────────────────────┘
```

---

## File Map & Responsibilities

### Core Infrastructure (PR 1)

| File | Purpose | Key Exports/Functions |
|------|---------|----------------------|
| `vite.config.js` | COOP/COEP headers for SharedArrayBuffer unlock | — |
| `src/types/MemoryLayout.js` | All byte offset constants, SAB sizes, flag bitmasks | `SAB_SIZE`, `SLOT_SIZE`, `SLOT_COUNT`, `CONTROL`, `SLOT`, `ACTION`, `SIDE`, `FLAG_*`, `FEATURE_*` |
| `src/workers/memory/RingBuffer.js` | Lock-free SPSC ring buffer over SharedArrayBuffer | `RingBuffer.create(sab)`, `.push()`, `.pop()`, `.available()`, `.readSlotAt()`, `createSlot()` |
| `src/workers/IngestionWorker.js` | WebSocket ingestion + FlatBuffer decode + LOB state + mock feed | Messages: `init`, `start-mock`, `stop-mock`, `connect`, `disconnect`, `get-stats`, `request-recovery` |
| `src/hooks/useMemoryBridge.js` | React hook: allocates SAB, spawns workers, runs rAF loop | Returns `{ sab, featureSAB, ringBuffer, worker, algoWorker, getStats, startMock, stopMock, connect }` |

### Algorithm Engine (PR 2)

| File | Purpose | Key Algorithms |
|------|---------|---------------|
| `src/workers/AlgorithmWorker.js` | Reads SAB → writes FeatureSAB with all computed features | CVD + Divergence, Diagonal Imbalance (ratio ≥ 3.0), Stacked Imbalance (3+ consecutive), VPOC (argmax volume), TPO (30s slots, VAH/VAL/POC), Iceberg (Kaplan-Meier survival), Absorption (adaptive threshold), BBO tracking, Bar Stats (Max/Min Delta, Total Volume) |

### Canvas2D Footprint Engine — GoCharting Clone (PR 3)

| File | Purpose |
|------|---------|
| `src/renderer/SpriteAtlas.js` | Pre-rendered glyph atlas (0-9, K/M/B, ▲▼●, imbalance tiles) on OffscreenCanvas. `initSpriteAtlas()`, `blitText()`, `formatVolume()`, `formatDelta()`, `getGlyph()` |
| `src/renderer/FootprintCanvas.js` | Full footprint renderer: Bid/Ask split boxes, imbalance highlights (gold triangles), stacked zones, VPOC markers (orange), volume profile histogram (teal), TPO profile, bar stats grid, price axis |
| `src/components/RightViewport.jsx` | React shell for footprint canvas, wheel zoom/scroll handlers |

### WebGL2 Heatmap Engine — Bookmap Clone (PR 4)

| File | Purpose |
|------|---------|
| `src/shaders/heatmap.vert` | Quad vertex shader with `u_scroll_offset` for texture scrolling |
| `src/shaders/heatmap.frag` | Thermal LUT coloring: `raw_intensity × contrast_scale → LUT lookup` |
| `src/shaders/bubble.vert` | Hardware instancing: per-instance position, radius, color, type |
| `src/shaders/bubble.frag` | SDF circle/diamond rendering with `fwidth()` AA, liquidation pulse |
| `src/shaders/bbo.vert` | BBO line strip vertex shader with side flag |
| `src/shaders/bbo.frag` | BBO fragment shader (teal bid, coral ask) |
| `src/renderer/WebGLHeatmap.js` | Full WebGL2 renderer: desynchronized context, R32F circular texture (4096×4096), 7-stop LUT (Black→Blue→Orange→Yellow→White), instanced bubbles (trade/iceberg/absorption/liquidation), BBO line strips, shared MVP matrix |
| `src/components/LeftViewport.jsx` | React shell for WebGL canvas (used inside HeatmapPage) |
| `src/components/CenterDOM.jsx` | React-bypass DOM ladder (standalone component) |
| `src/components/RightViewport.jsx` | React shell for Canvas2D footprint (used inside FootprintPage) |
| `src/components/HeatmapPage.jsx` | Full-page Bookmap: WebGL heatmap (85%) + DOM ladder (15%) + legend + BBO overlay |
| `src/components/FootprintPage.jsx` | Full-page GoCharting: DOM ladder (12%) + Canvas2D footprint (88%) + CVD oscillator (80px) |
| `src/components/CVDOscillator.jsx` | CVD line chart + per-candle delta bars, reads FeatureSAB |

### Rust Backend (PR 5)

| File | Purpose |
|------|---------|
| `schemas/tick.fbs` | FlatBuffers schema: `TickMessage`, `SnapshotMessage`, `RecoveryRequest`, `DeltaSyncMessage` |
| `rust-backend/src/main.rs` | Tokio async server: mock tick generator, WebSocket broadcaster, LOB state, snapshot task, FlatBuffer encoding |
| `rust-backend/src/state_recovery.rs` | Delta buffer (10K tick ring), recovery handler (delta sync vs full snapshot), heartbeat monitor |
| _(Docker files removed — use `npm run dev` + `cargo run` directly)_ | |

### Integration Layer

| File | Purpose |
|------|---------|
| `src/App.jsx` | Master layout: Tab-based navigation (HEATMAP / FOOTPRINT), full-page views, toolbar, HUD, status bar |
| `src/components/HeatmapPage.jsx` | Full-page Bookmap view: WebGL heatmap (85%) + DOM ladder (15%) + BBO labels + legend |
| `src/components/FootprintPage.jsx` | Full-page GoCharting view: DOM ladder (12%) + Canvas2D footprint (88%) + CVD oscillator (80px) |
| `src/components/CVDOscillator.jsx` | CVD line chart + per-candle delta bars, reads FeatureSAB directly |
| `src/trading/OrderRouter.js` | DOM Pro order routing: market/limit/cancel/modify via WebSocket to ORDER_PLANT |
| `src/config/TerminalConfig.js` | All frozen configuration constants + institutional color palette |
| `src/workers/WasmDecoder.js` | Wasm FlatBuffer decoder wrapper (with JS fallback) |

---

## Memory Layout (SharedArrayBuffer)

### Tick Data SAB — 512MB

```
CONTROL HEADER (first 128 bytes, Int32Array):
┌──────────┬──────────────┬─────────────────┐
│ Offset 0 │ WRITE_INDEX  │ Producer advances│
│ Offset 4 │ READ_INDEX   │ Consumer advances│
│ Offset 8 │ BUFFER_CAP   │ SLOT_COUNT       │
│ Offset 12│ PRODUCER_EPOCH│                  │
│ Offset 16│ CONSUMER_EPOCH│                  │
│ Offset 20│ FLAGS        │                  │
│ Offset 24│ TICK_COUNT   │ Total ticks seen │
│ 32-127   │ PADDING      │ Cache-line align │
└──────────┴──────────────┴─────────────────┘

SLOT LAYOUT (128 bytes each, after header):
┌──────────┬────────────────┬────────────┐
│ Byte 0-7 │ timestamp_ns   │ Float64    │
│ Byte 8-15│ price          │ Float64    │
│ Byte 16-23│ bid_size      │ Float64    │
│ Byte 24-31│ ask_size      │ Float64    │
│ Byte 32-39│ trade_size    │ Float64    │
│ Byte 40-43│ order_id      │ Uint32     │
│ Byte 44-47│ flags         │ Uint32     │
│ Byte 48-51│ price_level_idx│ Uint32    │
│ Byte 52-55│ candle_idx    │ Uint32     │
│ Byte 56-59│ seq_num       │ Uint32     │
│ Byte 60   │ action        │ Uint8      │
│ Byte 61   │ side          │ Uint8      │
│ 62-127   │ reserved      │            │
└──────────┴────────────────┴────────────┘

SLOT_COUNT = floor((512MB - 128) / 128) = 4,194,303 slots
Index wraps via: (index + 1) & (SLOT_COUNT - 1)
```

### Feature SAB — 64MB

```
Region A: CVD Array          — Float64Array[8192]   (1 per candle)
Region B: Delta Array        — Float64Array[8192]
Region C: Imbalance Map      — Float32Array[4096]   (price → ratio)
Region D: Stacked Imbalance  — Uint8Array[4096]     (1=active zone)
Region E: VPOC               — Float64Array[8192]   (price per candle)
Region F: Volume Profile     — Float64Array[4096]   (session total)
Region G: TPO Map            — Uint32Array[4096×96] (price × time-slot)
Region H: Iceberg Map        — Float32Array[65536]  (order → hidden size)
Region I: Absorption Flags   — Uint8Array[4096]
Region J: BBO Bid            — Float64Array[216000] (sliding window)
Region K: BBO Ask            — Float64Array[216000]
Region L: Max Delta          — Float64Array[8192]
Region M: Min Delta          — Float64Array[8192]
Region N: Total Volume       — Float64Array[8192]
Region O: Divergence Flags   — Uint8Array[8192]     (1=bearish, 2=bullish)
```

---

## Flag Bitmasks

| Constant | Value | Meaning |
|----------|-------|---------|
| `FLAG_IS_BID` | `1 << 0` | Tick is on bid side |
| `FLAG_IS_TRADE` | `1 << 1` | Tick is an aggressive trade |
| `FLAG_IS_ICEBERG` | `1 << 2` | Iceberg order detected |
| `FLAG_IS_ABSORPTION` | `1 << 3` | Absorption detected |
| `FLAG_IS_LIQUIDATION` | `1 << 4` | Forced liquidation |
| `FLAG_IS_SNAPSHOT` | `1 << 5` | Part of initial snapshot |

---

## Action & Side Enums

| Enum | Values |
|------|--------|
| `ACTION` | INSERT=0, UPDATE=1, DELETE=2, TRADE=3, TOP_OF_BOOK=4 |
| `SIDE` | BID=0, ASK=1 |

---

## Institutional Color Palette

| Role | Hex | Usage |
|------|-----|-------|
| `BG_PRIMARY` | `#0B0E11` | Main background |
| `BG_SURFACE` | `#131722` | Panels, toolbar, surface |
| `BULLISH` | `#26A69A` | Buy aggression, bid text, positive delta |
| `BEARISH` | `#EF5350` | Sell aggression, ask text, negative delta |
| `COLOR_POC` | `#F2994A` | POC/VPOC markers and lines |
| `COLOR_IMBALANCE` | `#F2C94C` | Imbalance highlight triangles |
| `COLOR_TEXT_PRIMARY` | `#E1E4E8` | Primary text |
| `COLOR_TEXT_MUTED` | `#787B86` | Muted/secondary text |
| `COLOR_BORDER` | `#1E222D` | All borders and grid lines |
| `COLOR_ICEBERG` | `#F2C94C` | Iceberg diamond markers |
| `COLOR_ABSORPTION` | `#AB47BC` | Absorption highlight |
| `COLOR_LIQUIDATION` | `#FF7043` | Liquidation pulse bubbles |

### Heatmap LUT (7-stop gradient)

| Position | Color | Meaning |
|----------|-------|---------|
| 0.00 | Black `rgb(0,0,0)` | No liquidity |
| 0.15 | Dark Blue `rgb(0,0,80)` | Minimal |
| 0.30 | Blue `rgb(0,40,180)` | Low |
| 0.50 | Orange `rgb(230,120,0)` | Medium |
| 0.70 | Yellow `rgb(255,200,0)` | High |
| 0.85 | Bright Yellow `rgb(255,240,100)` | Very High |
| 1.00 | White `rgb(255,255,255)` | Maximum |

---

## Algorithm Reference

### 1. Cumulative Volume Delta (CVD)
```
Per trade tick: delta = (side === ASK) ? +trade_size : -trade_size
Per candle: bar_delta[candle] += delta
CVD[candle] = CVD[candle-1] + bar_delta[candle]
Divergence: Price HH + CVD LH → Bearish | Price LL + CVD HL → Bullish
```

### 2. Diagonal Bid/Ask Imbalance
```
ratio = AskVolume(P) / BidVolume(P - tick_size)
if ratio ≥ 3.0 → ASK_IMBALANCE (gold triangle right)
if ratio ≤ 0.333 → BID_IMBALANCE (gold triangle left)
3+ consecutive → STACKED_IMBALANCE zone (extends horizontally)
```

### 3. Volume Point of Control (VPOC)
```
VPOC[candle] = argmax over price levels of total_traded_volume[P]
Session VolumeProfile[P] += trade_size (cumulative per level)
```

### 4. TPO / Market Profile
```
30-second slots: slot_idx = floor(elapsed_ns / 30s)
TPO_Map[P][slot]++
POC = price with max TPO count
Value Area = expand from POC until ≥ 70% of total TPO count
VAH = highest price in value area, VAL = lowest
```

### 5. Iceberg Detection (Native CME MBO)
```
On ORDER_UPDATE where new_size > old_size:
  pool[order_id].cumulative_refill += (new_size - old_size)
  pool[order_id].hit_count++
  survival_probability = hit_count / (hit_count + 1)
  projected_remaining = cumulative_refill × survival_probability

Synthetic Iceberg (FXCM, no order IDs):
  if total_traded_at_P ≥ 3 × visible_book_depth_at_P → synthetic iceberg
```

### 6. Absorption Detection
```
Rolling window of 50 ticks per price level:
  aggressive_volume_at_P += trade_size
  book_depth_change = |current_depth[P] - depth_50_ticks_ago[P]|
  if aggressive_volume > 3 × rolling_mean_trade_size
     AND book_depth_change < 10% of depth_50_ticks_ago:
       AbsorptionFlags[P] = 1
```

### 7. BBO Micro-Spread
```
1 slot per frame (60/sec)
BBO_Bid[slot] = best_bid_price
BBO_Ask[slot] = best_ask_price
Advance slot via modulo (ring buffer)
Rendered as gl.LINE_STRIP in WebGL (teal bid, coral ask)
```

---

## Hard Constraints (MUST enforce)

1. **ZERO** dynamic object allocation in hot path (no `new`, no `{}`, no `[]`)
2. **ZERO** `JSON.parse()` on main thread
3. **ZERO** `useState` or React re-renders for chart/DOM data updates
4. **ALL** chart data reads via `Atomics.load()` from SharedArrayBuffer
5. **ALL** number text rendering via sprite atlas blitting (no `ctx.fillText` in loop)
6. **Frame budget:** 16.6ms (60 FPS) including ALL draw calls
7. **SAB size:** 512MB max — ring buffer modulo eviction

---

## Y-Axis Synchronization Math

All three viewports share the same `viewState` object (NOT React state — a plain mutable JS object):

```
viewState = {
  scrollX: candle index offset,
  zoom: pixels per candle (4-200),
  priceMin: lowest visible price,
  priceMax: highest visible price,
  pixelsPerTick: canvas.height / ((priceMax - priceMin) / tickSize)
}

priceToY(price) = canvas.height - ((price - priceMin) / (priceMax - priceMin)) × canvas.height

WebGL MVP Matrix:
  ortho(left=0, right=width, bottom=priceMin, top=priceMax, near=-1, far=1)

Canvas2D uses identical priceToY() function → MATHEMATICALLY GUARANTEED sync
```

---

## FlatBuffer TickMessage Schema

```
table TickMessage {
  timestamp_ns: ulong
  price: double
  bid_size: float
  ask_size: float
  trade_size: float
  order_id: uint32
  action: uint8   (INSERT=0, UPDATE=1, DELETE=2, TRADE=3, TOP_OF_BOOK=4)
  side: uint8     (BID=0, ASK=1)
  flags: uint8    (bitmask: ICEBERG=1, ABSORPTION=2, LIQUIDATION=4, SNAPSHOT=8)
  seq_num: ulong
}
```

---

## WebSocket Protocol

**Backend → Browser:** Binary FlatBuffer frames (TickMessage)
**Browser → Backend:** JSON text frames

| Message | Direction | Purpose |
|---------|-----------|---------|
| TickMessage (binary) | Server → Client | Real-time tick stream |
| SnapshotMessage (binary) | Server → Client | Full LOB snapshot on connect |
| `RECOVERY_REQUEST` | Client → Server | `{ type: "RECOVERY_REQUEST", last_seq_num: N }` |
| DeltaSyncMessage (binary) | Server → Client | Missed ticks after reconnect |

**Reconnection Logic:**
- Gap < 5000 ticks → Delta sync (send missed ticks)
- Gap ≥ 5000 ticks → Full snapshot + resume from current head

---

## Worker Message Protocol

### IngestionWorker

| Message Type | Data | Description |
|-------------|------|-------------|
| `init` | `{ sab, wsUrl, useMock, mockRate }` | Initialize with SAB, start feed |
| `start-mock` | `{ rate }` | Start mock data feed |
| `stop-mock` | `{ }` | Stop mock data feed |
| `connect` | `{ wsUrl }` | Connect to live backend |
| `disconnect` | `{ }` | Disconnect |
| `get-stats` | `{ }` | Request stats reply |
| `request-recovery` | `{ }` | Send recovery request to backend |

**Posted back:** `{ type: 'status', status: 'CONNECTED'|'DISCONNECTED'|'ERROR' }`
**Posted back:** `{ type: 'stats', data: { ticksPerSecond, bidCount, askCount, bestBid, bestAsk, lastSeqNum, ringBufferFill } }`

### AlgorithmWorker

| Message Type | Data | Description |
|-------------|------|-------------|
| `init` | `{ sab, featureSAB }` | Initialize with both SABs |
| `set-candle-interval` | `{ intervalMs }` | Change candle timeframe |
| `get-cvd` | `{ }` | Request CVD array |

---

## Current Status & Known Gaps

### Working
- Project scaffolding and build pipeline (Vite + COOP/COEP)
- Ring buffer push/pop with Atomics
- Mock data feed at 10K ticks/sec
- IngestionWorker with LOB state + bid/ask size tracking
- AlgorithmWorker with all 7 algorithms + per-cell volume grid + LOB depth + OHLC + VWAP + TPO structural + Orderflows indicators
- WebGL2 heatmap renderer (LUT, texture, bubbles, BBO) — reads LOB depth, Bookmap color LUT
- Canvas2D footprint renderer with per-cell volume numbers, absorption, divergence, VWAP lines, TPO features, exhaustion/sweep markers
- CandlestickRenderer — OHLC candlestick chart type support
- DOM ladder with bid/ask size columns (both pages)
- VolumeBarOverlay — buy/sell volume bars at bottom of heatmap
- CrosshairOverlay — price/time crosshair with labels on both pages
- SettingsPanel — slide-out panel with dimming, contrast, thresholds, toggles, localStorage persistence
- TimeAndSales panel — scrolling trade list with side coloring
- TradeBus — pub/sub event system for trade data
- Keyboard shortcuts (1/2=tab, +/-=zoom, arrows=scroll, M=mock, R=recenter, T=T&S, S=settings, Esc=close)
- DOM click-to-trade — click price rows to place limit orders
- Institutional color palette applied
- Rust backend with mock generator + WebSocket broadcast
- Tab-based full-page layout: HEATMAP tab + FOOTPRINT tab
- HeatmapPage (WebGL + DOM ladder with BID/ASK + CVD sub-panel + volume bars + crosshair)
- FootprintPage (DOM ladder with BID/ASK + Canvas2D footprint + CVD oscillator + crosshair)
- CVDOscillator with divergence bands
- SpriteAtlas with color tinting (blitText + blitTextBatch)
- Per-candle per-price-level bid/ask volume grid in FeatureSAB
- LOB bid/ask depth arrays in FeatureSAB
- Volume dots wired to trade events with aggressor coloring
- Absorption detection fixed + visualization
- Divergence visualization (candles + CVD panel)
- POC/VAH/VAL rays extending full chart width
- Session VWAP + Buy VWAP + Sell VWAP computation and rendering
- TPO structural: IBR band, single prints, buying/selling tails, naked POC
- Orderflows Trader: Exhaustion prints, Market sweep detector, Delta divergence
- OHLC open/high/low/close per candle in FeatureSAB
- Candle interval dropdown wired to AlgorithmWorker
- Settings persistence via localStorage
- Production build passes (`npx vite build` ✓, 33 modules)
- Dev server runs at http://localhost:5173

### Needs Wiring (Critical Path)
1. **Live data verification:** Confirm mock feed populates all new features with visible data
2. **Per-cell volume numbers:** Verify candleBidVolGrid/candleAskVolGrid indices map correctly
3. **Y-axis sync:** viewState mutation propagating across both page views
4. **OHLC rendering:** Verify OHLC data is correctly tracked and rendered
5. **VWAP bands:** Add standard deviation bands around VWAP (currently just line)

### Not Yet Implemented
- Wasm decoder (Rust → wasm-pack compiled)
- Rithmic Protobuf ingestion (real data)
- FXCM Socket.io ingestion (real data)
- Historical data backfill / Replay mode
- Multi-instrument tab workspace
- Drawing tools (trend lines, Fibonacci, channels)
- Full alert system (webhook, push, email)
- Trading panel UI with bracket orders
- Scripting engine (Lipi equivalent)
- 200+ technical indicators (RSI, MACD, Bollinger, etc.)
- Orderflows Trader remaining indicators (7.3 Ratio, 7.4 POC Slingshot, 7.5 Weakness, 7.6 Sequencing, 7.8-7.24)
- Chart sync across multiple charts
- Custom range volume profile (click-drag)
- Log/sqrt/inverse price scales

---

## Run Commands

```bash
# Frontend (development)
cd /home/jogi999/Desktop/nexus-flow-terminal
npm run dev
# → http://localhost:5173

# Frontend (production build)
npm run build
npm run preview

# Rust backend
cd /home/jogi999/Desktop/nexus-flow-terminal/rust-backend
cargo run --release
# → WebSocket server on ws://localhost:9001

# Both together (2 terminals)
# Terminal 1: npm run dev
# Terminal 2: cd rust-backend && cargo run --release
```

---

## Reference Documents

| Document | Location | Content |
|----------|----------|---------|
| Master Build Prompt | `/home/jogi999/Desktop/legend/NEXUS_FLOW_LEGENDARY_MASTER_PROMPT.md` | Full PR specs (PR 1-5 + Integration) |
| Deep Research Notes | `/home/jogi999/Desktop/legend/Untitled 2.md` | Backend + Frontend + Infrastructure research |
| Bookmap PDFs | `/home/jogi999/Desktop/legend/*_images/` | UI screenshots (900+ pages) |
| GoCharting Lesson | `/home/jogi999/Desktop/legend/GochartingOrderFlowLesson2_images/` | Order flow lesson (27 pages) |
