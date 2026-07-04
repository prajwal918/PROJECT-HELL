package com.overseer.bridge;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
import com.motivewave.platform.sdk.study.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/**
 * OVERSEER MotiveWave MBO Bridge v2026-06-16.1-STABLE
 * 
 * HARDCODED RULES (cannot be disabled):
 * 1. NEVER disconnect — catch ALL Throwables silently
 * 2. AUTO-REBUILD socket on ANY failure (infinite retry)
 * 3. FORCE RESUBSCRIPTION every 30s regardless of state
 * 4. AGGRESSIVE MAINTENANCE LOOP (500ms check cycle)
 * 5. HEARTBEAT every 2s to prove UDP path is alive
 * 6. RITHMIC RECONNECT DETECTION with full state reset
 */
@StudyHeader(
    namespace = "com.overseer",
    id = "OverseerMotiveWaveBridge",
    name = "OVERSEER MotiveWave MBO Bridge",
    menu = "OVERSEER",
    desc = "ROCK-SOLID UDP Bridge — NEVER disconnects, auto-rebuilds on any failure",
    overlay = true,
    studyOverlay = true,
    strategy = true,
    supportsBarUpdates = false,
    requiresBarUpdates = false,
    requiresBidAskHistory = true,
    multipleInstrument = true
)
public class OverseerMotiveWaveBridge extends Study implements DOMListener {

    private static final String VERSION = "2026-06-16.1-STABLE";

    // --- Settings (editable in MotiveWave GUI) ---
    private String udpHost = "127.0.0.1";
    private int udpPort = 65000;
    private int domDepth = 10;
    private int mboFilterMinSize = 5; // Defaulted to 5 to filter noise
    private boolean sendTicks = true;
    private boolean sendDomSnapshots = true;
    private boolean sendMboEvents = true;
    private int domSnapshotIntervalMs = 100;
    private int heartbeatIntervalMs = 2000;

    // --- INTERNAL STATE (atomic + volatile for thread safety) ---
    private volatile DatagramSocket udpSocket;
    private volatile InetSocketAddress udpEndpoint;
    private final AtomicInteger packetCount = new AtomicInteger(0);
    private final AtomicInteger errorCount = new AtomicInteger(0);
    private volatile long lastDomSnapshotTime = 0;
    private volatile boolean active = false;
    private final AtomicInteger socketReconnectCount = new AtomicInteger(0);
    private final AtomicInteger consecutiveSendErrors = new AtomicInteger(0);
    private final AtomicLong lastPacketTime = new AtomicLong(System.currentTimeMillis());
    private final Object socketLock = new Object();
    private volatile long lastSocketRefreshTime = 0;
    private volatile long lastHeartbeatTime = 0;
    private volatile long lastInstrumentSubscribeTime = 0;
    private volatile int subscribeAttempts = 0;
    private volatile boolean rithmicWasConnected = false;
    private volatile boolean socketEverBuilt = false;
    private ExecutorService maintenanceExecutor;

    private final ConcurrentHashMap<String, List<DomLevelState>> prevBidDom = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, List<DomLevelState>> prevAskDom = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Long> lastTickPerSymbol = new ConcurrentHashMap<>();
    private final AtomicInteger subscribedCount = new AtomicInteger(0);

    private final Object logLock = new Object();
    private String logPath;
    private final AtomicBoolean autoStarted = new AtomicBoolean(false);
    private ExecutorService initExecutor;

    private static String resolveLogPath() {
        // Linux path: /home/jogi999/PROJECT HELL/overseer/logs/motivewave_bridge.log
        String home = System.getProperty("user.home", ".");
        String primaryPath = home + "/PROJECT HELL/overseer/logs/motivewave_bridge.log";
        java.io.File f = new java.io.File(primaryPath);
        if (f.getParentFile() != null) {
            try { f.getParentFile().mkdirs(); } catch (Exception ignored) {}
            return primaryPath;
        }
        // Windows fallback
        String winPath = home + "\\PROJECT HELL\\overseer\\logs\\motivewave_bridge.log";
        java.io.File fw = new java.io.File(winPath);
        if (fw.getParentFile() != null) {
            try { fw.getParentFile().mkdirs(); } catch (Exception ignored) {}
            return winPath;
        }
        return home + java.io.File.separator + "overseer_bridge.log";
    }

