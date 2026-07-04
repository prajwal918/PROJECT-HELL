use std::time::{SystemTime, UNIX_EPOCH};
use rithmic_rs::{
    RithmicConfig, RithmicEnv, ConnectStrategy, RithmicTickerPlant,
    rti::messages::RithmicMessage,
    rti::DepthByOrder,
};
use tracing::{info, warn, error};

const MBO_UPDATE_TYPE_NEW: i32 = 0;
const MBO_UPDATE_TYPE_CHANGE: i32 = 1;
const MBO_UPDATE_TYPE_DELETE: i32 = 2;
const MBO_UPDATE_TYPE_ORDER_BOOK_CLEAR: i32 = 9;

const MBO_TRANSACTION_TYPE_BID: i32 = 0;
const MBO_TRANSACTION_TYPE_ASK: i32 = 1;

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

pub struct RithmicBridge {
    config: RithmicConfig,
    symbols: Vec<(String, String)>,
}

impl RithmicBridge {
    pub fn new(
        username: String,
        password: String,
        system_name: String,
        gateway: String,
        symbols: Vec<(String, String)>,
    ) -> Result<Self, Box<dyn std::error::Error + Send + Sync>> {
        let config = RithmicConfig::builder(RithmicEnv::Demo)
            .url(gateway.clone())
            .beta_url(gateway)
            .user(username)
            .password(password)
            .system_name(system_name)
            .app_name("pojd:NEXUS_FLOW".to_string())
            .app_version("3.0.0".to_string())
            .build()?;

        Ok(Self { config, symbols })
    }

    pub async fn run(
        self,
        tx: tokio::sync::mpsc::UnboundedSender<TickData>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        loop {
            info!("[RITHMIC] Connecting Ticker Plant via rithmic-rs...");

            let plant = match RithmicTickerPlant::connect(&self.config, ConnectStrategy::Retry).await {
                Ok(p) => p,
                Err(e) => {
                    error!("[RITHMIC] Failed to connect: {}", e);
                    tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
                    continue;
                }
            };

            let mut handle = plant.get_handle();

            match handle.login().await {
                Ok(_) => info!("[RITHMIC] Authenticated to Ticker Plant"),
                Err(e) => {
                    error!("[RITHMIC] Login failed: {}", e);
                    continue;
                }
            }

            for (symbol, exchange) in &self.symbols {
                match handle.subscribe(symbol, exchange).await {
                    Ok(_) => info!("[RITHMIC] Subscribed to {}@{}", symbol, exchange),
                    Err(e) => warn!("[RITHMIC] Failed to subscribe {}@{}: {}", symbol, exchange, e),
                }
            }

            info!("[RITHMIC] Streaming market data...");

            loop {
                match handle.subscription_receiver.recv().await {
                    Ok(update) => {
                        if let Some(err) = &update.error {
                            if err.is_connection_issue() {
                                error!("[RITHMIC] Connection issue: {}", err);
                                break;
                            }
                            warn!("[RITHMIC] Update error: {}", err);
                            continue;
                        }

                        match update.message {
                            RithmicMessage::DepthByOrder(dbo) => {
                                self.process_depth_by_order(&dbo, &tx);
                            }
                            RithmicMessage::BestBidOffer(bbo) => {
                                self.process_bbo(&bbo, &tx);
                            }
                            RithmicMessage::LastTrade(trade) => {
                                self.process_last_trade(&trade, &tx);
                            }
                            RithmicMessage::OrderBook(ob) => {
                                self.process_order_book(&ob, &tx);
                            }
                            RithmicMessage::HeartbeatTimeout => {
                                error!("[RITHMIC] Heartbeat timeout - reconnecting");
                                break;
                            }
                            RithmicMessage::ConnectionError => {
                                error!("[RITHMIC] Connection error - reconnecting");
                                break;
                            }
                            RithmicMessage::ForcedLogout(_) => {
                                error!("[RITHMIC] Forced logout - reconnecting");
                                break;
                            }
                            _ => {}
                        }
                    }
                    Err(e) => {
                        error!("[RITHMIC] Channel error: {}", e);
                        break;
                    }
                }
            }

            info!("[RITHMIC] Reconnecting in 5s...");
            tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
        }
    }

