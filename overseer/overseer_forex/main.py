"""
OVERSEER Forex Edition - Main Entry Point
Toxic Flow Arbitrage Engine for MT4/MT5
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import os

# Load environment
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from hub.state_manager import StateManager
from hub.telegram_alert import TelegramBot
from hub.zmq_receiver import ZMQReceiver
from hub.mt5_client import MT5Client
from hub.signal_processor import SignalProcessor
from hub.trade_manager import TradeManager
from gates.gate_engine import GateEngine
from utils.logger import setup_logger
from utils.journal import TradeJournal

# Setup logging
logger = setup_logger()


class OverseerEngine:
    """Main orchestrator for OVERSEER Forex trading system."""
    
    def __init__(self):
        self.running = False
        self.state = StateManager()
        self.telegram = TelegramBot()
        self.zmq = ZMQReceiver()
        self.mt5 = MT5Client()
        self.gates = GateEngine()
        self.processor = SignalProcessor(self.gates)
        self.trade_manager = TradeManager(self.state, self.mt5)
        self.journal = TradeJournal()
        
    async def start(self):
        """Initialize and start all components."""
        logger.info("=" * 60)
        logger.info("OVERSEER FOREX - Starting...")
        logger.info("=" * 60)
        
        # Circuit breaker check (Gate I)
        if self.state.get('circuit_breaker'):
            msg = "[GATE I] CIRCUIT BREAKER ACTIVE - System halted due to consecutive losses"
            logger.warning(msg)
            await self.telegram.send_alert(f"⚠️ OVERSEER HALTED\n\n{msg}\n\nReset state.json to resume.")
            return
        
        # Weekly circuit breaker check
        if self.state.get('weekly_circuit_breaker'):
            msg = "[GATE I] WEEKLY CIRCUIT BREAKER ACTIVE - Max weekly loss reached"
            logger.warning(msg)
            await self.telegram.send_alert(f"⚠️ OVERSEER HALTED\n\n{msg}\n\nWait for next week or reset state.json.")
            return
        
        # Connect to MT5
        if not await self.mt5.connect():
            logger.error("Failed to connect to MT5. Exiting.")
            await self.telegram.send_alert("❌ OVERSEER FAILED TO START\n\nMT5 connection failed.")
            return
        
        # Start ZMQ receiver
        await self.zmq.start(self._on_signal)
        
        # Send startup notification
        account = self.mt5.get_account_info()
        startup_msg = (
            f"🟢 OVERSEER FOREX ONLINE\n\n"
            f"Account: {account.get('login', 'N/A')}\n"
            f"Balance: ${account.get('balance', 0):.2f}\n"
            f"Equity: ${account.get('equity', 0):.2f}\n"
            f"Daily Trades: {self.state.get('daily_trade_count', 0)}/{os.getenv('MAX_DAILY_TRADES', 3)}\n"
            f"Circuit Breaker: {'🔴 ACTIVE' if self.state.get('circuit_breaker') else '🟢 CLEAR'}\n\n"
            f"Monitoring 10 pairs for signals..."
        )
        await self.telegram.send_alert(startup_msg)
        
        self.running = True
        logger.info("OVERSEER started successfully")
        
        # Main loop
        while self.running:
            await asyncio.sleep(1)
            
    async def _on_signal(self, raw_signal: dict):
        """Process incoming signal from C# Scanner."""
        try:
            signal_time = datetime.utcnow()
            logger.info(f"[SIGNAL] Received from Scanner: {raw_signal.get('asset', 'UNKNOWN')}")
            
            # Process through all gates
            result = await self.processor.process(raw_signal)
            
            if not result['passed']:
                logger.info(f"[REJECTED] Gate failure: {result['failed_gate']}")
                self.journal.log_rejection(raw_signal, result)
                return
            
            # Calculate position sizing (Gate L)
            position_info = self.trade_manager.calculate_position(
                result['signal'],
                result['sl_pips'],
                self.mt5.get_account_info()
            )
            
            # Update signal with position info
            result['signal']['lot_size'] = position_info['lot_size']
            result['signal']['risk_amount'] = position_info['risk_amount']
            result['signal']['sl_price'] = position_info['sl_price']
            result['signal']['tp1_price'] = position_info['tp1_price']
            result['signal']['tp2_price'] = position_info['tp2_price']
            result['signal']['rr_ratio'] = position_info['rr_ratio']
            
            # Send Telegram alert
            await self.telegram.send_signal_alert(result['signal'])
            
            # Log to journal
            trade_id = self.journal.log_signal(result['signal'])
            result['signal']['trade_id'] = trade_id
            
            # Execute trade (if auto-execute enabled)
            if os.getenv('AUTO_EXECUTE', 'false').lower() == 'true':
                execution = await self.trade_manager.execute_trade(result['signal'])
                if execution['success']:
                    await self.telegram.send_alert(f"✅ Trade executed: {result['signal']['asset']} {result['signal']['direction']}")
                else:
                    await self.telegram.send_alert(f"❌ Trade failed: {execution['error']}")
            
            # Update state
            self.state.increment('daily_trade_count')
            self.state.set('last_signal_time', signal_time.isoformat())
            
        except Exception as e:
            logger.error(f"Error processing signal: {e}", exc_info=True)
            
    async def stop(self):
        """Graceful shutdown."""
        logger.info("Shutting down OVERSEER...")
        self.running = False
        await self.zmq.stop()
        await self.mt5.disconnect()
        await self.telegram.send_alert("🔴 OVERSEER OFFLINE")
        

def main():
    """Main entry point."""
    engine = OverseerEngine()
    
    def signal_handler(sig, frame):
        asyncio.create_task(engine.stop())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        asyncio.run(engine.start())
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("OVERSEER stopped")


if __name__ == "__main__":
    main()