    @Override
    public void initialize(Defaults defaults) {
        SettingsDescriptor sd = new SettingsDescriptor();
        SettingTab tab = new SettingTab("Connection");
        SettingGroup connGroup = tab.addGroup("UDP Settings");
        connGroup.addRow(
            new StringDescriptor("UdpHost", "UDP Host", udpHost),
            new IntegerDescriptor("UdpPort", "UDP Port", udpPort, 1, 65535, 1),
            new IntegerDescriptor("DomDepth", "DOM Depth", domDepth, 1, 50, 1),
            new IntegerDescriptor("MboFilter", "MBO Filter Min", mboFilterMinSize, 0, 99999, 1)
        );
        sd.addTab(tab);

        SettingTab flagsTab = new SettingTab("Data");
        SettingGroup dataGroup = flagsTab.addGroup("Event Types");
        dataGroup.addRow(
            new BooleanDescriptor("SendTicks", "Send Tick Events", sendTicks),
            new BooleanDescriptor("SendDom", "Send DOM Snapshots", sendDomSnapshots),
            new BooleanDescriptor("SendMbo", "Send MBO Events", sendMboEvents),
            new IntegerDescriptor("DomInterval", "DOM Interval MS", domSnapshotIntervalMs, 10, 5000, 10),
            new IntegerDescriptor("HeartbeatMs", "Heartbeat Interval MS", heartbeatIntervalMs, 1000, 30000, 1000)
        );
        sd.addTab(flagsTab);
        setSettingsDescriptor(sd);
        setRuntimeDescriptor(new RuntimeDescriptor());
        
        // Auto-start the bridge after settings are loaded (500ms delay)
        initExecutor = Executors.newSingleThreadExecutor(r -> {
            Thread t = new Thread(r, "overseer-init");
            t.setDaemon(true);
            return t;
        });
        initExecutor.submit(() -> {
            try { Thread.sleep(500); } catch (InterruptedException ignored) {}
            startBridge("AUTO");
        });
    }

    @Override
    protected void calculate(int index, DataContext ctx) {
        // Also trigger start from calculate as a backup
        if (autoStarted.compareAndSet(false, true)) {
            startBridge("CALC");
        }
    }

    // =================================================================
    // LIFECYCLE — NEVER STOP
    // =================================================================

    @Override
    public void onActivate(OrderContext ctx) {
        logFile("onActivate called — delegating to startBridge()");
        startBridge("ACTIVATE");
    }

    @Override
    public void onDeactivate(OrderContext ctx) {
        logFile("onDeactivate called — IGNORED (hardcoded: NEVER stop)");
        // The bridge keeps running even if deactivated
        // This is intentional — we never want the UDP stream to stop
    }

    // =================================================================
    // SHARED STARTUP (called from initialize, calculate, onActivate)
    // =================================================================

