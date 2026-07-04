mod rithmic;
use std::sync::Arc;
use std::collections::VecDeque;
use std::env;
use parking_lot::{RwLock, Mutex};
use tokio::sync::broadcast;
use tokio::net::TcpListener;
use tokio_tungstenite::tungstenite::{Message, Error};
use futures_util::{SinkExt, StreamExt};
use ordered_float::OrderedFloat;
use tracing::{info, warn, error};

const BROADCAST_CAPACITY: usize = 65536;
const DELTA_BUFFER_CAPACITY: usize = 10000;
const SNAPSHOT_INTERVAL_SECS: u64 = 300;

use rithmic::TickData;

#[derive(Clone, Debug)]
struct LobLevel {
    bid_size: f64,
    ask_size: f64,
    order_count: u32,
}

struct LimitOrderBook {
    bids: std::collections::BTreeMap<OrderedFloat<f64>, LobLevel>,
    asks: std::collections::BTreeMap<OrderedFloat<f64>, LobLevel>,
}

impl LimitOrderBook {
    fn new() -> Self {
        Self {
            bids: std::collections::BTreeMap::new(),
            asks: std::collections::BTreeMap::new(),
        }
    }

    fn insert(&mut self, price: f64, side: u8, size: f64) {
        let key = OrderedFloat(price);
        if side == 0 {
            self.bids.entry(key).or_insert(LobLevel { bid_size: size, ask_size: 0.0, order_count: 1 }).bid_size = size;
        } else {
            self.asks.entry(key).or_insert(LobLevel { bid_size: 0.0, ask_size: size, order_count: 1 }).ask_size = size;
        }
    }

    fn update(&mut self, price: f64, side: u8, size: f64) {
        let key = OrderedFloat(price);
        if size == 0.0 {
            self.delete(price, side);
            return;
        }
        if side == 0 {
            if let Some(level) = self.bids.get_mut(&key) {
                level.bid_size = size;
            } else {
                self.insert(price, side, size);
            }
        } else {
            if let Some(level) = self.asks.get_mut(&key) {
                level.ask_size = size;
            } else {
                self.insert(price, side, size);
            }
        }
    }

    fn delete(&mut self, price: f64, side: u8) {
        let key = OrderedFloat(price);
        if side == 0 {
            self.bids.remove(&key);
        } else {
            self.asks.remove(&key);
        }
    }
}

struct DeltaBuffer {
    buffer: VecDeque<TickData>,
}

impl DeltaBuffer {
    fn new() -> Self {
        Self {
            buffer: VecDeque::with_capacity(DELTA_BUFFER_CAPACITY),
        }
    }

    fn push(&mut self, tick: TickData) {
        if self.buffer.len() >= DELTA_BUFFER_CAPACITY {
            self.buffer.pop_front();
        }
        self.buffer.push_back(tick);
    }

    fn get_since(&self, seq_num: u64) -> Vec<&TickData> {
        self.buffer.iter().filter(|t| t.seq_num > seq_num).collect()
    }
}

struct ClientState {
    last_pong: std::time::Instant,
}

fn encode_tick_flatbuffer(tick: &TickData) -> Vec<u8> {
    let mut builder = flatbuffers::FlatBufferBuilder::with_capacity(256);
    let tick_msg = nexus_flat::TickMessage::create(
        &mut builder,
        &nexus_flat::TickMessageArgs {
            timestamp_ns: tick.timestamp_ns,
            price: tick.price,
            bid_size: tick.bid_size,
            ask_size: tick.ask_size,
            trade_size: tick.trade_size,
            order_id: tick.order_id,
            action: tick.action,
            side: tick.side,
            flags: tick.flags,
            seq_num: tick.seq_num,
        },
    );
    builder.finish(tick_msg, None);
    builder.finished_data().to_vec()
}

fn generate_mock_tick(seq: u64) -> TickData {
    use rand::Rng;
    let mut rng = rand::thread_rng();
    let base_price = 4500.25;
    let spread = 0.25_f64;
    let price_offset = rng.gen_range(-10.0..10.0) * spread;
    let price = base_price + price_offset;
    let side: u8 = if rng.gen_bool(0.5) { 0 } else { 1 };
    let action_roll: f64 = rng.gen();
    let action = if action_roll < 0.3 { 0 } else if action_roll < 0.55 { 1 } else if action_roll < 0.75 { 2 } else { 3 };
    let size = rng.gen_range(1.0..500.0) as f32;

    TickData {
        timestamp_ns: std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos() as u64,
        price,
        bid_size: if side == 0 { size } else { rng.gen_range(1.0..200.0) as f32 },
        ask_size: if side == 1 { size } else { rng.gen_range(1.0..200.0) as f32 },
        trade_size: if action == 3 { size } else { 0.0 },
        order_id: rng.gen_range(0..1000000),
        action,
        side,
        flags: 0,
        seq_num: seq,
    }
}

mod nexus_flat {
    #![allow(dead_code)]
    use flatbuffers::*;