    fn now_ns() -> u64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64
    }

    fn process_depth_by_order(&self, dbo: &DepthByOrder, tx: &tokio::sync::mpsc::UnboundedSender<TickData>) {
        let ts = Self::now_ns();
        let symbol = dbo.symbol();
        let exchange = dbo.exchange();

        let prices = &dbo.depth_price;
        let sizes = &dbo.depth_size;
        let priorities = &dbo.depth_order_priority;
        let order_ids = &dbo.exchange_order_id;
        let update_types = &dbo.update_type;
        let transaction_types = &dbo.transaction_type;

        let count = prices.len().min(sizes.len()).min(priorities.len());

        for i in 0..count {
            let price = prices[i];
            let size = sizes[i] as f32;
            let order_priority = priorities[i];
            let order_id = if i < order_ids.len() {
                order_ids[i].parse::<u32>().unwrap_or(0)
            } else {
                order_priority as u32
            };

            let update_type = if i < update_types.len() { update_types[i] } else { MBO_UPDATE_TYPE_NEW };
            let transaction_type = if i < transaction_types.len() { transaction_types[i] } else { MBO_TRANSACTION_TYPE_BID };

            let action = match update_type {
                MBO_UPDATE_TYPE_NEW => 0,
                MBO_UPDATE_TYPE_CHANGE => 1,
                MBO_UPDATE_TYPE_DELETE => 2,
                MBO_UPDATE_TYPE_ORDER_BOOK_CLEAR => 2,
                _ => 0,
            };

            let side = match transaction_type {
                MBO_TRANSACTION_TYPE_BID => 0,
                MBO_TRANSACTION_TYPE_ASK => 1,
                _ => 0,
            };

            let tick = TickData {
                timestamp_ns: ts,
                price,
                bid_size: if side == 0 { size } else { 0.0 },
                ask_size: if side == 1 { size } else { 0.0 },
                trade_size: 0.0,
                order_id,
                action,
                side,
                flags: 0,
                seq_num: dbo.sequence_number(),
            };

            let _ = tx.send(tick);
        }

        if count > 0 {
            info!(
                "[RITHMIC] MBO: {} {} {} orders for {}@{}",
                count,
                if count == 1 { "order" } else { "orders" },
                match update_types.first().copied().unwrap_or(0) {
                    0 => "NEW",
                    1 => "CHANGE",
                    2 => "DELETE",
                    _ => "UNKNOWN",
                },
                symbol,
                exchange,
            );
        }
    }

    fn process_bbo(
        &self,
        bbo: &rithmic_rs::rti::BestBidOffer,
        tx: &tokio::sync::mpsc::UnboundedSender<TickData>,
    ) {
        let ts = Self::now_ns();
        let bid_price = bbo.bid_price();
        let ask_price = bbo.ask_price();
        let bid_size = bbo.bid_size() as f32;
        let ask_size = bbo.ask_size() as f32;

        if bid_price > 0.0 {
            let _ = tx.send(TickData {
                timestamp_ns: ts,
                price: bid_price,
                bid_size,
                ask_size: 0.0,
                trade_size: 0.0,
                order_id: 0,
                action: 4,
                side: 0,
                flags: 0,
                seq_num: bbo.ssboe() as u64,
            });
        }

        if ask_price > 0.0 {
            let _ = tx.send(TickData {
                timestamp_ns: ts,
                price: ask_price,
                bid_size: 0.0,
                ask_size,
                trade_size: 0.0,
                order_id: 0,
                action: 4,
                side: 1,
                flags: 0,
                seq_num: bbo.ssboe() as u64 + 1,
            });
        }
    }

    fn process_last_trade(
        &self,
        trade: &rithmic_rs::rti::LastTrade,
        tx: &tokio::sync::mpsc::UnboundedSender<TickData>,
    ) {
        let ts = Self::now_ns();
        let price = trade.trade_price();
        let size = trade.trade_size() as f32;
        let aggressor = trade.aggressor.unwrap_or(0) as u8;

        if price > 0.0 && size > 0.0 {
            let _ = tx.send(TickData {
                timestamp_ns: ts,
                price,
                bid_size: 0.0,
                ask_size: 0.0,
                trade_size: size,
                order_id: 0,
                action: 3,
                side: aggressor as u8,
                flags: 0,
                seq_num: trade.ssboe() as u64,
            });
        }
    }

    fn process_order_book(
        &self,
        ob: &rithmic_rs::rti::OrderBook,
        tx: &tokio::sync::mpsc::UnboundedSender<TickData>,
    ) {
        let ts = Self::now_ns();

        for i in 0..ob.bid_price.len() {
            let price = ob.bid_price[i];
            let size = ob.bid_size.get(i).copied().unwrap_or(0) as f32;
            let _ = tx.send(TickData {
                timestamp_ns: ts,
                price,
                bid_size: size,
                ask_size: 0.0,
                trade_size: 0.0,
                order_id: 0,
                action: 0,
                side: 0,
                flags: 0,
                seq_num: ob.ssboe() as u64,
            });
        }

        for i in 0..ob.ask_price.len() {
            let price = ob.ask_price[i];
            let size = ob.ask_size.get(i).copied().unwrap_or(0) as f32;
            let _ = tx.send(TickData {
                timestamp_ns: ts,
                price,
                bid_size: 0.0,
                ask_size: size,
                trade_size: 0.0,
                order_id: 0,
                action: 0,
                side: 1,
                flags: 0,
                seq_num: ob.ssboe() as u64 + 1,
            });
        }
    }
}