    private synchronized void startBridge(String source) {
        try {
            Settings s = getSettings();
            if (s != null) {
                udpHost = s.getString("UdpHost", udpHost);
                udpPort = s.getInteger("UdpPort", udpPort);
                domDepth = s.getInteger("DomDepth", domDepth);
                mboFilterMinSize = s.getInteger("MboFilter", mboFilterMinSize);
                sendTicks = s.getBoolean("SendTicks", sendTicks);
                sendDomSnapshots = s.getBoolean("SendDom", sendDomSnapshots);
                sendMboEvents = s.getBoolean("SendMbo", sendMboEvents);
                domSnapshotIntervalMs = s.getInteger("DomInterval", domSnapshotIntervalMs);
                heartbeatIntervalMs = s.getInteger("HeartbeatMs", heartbeatIntervalMs);
            }
            if (logPath == null) {
                logPath = resolveLogPath();
            }
            
            // Prevent double-start
            if (active && maintenanceExecutor != null && !maintenanceExecutor.isShutdown()) {
                logFile("startBridge(" + source + "): already active, skipping");
                return;
            }
            
            active = true;
            maintenanceExecutor = Executors.newSingleThreadExecutor(r -> {
                Thread t = new Thread(r, "overseer-rock-loop");
                t.setDaemon(true);
                return t;
            });
            maintenanceExecutor.submit(this::rockSolidLoop);

            logFile("=== OVERSEER Bridge " + VERSION + " STARTED (source=" + source + ") ===");
            logFile("HARDCODED: NEVER disconnect, ALWAYS rebuild socket, FORCED resubscription");
            logFile("UDP target=" + udpHost + ":" + udpPort + " multipleInstrument=true");
        } catch (Throwable e) {
            logFile("startBridge(" + source + ") error: " + e.toString());
            active = true;
            maintenanceExecutor = Executors.newSingleThreadExecutor(r -> {
                Thread t = new Thread(r, "overseer-rock-loop");
                t.setDaemon(true);
                return t;
            });
            maintenanceExecutor.submit(this::rockSolidLoop);
        }
    }

    // =================================================================
    // ROCK-SOLID MAINTENANCE LOOP (500ms cycle)
    // =================================================================

    private void rockSolidLoop() {
        logFile("ROCK-SOLID Maintenance Loop starting — 500ms cycle, NEVER STOP");

        while (active) {
            try {
                long now = System.currentTimeMillis();

                // 1. Ensure socket is alive — rebuild on ANY issue
                boolean needsRebuild = false;
                synchronized (socketLock) {
                    if (udpSocket == null || udpSocket.isClosed() || udpEndpoint == null) {
                        needsRebuild = true;
                    }
                }

                if (!needsRebuild && !socketEverBuilt) {
                    needsRebuild = true;
                }

                // Force refresh every 1 hour to handle network changes (was 60s)
                if (!needsRebuild && (now - lastSocketRefreshTime > 3_600_000)) {
                    needsRebuild = true;
                }

                // No packets for 300s = rebuild (was 10s - too aggressive for slow symbols)
                if (!needsRebuild && (now - lastPacketTime.get() > 300_000)) {
                    logFile("Watchdog: No packets for 300s — rebuilding socket");
                    needsRebuild = true;
                }

                if (needsRebuild) {
                    rockRebuildSocket();
                }

                // 2. Force resubscription every 30s
                if (now - lastInstrumentSubscribeTime > 30_000) {
                    resubscribeInstruments();
                }

                // 3. Check Rithmic connection
                boolean rithmicConnected = checkRithmicConnection();
                if (!rithmicConnected && rithmicWasConnected) {
                    logFile("RITHMIC DISCONNECT DETECTED! Full state reset...");
                    prevBidDom.clear();
                    prevAskDom.clear();
                    lastTickPerSymbol.clear();
                    // Force immediate resubscription
                    lastInstrumentSubscribeTime = 0;
                }
                rithmicWasConnected = rithmicConnected;

                // 4. Aggressive heartbeat — every 2s
                if (now - lastHeartbeatTime > heartbeatIntervalMs) {
                    sendHeartbeat();
                    lastHeartbeatTime = now;
                }

                Thread.sleep(500);
            } catch (InterruptedException e) {
                // Only exit on intentional interrupt
                if (!active) break;
            } catch (Throwable t) {
                logFile("Rock Loop Error (recovering): " + t.toString());
                try { Thread.sleep(2000); } catch (Exception ignored) {}
            }
        }

        // If we ever exit the loop, restart (NEVER STOP)
        if (active) {
            logFile("CRITICAL: Loop exited unexpectedly — SELF-HEALING restart");
            maintenanceExecutor.submit(this::rockSolidLoop);
        }
    }