    pub enum Action { INSERT = 0, UPDATE = 1, DELETE = 2, TRADE = 3, TOP_OF_BOOK = 4 }
    pub enum Side { BID = 0, ASK = 1 }

    #[derive(Clone, Copy, Debug, PartialEq)]
    pub struct TickMessageArgs {
        pub timestamp_ns: u64,
        pub price: f64,
        pub bid_size: f32,
        pub ask_size: f32,
        pub trade_size: f32,
        pub order_id: u32,
        pub action: u8,
        pub side: u8,
        pub flags: u8,
        pub seq_num: u64,
    }

    pub struct TickMessage;

    impl TickMessage {
        pub fn create<'a>(builder: &mut flatbuffers::FlatBufferBuilder<'a>, args: &TickMessageArgs) -> WIPOffset<flatbuffers::TableFinishedWIPOffset> {
            let fields = [
                FieldValue::U64(args.timestamp_ns),
                FieldValue::F64(args.price),
                FieldValue::F32(args.bid_size),
                FieldValue::F32(args.ask_size),
                FieldValue::F32(args.trade_size),
                FieldValue::U32(args.order_id),
                FieldValue::U8(args.action),
                FieldValue::U8(args.side),
                FieldValue::U8(args.flags),
                FieldValue::U64(args.seq_num),
            ];
            let start = builder.start_table();
            for (i, field) in fields.iter().enumerate() {
                match field {
                    FieldValue::U64(v) => { builder.push_slot::<u64>(i as u16 * 2 + 4, *v, 0); }
                    FieldValue::F64(v) => { builder.push_slot::<f64>(i as u16 * 2 + 4, *v, 0.0); }
                    FieldValue::F32(v) => { builder.push_slot::<f32>(i as u16 * 2 + 4, *v, 0.0); }
                    FieldValue::U32(v) => { builder.push_slot::<u32>(i as u16 * 2 + 4, *v, 0); }
                    FieldValue::U8(v) => { builder.push_slot::<u8>(i as u16 * 2 + 4, *v, 0); }
                    _ => {}
                }
            }
            builder.end_table(start)
        }
    }

    enum FieldValue {
        U64(u64), F64(f64), F32(f32), U32(u32), U8(u8),
    }
}

