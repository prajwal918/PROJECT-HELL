use std::sync::Arc;
use parking_lot::Mutex;
use std::collections::VecDeque;
use tokio::sync::broadcast;
use tokio_tungstenite::tungstenite::Message;
use tracing::{info, warn};

const DELTA_BUFFER_CAPACITY: usize = 10000;
const HEARTBEAT_INTERVAL_MS: u64 = 1000;
const HEARTBEAT_TIMEOUT_MS: u64 = 2000;

#[derive(Clone, Debug)]
pub struct TickData {
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

pub struct DeltaBuffer {
    buffer: VecDeque<TickData>,
}

impl DeltaBuffer {
    pub fn new() -> Self {
        Self {
            buffer: VecDeque::with_capacity(DELTA_BUFFER_CAPACITY),
        }
    }

    pub fn push(&mut self, tick: TickData) {
        if self.buffer.len() >= DELTA_BUFFER_CAPACITY {
            self.buffer.pop_front();
        }
        self.buffer.push_back(tick);
    }

    pub fn get_since(&self, seq_num: u64) -> Vec<&TickData> {
        self.buffer.iter().filter(|t| t.seq_num > seq_num).collect()
    }

    pub fn len(&self) -> usize {
        self.buffer.len()
    }

    pub fn is_empty(&self) -> bool {
        self.buffer.is_empty()
    }

    pub fn latest_seq(&self) -> u64 {
        self.buffer.back().map(|t| t.seq_num).unwrap_or(0)
    }
}

pub struct RecoveryResponse {
    pub recovery_type: RecoveryType,
    pub ticks: Vec<TickData>,
}

#[derive(Debug, PartialEq)]
pub enum RecoveryType {
    DeltaSync,
    FullSnapshot,
}

pub fn handle_recovery_request(
    delta_buffer: &Arc<Mutex<DeltaBuffer>>,
    last_seq_num: u64,
) -> RecoveryResponse {
    let db = delta_buffer.lock();
    let current_seq = db.latest_seq();
    let gap = current_seq.saturating_sub(last_seq_num);

    if gap < 5000 && !db.is_empty() {
        let missed = db.get_since(last_seq_num);
        let ticks: Vec<TickData> = missed.iter().map(|t| (*t).clone()).collect();
        info!(
            "[NEXUS] Delta sync: sending {} ticks (seq {} to {})",
            ticks.len(),
            last_seq_num,
            current_seq
        );
        RecoveryResponse {
            recovery_type: RecoveryType::DeltaSync,
            ticks,
        }
    } else {
        warn!(
            "[NEXUS] Gap too large ({}), full snapshot required",
            gap
        );
        RecoveryResponse {
            recovery_type: RecoveryType::FullSnapshot,
            ticks: Vec::new(),
        }
    }
}

pub struct HeartbeatMonitor {
    last_pong_ms: u64,
    timeout_ms: u64,
}

impl HeartbeatMonitor {
    pub fn new(timeout_ms: u64) -> Self {
        Self {
            last_pong_ms: 0,
            timeout_ms,
        }
    }

    pub fn record_pong(&mut self, now_ms: u64) {
        self.last_pong_ms = now_ms;
    }

    pub fn is_alive(&self, now_ms: u64) -> bool {
        if self.last_pong_ms == 0 {
            return true;
        }
        now_ms - self.last_pong_ms < self.timeout_ms
    }

    pub fn should_ping(&self, now_ms: u64) -> bool {
        if self.last_pong_ms == 0 {
            return true;
        }
        now_ms - self.last_pong_ms >= HEARTBEAT_INTERVAL_MS
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_delta_buffer_push_eviction() {
        let mut buf = DeltaBuffer::new();
        for i in 0..DELTA_BUFFER_CAPACITY + 100 {
            buf.push(TickData {
                timestamp_ns: 0,
                price: 4500.0,
                bid_size: 100.0,
                ask_size: 0.0,
                trade_size: 0.0,
                order_id: 0,
                action: 0,
                side: 0,
                flags: 0,
                seq_num: i as u64,
            });
        }
        assert_eq!(buf.len(), DELTA_BUFFER_CAPACITY);
        let latest = buf.latest_seq();
        assert_eq!(latest, (DELTA_BUFFER_CAPACITY + 100 - 1) as u64);
    }

    #[test]
    fn test_recovery_delta_sync() {
        let db = Arc::new(Mutex::new(DeltaBuffer::new()));
        {
            let mut buf = db.lock();
            for i in 0..100 {
                buf.push(TickData {
                    timestamp_ns: 0, price: 4500.0, bid_size: 100.0,
                    ask_size: 0.0, trade_size: 0.0, order_id: 0,
                    action: 0, side: 0, flags: 0, seq_num: i,
                });
            }
        }
        let result = handle_recovery_request(&db, 90);
        assert_eq!(result.recovery_type, RecoveryType::DeltaSync);
        assert_eq!(result.ticks.len(), 9);
    }

    #[test]
    fn test_heartbeat_monitor() {
        let mut monitor = HeartbeatMonitor::new(2000);
        assert!(monitor.is_alive(0));
        assert!(monitor.should_ping(0));
        monitor.record_pong(1000);
        assert!(monitor.is_alive(2500));
        assert!(!monitor.is_alive(3500));
    }
}