    // =================================================================
    // ROCK-SOLID SOCKET (infinite retry, never give up)
    // =================================================================

    private void rockRebuildSocket() {
        int attempts = 0;
        while (active) {
            try {
                synchronized (socketLock) {
                    if (udpSocket != null) {
                        try { udpSocket.close(); } catch (Throwable ignored) {}
                    }
                    try {
                        InetAddress addr = InetAddress.getByName(udpHost);
                        udpEndpoint = new InetSocketAddress(addr, udpPort);
                        udpSocket = new DatagramSocket();
                        udpSocket.setSendBufferSize(512 * 1024);
                        lastSocketRefreshTime = System.currentTimeMillis();
                        lastPacketTime.set(System.currentTimeMillis());
                        socketReconnectCount.incrementAndGet();
                        consecutiveSendErrors.set(0);
                        socketEverBuilt = true;
                        logFile("SOCKET REBUILD OK: " + addr.getHostAddress() + ":" + udpPort + " (#" + socketReconnectCount.get() + ")");
                        return;
                    } catch (Throwable e) {
                        attempts++;
                        long delay = Math.min(attempts * 1000L, 30_000L);
                        logFile("SOCKET FAIL (attempt " + attempts + "): " + e.getMessage() + " — retry in " + delay + "ms");
                    }
                }
                Thread.sleep(Math.min(attempts * 1000L, 30_000L));
            } catch (Throwable t) {
                logFile("rockRebuildSocket error: " + t.toString());
                try { Thread.sleep(5000); } catch (Exception ignored) {}
            }
        }
    }

    // =================================================================
    // INSTRUMENT SUBSCRIPTION (aggressive resubscription)
    // =================================================================

    private boolean checkRithmicConnection() {
        if (lastTickPerSymbol.isEmpty()) return false;
        long now = System.currentTimeMillis();
        for (Map.Entry<String, Long> entry : lastTickPerSymbol.entrySet()) {
            if (now - entry.getValue() < 60_000) return true;
        }
        return false;
    }

    @SuppressWarnings("unchecked")
    private void resubscribeInstruments() {
        lastInstrumentSubscribeTime = System.currentTimeMillis();
        subscribeAttempts++;

        List instrList = null;
        try {
            instrList = getInstruments();
        } catch (Throwable e) {
            logFile("getInstruments() error: " + e.toString());
        }

        if (instrList == null || instrList.isEmpty()) {
            DataContext dc = null;
            try { dc = getDataContext(); } catch (Throwable ignored) {}
            if (dc != null && dc.getInstrument() != null) {
                instrList = new ArrayList();
                instrList.add(dc.getInstrument());
            }
        }

        if (instrList == null || instrList.isEmpty()) {
            if (subscribeAttempts % 30 == 0) {
                logFile("No instruments yet (attempt " + subscribeAttempts + ") — will keep retrying");
            }
            return;
        }

        int count = 0;
        for (Object obj : instrList) {
            if (!(obj instanceof Instrument)) continue;
            Instrument inst = (Instrument) obj;
            String symbol = inst.getSymbol();

            try {
                inst.removeListener((DOMListener) this);
            } catch (Throwable ignored) {}

            try {
                inst.addListener((DOMListener) this);
                inst.addListener((TickOperation) (tick) -> {
                    try {
                        if (active && sendTicks) onTickEvent(symbol, tick);
                    } catch (Throwable ignored) {}
                });
                count++;
            } catch (Throwable e) {
                logFile("Subscribe error " + symbol + ": " + e.toString());
            }
        }

        int newCount = subscribedCount.get();
        if (count != newCount || count == 0) {
            logFile("Subscription update: " + count + " active (was " + newCount + ") — attempt #" + subscribeAttempts);
        }
        subscribedCount.set(count);

        if (count > 0) {
            if (subscribeAttempts % 10 == 1) {
                logFile("Bridge READY. " + count + " instruments subscribed. Packets sent: " + packetCount.get());
            }
        }
    }