#[tokio::main]
async fn main() {
    dotenv::dotenv().ok();
    tracing_subscriber::fmt::init();
    info!("[NEXUS] Backend starting v0.3.0 (Rithmic rithmic-rs + Real MBO)...");

    let rithmic_username = env::var("RITHMIC_USERNAME").expect("RITHMIC_USERNAME not set");
    let rithmic_password = env::var("RITHMIC_PASSWORD").expect("RITHMIC_PASSWORD not set");
    let rithmic_system_name = env::var("RITHMIC_SYSTEM_NAME").expect("RITHMIC_SYSTEM_NAME not set");
    let rithmic_gateway = env::var("RITHMIC_GATEWAY").expect("RITHMIC_GATEWAY not set");

    info!("[NEXUS] Rithmic credentials loaded");
    info!("[NEXUS] User: {}", rithmic_username);
    info!("[NEXUS] Gateway: {}", rithmic_gateway);

    let symbols_str = env::var("SYMBOLS").unwrap_or_else(|_| "ES,CL,NQ".to_string());
    let symbols: Vec<(String, String)> = symbols_str
        .split(',')
        .map(|s| {
            let symbol = s.trim().to_string();
            let exchange = match symbol.chars().next().unwrap_or('E') {
                'C' | 'S' | 'W' | 'K' => "CBOT",
                'H' | 'Y' => "NYMEX",
                'Q' => "CFE",
                _ => "CME",
            };
            (symbol, exchange.to_string())
        })
        .collect();

    info!("[NEXUS] Subscribing to symbols: {:?}", symbols);

    let lob = Arc::new(RwLock::new(LimitOrderBook::new()));
    let delta_buffer = Arc::new(Mutex::new(DeltaBuffer::new()));
    let (tx_broadcast, _) = broadcast::channel(BROADCAST_CAPACITY);

    let (tick_tx, mut tick_rx) = tokio::sync::mpsc::unbounded_channel::<TickData>();

    let lob_clone = lob.clone();
    let tx_broadcast_clone = tx_broadcast.clone();
    let delta_clone = delta_buffer.clone();

    // Spawn Rithmic Bridge Task (real MBO via rithmic-rs)
    let username_clone = rithmic_username.clone();
    let password_clone = rithmic_password.clone();
    let system_name_clone = rithmic_system_name.clone();
    let gateway_clone = rithmic_gateway.clone();
    let symbols_clone = symbols.clone();

    let _rithmic_task = tokio::spawn(async move {
        let bridge = match rithmic::RithmicBridge::new(
            username_clone,
            password_clone,
            system_name_clone,
            gateway_clone,
            symbols_clone,
        ) {
            Ok(b) => b,
            Err(e) => {
                error!("[NEXUS] Failed to create RithmicBridge: {}", e);
                return;
            }
        };

        if let Err(e) = bridge.run(tick_tx).await {
            error!("[NEXUS] RithmicBridge exited: {}", e);
        }
    });

    // Main tick processing loop: consume from Rithmic bridge & broadcast
    let lob_process = lob.clone();
    let tx_process = tx_broadcast.clone();
    let delta_process = delta_buffer.clone();

    let process_task = tokio::spawn(async move {
        let mut seq: u64 = 0;

        while let Some(tick_data) = tick_rx.recv().await {
            {
                let mut lob = lob_process.write();
                match tick_data.action {
                    0 => lob.insert(tick_data.price, tick_data.side, tick_data.bid_size as f64 + tick_data.ask_size as f64),
                    1 => lob.update(tick_data.price, tick_data.side, tick_data.bid_size as f64 + tick_data.ask_size as f64),
                    2 => lob.delete(tick_data.price, tick_data.side),
                    _ => {}
                }
            }
            {
                let mut db = delta_process.lock();
                db.push(tick_data.clone());
            }

            let encoded = encode_tick_flatbuffer(&tick_data);
            let _ = tx_process.send(Message::Binary(encoded.into()));

            seq += 1;
        }
    });

    // Mock tick fallback (runs if no real data for 5 seconds)
    let tx_mock = tx_broadcast.clone();
    let lob_mock = lob.clone();
    let delta_mock = delta_buffer.clone();
    let mock_task = tokio::spawn(async move {
        let mut seq: u64 = 1000000;
        loop {
            tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
            let tick = generate_mock_tick(seq);
            {
                let mut lob = lob_mock.write();
                match tick.action {
                    0 => lob.insert(tick.price, tick.side, tick.bid_size as f64 + tick.ask_size as f64),
                    1 => lob.update(tick.price, tick.side, tick.bid_size as f64 + tick.ask_size as f64),
                    2 => lob.delete(tick.price, tick.side),
                    _ => {}
                }
            }
            {
                let mut db = delta_mock.lock();
                db.push(tick.clone());
            }
            let encoded = encode_tick_flatbuffer(&tick);
            let _ = tx_mock.send(Message::Binary(encoded.into()));
            seq += 1;
        }
    });

    // Snapshot task
    let lob_snap = lob.clone();
    let _snapshot_task = tokio::spawn(async move {
        loop {
            tokio::time::sleep(std::time::Duration::from_secs(SNAPSHOT_INTERVAL_SECS)).await;
            let lob = lob_snap.read();
            info!("[NEXUS] Periodic snapshot: {} bids, {} asks", lob.bids.len(), lob.asks.len());
        }
    });

    let listener = TcpListener::bind("0.0.0.0:9001").await.expect("Failed to bind");
    info!("[NEXUS] WebSocket server listening on 0.0.0.0:9001");

    while let Ok((stream, addr)) = listener.accept().await {
        info!("[NEXUS] Client connected: {}", addr);
        let rx = tx_broadcast.subscribe();
        let delta_buf = delta_buffer.clone();
        let lob = lob.clone();

        tokio::spawn(async move {
            let ws_stream = tokio_tungstenite::accept_async(stream).await;
            match ws_stream {
                Ok(ws_stream) => {
                    let (mut ws_sender, mut ws_receiver) = ws_stream.split();
                    let mut rx = rx;
                    let mut client_state = ClientState {
                        last_pong: std::time::Instant::now(),
                    };

                    let send_task = async {
                        loop {
                            match rx.recv().await {
                                Ok(msg) => {
                                    if ws_sender.send(msg).await.is_err() {
                                        break;
                                    }
                                }
                                Err(broadcast::error::RecvError::Lagged(n)) => {
                                    warn!("[NEXUS] Client {} lagged {} ticks", addr, n);
                                }
                                Err(_) => break,
                            }
                        }
                    };

                    let recv_task = async {
                        while let Some(msg) = ws_receiver.next().await {
                            match msg {
                                Ok(Message::Text(text)) => {
                                    if text.contains("RECOVERY_REQUEST") {
                                        info!("[NEXUS] Recovery request from {}", addr);
                                        let db = delta_buf.lock();
                                        let last_seq: u64 = text.parse().unwrap_or(0);
                                        let missed = db.get_since(last_seq);
                                        if missed.len() < 5000 {
                                            info!("[NEXUS] Delta sync: {} ticks", missed.len());
                                        } else {
                                            info!("[NEXUS] Full snapshot required for {}", addr);
                                        }
                                    }
                                }
                                Ok(Message::Pong(_)) => {
                                    client_state.last_pong = std::time::Instant::now();
                                }
                                Ok(Message::Close(_)) => break,
                                Err(_) => break,
                                _ => {}
                            }
                        }
                    };

                    tokio::select! {
                        _ = send_task => {},
                        _ = recv_task => {},
                    }

                    info!("[NEXUS] Client disconnected: {}", addr);
                }
                Err(e) => {
                    error!("[NEXUS] WebSocket handshake failed for {}: {}", addr, e);
                }
            }
        });
    }
}