    // =================================================================
    // EVENT HANDLERS (NEVER crash)
    // =================================================================

    @Override
    public void update(DOM dom) {
        try {
            if (!active || dom == null) return;
            Instrument inst = dom.getInstrument();
            if (inst == null) return;
            String symbol = inst.getSymbol();
            lastTickPerSymbol.put(symbol, System.currentTimeMillis());
            if (sendDomSnapshots) {
                long now = System.currentTimeMillis();
                if (now - lastDomSnapshotTime >= domSnapshotIntervalMs) {
                    lastDomSnapshotTime = now;
                    sendDomSnapshot(symbol, dom);
                }
            }
            if (sendMboEvents) inferMboEvents(symbol, dom);
        } catch (Throwable e) {
            errorCount.incrementAndGet();
        }
    }

    private void onTickEvent(String symbol, Tick tick) {
        try {
            if (tick == null || !active) return;
            lastTickPerSymbol.put(symbol, System.currentTimeMillis());
            Map<String, Object> msg = new LinkedHashMap<>();
            msg.put("type", "TICK");
            msg.put("source", "motivewave");
            msg.put("version", VERSION);
            msg.put("symbol", symbol);
            msg.put("price", (double) tick.getPrice());
            msg.put("volume", tick.getVolume());
            if (tick.getBidPrice() != 0 || tick.getAskPrice() != 0) {
                msg.put("bid_price", (double) tick.getBidPrice());
                msg.put("ask_price", (double) tick.getAskPrice());
            }
            msg.put("bid_size", tick.getBidSizeAsFloat());
            msg.put("ask_size", tick.getAskSizeAsFloat());
            msg.put("timestamp", tick.getTime());
            try {
                List instrList = getInstruments();
                if (instrList != null) {
                    for (Object obj : instrList) {
                        if (obj instanceof Instrument) {
                            Instrument inst = (Instrument) obj;
                            if (symbol.equals(inst.getSymbol())) {
                                long oi = 0;
                                
                                break;
                            }
                        }
                    }
                }
            } catch (Throwable ignored) {}
            sendJson(msg);
        } catch (Throwable e) {
            errorCount.incrementAndGet();
        }
    }

    // =================================================================
    // DATA SERIALIZATION (same as before, just hardened)
    // =================================================================

    private void sendDomSnapshot(String symbol, DOM dom) {
        try {
            List<?> askRows = dom.getAskRows();
            List<?> bidRows = dom.getBidRows();
            if (askRows == null && bidRows == null) return;
            List<Map<String, Object>> bids = extractDomRows(bidRows);
            List<Map<String, Object>> asks = extractDomRows(askRows);
            Map<String, Object> msg = new LinkedHashMap<>();
            msg.put("type", "DOM_SNAPSHOT");
            msg.put("source", "motivewave");
            msg.put("version", VERSION);
            msg.put("symbol", symbol);
            msg.put("bids", bids);
            msg.put("asks", asks);
            msg.put("timestamp", System.currentTimeMillis());
            sendJson(msg);
        } catch (Throwable e) { errorCount.incrementAndGet(); }
    }

    private List<Map<String, Object>> extractDomRows(List<?> rows) {
        List<Map<String, Object>> result = new ArrayList<>();
        if (rows == null) return result;
        int count = 0;
        for (Object r : rows) {
            if (!(r instanceof DOMRow)) continue;
            if (count >= domDepth) break;
            try {
                DOMRow row = (DOMRow) r;
                Map<String, Object> level = new LinkedHashMap<>();
                level.put("price", (double) row.getPrice());
                level.put("size", (double) row.getSize());
                level.put("order_count", row.getOrderCount());
                List<Map<String, Object>> orders = new ArrayList<>();
                List<?> rowOrders = row.getOrders();
                if (rowOrders != null) {
                    // Sort orders by size descending to keep the most important ones
                    List<DOMOrder> sortedOrders = new ArrayList<>();
                    for (Object o : rowOrders) {
                        if (o instanceof DOMOrder) sortedOrders.add((DOMOrder) o);
                    }
                    sortedOrders.sort((a, b) -> Float.compare(b.getQuantity(), a.getQuantity()));

                    int orderCount = 0;
                    for (DOMOrder ord : sortedOrders) {
                        if (orderCount >= 15) break; // Hard limit 15 orders per level in snapshot
                        if (ord.getQuantity() >= mboFilterMinSize) {
                            Map<String, Object> om = new LinkedHashMap<>();
                            om.put("order_id", ord.getExchangeOrderId());
                            om.put("quantity", (double) ord.getQuantity());
                            orders.add(om);
                            orderCount++;
                        }
                    }
                }
                level.put("orders", orders);
                result.add(level);
                count++;
            } catch (Throwable e) {
                errorCount.incrementAndGet();
            }
        }
        return result;
    }

    private void inferMboEvents(String symbol, DOM dom) {
        try {
            List<DomLevelState> currentBids = snapshotState(dom.getBidRows());
            List<DomLevelState> currentAsks = snapshotState(dom.getAskRows());
            List<DomLevelState> prevBids = prevBidDom.put(symbol, currentBids);
            List<DomLevelState> prevAsks = prevAskDom.put(symbol, currentAsks);
            if (prevBids != null) compareLevels(symbol, "BID", prevBids, currentBids);
            if (prevAsks != null) compareLevels(symbol, "ASK", prevAsks, currentAsks);
        } catch (Throwable e) { errorCount.incrementAndGet(); }
    }

    private List<DomLevelState> snapshotState(List<?> rows) {
        List<DomLevelState> list = new ArrayList<>();
        if (rows == null) return list;
        for (Object r : rows) {
            try {
                if (r instanceof DOMRow) {
                    DOMRow row = (DOMRow) r;
                    list.add(new DomLevelState(row.getPrice(), row.getSize(), row.getOrderCount(), row.getOrders()));
                }
            } catch (Throwable e) { errorCount.incrementAndGet(); }
        }
        return list;
    }

    private void compareLevels(String symbol, String side, List<DomLevelState> old, List<DomLevelState> cur) {
        try {
            Map<Float, DomLevelState> oldMap = new HashMap<>();
            for (DomLevelState d : old) oldMap.put(d.price, d);
            for (DomLevelState c : cur) {
                DomLevelState o = oldMap.get(c.price);
                if (o == null) emitMboEvent(symbol, side, "ADD", c.price, c.size, 0, c.orderCount);
                else {
                    float delta = c.size - o.size;
                    if (delta > 0) emitMboEvent(symbol, side, "ADD", c.price, delta, o.orderCount, c.orderCount);
                    else if (delta < 0) emitMboEvent(symbol, side, "MODIFY", c.price, -delta, o.orderCount, c.orderCount);
                }
            }
        } catch (Throwable e) { errorCount.incrementAndGet(); }
    }

    private void emitMboEvent(String symbol, String side, String action, float price, float size, int prevOC, int curOC) {
        if (size <= 0) return;
        try {
            Map<String, Object> msg = new LinkedHashMap<>();
            msg.put("type", "MBO_EVENT");
            msg.put("symbol", symbol);
            msg.put("side", side);
            msg.put("action", action);
            msg.put("price", (double) price);
            msg.put("size", (double) size);
            msg.put("prev_order_count", prevOC);
            msg.put("cur_order_count", curOC);
            msg.put("timestamp", System.currentTimeMillis());
            sendJson(msg);
        } catch (Throwable e) { errorCount.incrementAndGet(); }
    }

    // =================================================================
    // NETWORK I/O (hardened)
    // =================================================================

    private void sendJson(Map<String, Object> msg) {
        if (!active) return;
        try {
            String json = toJson(msg);
            byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
            if (bytes.length > 65507) return;
            synchronized (socketLock) {
                if (udpSocket == null || udpSocket.isClosed() || udpEndpoint == null) return;
                try {
                    DatagramPacket packet = new DatagramPacket(bytes, bytes.length, udpEndpoint);
                    udpSocket.send(packet);
                    consecutiveSendErrors.set(0);
                    lastPacketTime.set(System.currentTimeMillis());
                    packetCount.incrementAndGet();
                } catch (Throwable e) {
                    if (consecutiveSendErrors.incrementAndGet() >= 2) {
                        logFile("Send FAIL (consecutive=" + consecutiveSendErrors.get() + "): " + e.getMessage() + " — marking socket for rebuild");
                        synchronized (socketLock) {
                            try { udpSocket.close(); } catch (Throwable ignored) {}
                            udpSocket = null;
                            udpEndpoint = null;
                        }
                    }
                }
            }
        } catch (Throwable t) {
            errorCount.incrementAndGet();
        }
    }

    private void sendHeartbeat() {
        try {
            Map<String, Object> hb = new LinkedHashMap<>();
            hb.put("type", "BRIDGE_HEARTBEAT");
            hb.put("version", VERSION);
            hb.put("reconnects", socketReconnectCount.get());
            hb.put("packets", packetCount.get());
            hb.put("errors", errorCount.get());
            hb.put("subscribed", subscribedCount.get());
            hb.put("active_symbols", lastTickPerSymbol.size());
            hb.put("timestamp", System.currentTimeMillis());
            sendJson(hb);
        } catch (Throwable e) { errorCount.incrementAndGet(); }
    }

    // =================================================================
    // JSON SERIALIZATION
    // =================================================================

    private String toJson(Map<String, Object> map) {
        StringBuilder sb = new StringBuilder(2048);
        sb.append('{');
        boolean first = true;
        for (Map.Entry<String, Object> e : map.entrySet()) {
            if (!first) sb.append(',');
            first = false;
            sb.append('"').append(e.getKey()).append("\":").append(valueToJson(e.getValue()));
        }
        sb.append('}');
        return sb.toString();
    }

    private String valueToJson(Object val) {
        if (val == null) return "null";
        if (val instanceof Number || val instanceof Boolean) return val.toString();
        if (val instanceof String) return "\"" + val + "\"";
        if (val instanceof List) {
            List<?> l = (List<?>) val;
            StringBuilder sb = new StringBuilder("[");
            for (int i = 0; i < l.size(); i++) {
                if (i > 0) sb.append(',');
                sb.append(valueToJson(l.get(i)));
            }
            return sb.append(']').toString();
        }
        if (val instanceof Map) return toJson((Map<String, Object>) val);
        return "\"" + val.toString() + "\"";
    }

    // =================================================================
    // LOGGING (thread-safe, file-based)
    // =================================================================

    private void logFile(String message) {
        try {
            String line = String.format("%s %s%n", new java.util.Date().toString(), message);
            synchronized (logLock) {
                if (logPath == null) return;
                java.nio.file.Files.write(
                    java.nio.file.Paths.get(logPath),
                    line.getBytes(StandardCharsets.UTF_8),
                    java.nio.file.StandardOpenOption.CREATE,
                    java.nio.file.StandardOpenOption.APPEND
                );
            }
        } catch (Throwable ignored) {}
    }

    // =================================================================
    // HELPER CLASSES
    // =================================================================

    private static class DomLevelState {
        final float price;
        final float size;
        final int orderCount;
        final List<?> orders;
        DomLevelState(float price, float size, int oc, List<?> o) {
            this.price = price; this.size = size; this.orderCount = oc; this.orders = o;
        }
    }
}
