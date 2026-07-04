from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

if not hasattr(asyncio, "to_thread"):
    import functools
    async def _to_thread(func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
    asyncio.to_thread = _to_thread

from dotenv import load_dotenv

load_dotenv()

from core.hub_listener import start_udp_listener
from core.oanda_price_feed import poll_oanda_prices
from core.symbol_mapper import annotate_tick
from core.zmq_bridge import start_zmq_subscriber
from database.setup_db import DB_PATH, check_halt_status, init_db
from engine_logic.gates.gate_registry import GateRegistry
from execution.dynamic_exit import DynamicExitManager
from execution.mt5_executor import connect_mt5, execute_trade, kelly_lot_size, modify_sl, shutdown_mt5, MT5ConnectionManager
from ml.load_model import predict_trade_quality, reload_model
from ml.l3_scorer import L3RealTimeScorer
from ml.signal_logger import log_signal, update_mid_price, check_outcomes, mark_signal_closed, load_pending_from_db
from ml.framework_scorer import aggregate_framework_scores
from ml.dynamic_pair_selector import (
    DynamicPairSelector,
    STATUS_TRADE_CANDIDATE,
    STATUS_TRADE_CANDIDATE_SIGNAL_ONLY,
    STATUS_WATCHLIST,
)

from core.candle_aggregator import CandleAggregator
from config.instrument_config import InstrumentConfig
from core.dxy_calculator import DXYCalculator
from core.risk_regime import RiskRegimeClassifier
from core.telegram_alerts import TelegramAlerter
from engine_logic.gates.gate_continuation import PostReleaseContinuationFilter
from execution.partial_close import PartialCloseManager
from execution.trade_tracker import TradeTracker
from tools.calendar_scraper import scrape_calendar
from tools.options_iv_scraper import scrape_options_iv, get_skew_score, get_rr_25d
from tools.fred_scraper import scrape_fred
from tools.ecb_scraper import scrape_ecb
from tools.finnhub_scraper import scrape_finnhub
from ml.fundamental_bias import compute_fundamental_bias, get_fundamental_bias_adjustment
from core.dom_quality import DOMQualityChecker
from core.currency_exposure import CurrencyExposureTracker
from core.risk_engine import RiskEngine
from core.latency_tracker import LatencyTracker
from ml.drift_monitor import DriftMonitor
from ml.order_book_engine import OrderBookEngine
from ml.per_symbol_model import PerSymbolModelManager
from execution.execution_quality import ExecutionQualityLogger
from execution.trade_replay import TradeReplay
from execution.paper_trading import PaperTradingEngine
from execution.oanda_executor import (
    connect as oanda_connect,
    execute_trade as oanda_execute_trade,
    close_trade as oanda_close_trade,
    modify_sl as oanda_modify_sl,
    get_account_balance as oanda_get_balance,
    get_open_positions as oanda_get_positions,
    is_connected as oanda_is_connected,
    shutdown as oanda_shutdown,
    map_symbol as oanda_map_symbol,
)
from ml.vpin_toxicity import ToxicityEngine
from ml.ofi_microstructure import OFIManager
from core.regime_intelligence import RegimeIntelEngine
from execution.execution_algos import ExecutionAlgoEngine
from core.portfolio_risk import PortfolioRiskEngine
from core.cross_asset import CrossAssetEngine
from tools.cb_nlp import CentralBankNLP
from core.network_analysis import NetworkEngine
from ml.self_supervised import SelfSupervisedEngine
from core.vol_surface import VolSurfaceManager
from ml.pairs_statarb import PairsEngine
from ml.sequence_core import SequenceCore
from ml.xai_explainer import XAIExplainer
from database.vector_memory import VectorMemory
from execution.rl_brain import TabularRLBrain
from ml.causal_engine import CausalEngine
from ml.attention_gate import AttentionGateWeighting
from ml.legendary_mode import LegendaryMode, legendary_mode
from core.killzone_timer import get_killzone_quality, get_session_name, get_killzone_summary
from core.futures_calendar import get_roll_status, get_all_roll_statuses
from core.spread_intelligence import get_spread_zscore
from core.psychological_levels import classify_level, get_stop_hunt_probability
from core.session_levels import SessionLevels
from execution.scale_in_engine import ScaleInEngine
from core.dead_zone import is_dead_zone
from core.daily_bias import daily_bias
from core.session_multiplier import get_session_multiplier
from ml.time_heatmap import time_heatmap
from core.live_edge_tracker import live_edge_tracker
from core.system_health import should_skip_entry, get_system_health
from ml.score_calibration import score_calibrator
from core.entry_sniper import entry_sniper
from core.structural_sl import structural_sl
from core.london_fix import london_fix
from core.spread_velocity import spread_velocity
from core.tape_acceleration import tape_acceleration
from ml.hurst_exponent import hurst_exponent
from core.bid_ask_flip import bid_ask_flip
from core.flash_crash_detector import flash_crash_detector
from core.system_state_machine import system_state_machine, SystemState
from execution.anti_martingale import anti_martingale
from core.signal_frequency import signal_frequency
from ml.seasonal_patterns import seasonal_patterns
from core.quote_stuffing import quote_stuffing_detector
from core.micro_regime import micro_regime_shift
from core.drawdown_velocity import drawdown_velocity
from ml.gate_combos import gate_combo_memory
from ml.layer_performance import layer_performance_tracker
from core.initial_balance import initial_balance
from core.mm_spread_behavior import mm_spread_behavior
from core.kalman_tracker import kalman_tracker
from tools.retail_sentiment import retail_sentiment
from tools.pcr_scraper import pcr_scraper
from core.bond_signal import bond_signal
from core.equity_lead import equity_lead
from tools.surprise_index import surprise_index
from ml.wavelet_decomp import wavelet_decomp
from ml.value_migration import value_migration
from ml.bayesian_updater import bayesian_updater
from core.anchored_vwap import anchored_vwap
from ml.contrastive_learner import contrastive_learner
from tools.gamma_scraper import gamma_scraper
from tools.barrier_scraper import barrier_scraper
from tools.dot_plot_analyzer import dot_plot_analyzer
from core.cb_divergence import cb_divergence
from core.carry_monitor import carry_monitor
from tools.political_risk import political_risk
from ml.currency_network import currency_network
from ml.spillover import spillover_index
from ml.tda_patterns import tda_patterns
from ml.online_learner import online_learner
from ml.bandit_params import bandit_params
from ml.rl_exit_agent import rl_exit_agent
from ml.ms_garch import ms_garch
from ml.counterfactual import counterfactual_analyzer
from ml.causal_importance import causal_importance
from core.es_risk import es_risk
from core.ruin_calc import ruin_calc
from ml.hawkes_process import hawkes_process
from ml.disposition_effect import disposition_effect
from ml.anchoring_effect import anchoring_effect
from ml.mutual_info_audit import mutual_info_audit
from ml.signal_entropy import signal_entropy
from ml.footprint_patterns import footprint_patterns
from core.news_velocity import news_velocity
from core.broker_spread_comparison import broker_spread_comparison
from core.poor_high_low import poor_high_low
from core.network_jitter_monitor import network_jitter_monitor
from core.swap_anomaly import swap_anomaly
from tools.cot_crowding import get_crowding_bonus
from tools.yahoo_news_scraper import scrape_yahoo_news, get_usd_sentiment as yahoo_usd_sentiment
from tools.cboe_vol_scraper import scrape_cboe_vol, get_symbol_iv, get_symbol_skew, is_high_vol_environment
from tools.cot_reports_scraper import scrape_cot_reports, get_crowding_bonus as cot_lib_crowding_bonus, get_zscore as cot_lib_zscore
from tools.fxssi_web_scraper import scrape_fxssi_sentiment, get_buy_pct as fxssi_buy_pct, is_crowded as fxssi_is_crowded, get_fade_bonus as fxssi_fade_bonus

_log_dir = Path(__file__).resolve().parent / "logs"
_log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_log_dir / "overseer.log", encoding="utf-8"),
    ],
)
LOGGER = logging.getLogger("overseer.main")

ZMQ_ENABLED = os.getenv("ZMQ_ENABLED", "false").lower() == "true"
DYNAMIC_EXIT_ENABLED = os.getenv("DYNAMIC_EXIT_ENABLED", "true").lower() == "true"
DASHBOARD_ENABLED = os.getenv("DASHBOARD_ENABLED", "true").lower() == "true"
MT5_ENABLED = os.getenv("MT5_ENABLED", "false").lower() == "true"
AUTO_EXECUTE = os.getenv("AUTO_EXECUTE", "true").lower() == "true"
GATE_EVAL_INTERVAL = int(os.getenv("GATE_EVAL_INTERVAL", "1"))
AUTORETRAIN_TRADES = int(os.getenv("AUTORETRAIN_TRADES", "50"))
VANGUARD_AUTO_START = os.getenv("VANGUARD_AUTO_START", "true").lower() == "true"
VANGUARD_ROOT = Path(os.getenv("VANGUARD_ROOT", "/home/jogi999/PROJECT HELL/vanguard"))
VANGUARD_PYTHON = os.getenv(
    "VANGUARD_PYTHON",
    str(VANGUARD_ROOT / "venv" / "bin" / "python"),
)
VANGUARD_CLI = os.getenv(
    "VANGUARD_CLI",
    str(VANGUARD_ROOT / "cli" / "vanguard_cli.py"),
)
VPIN_ENABLED = os.getenv("VPIN_ENABLED", "true").lower() == "true"
OFI_ENABLED = os.getenv("OFI_ENABLED", "true").lower() == "true"
REGIME_INTEL_ENABLED = os.getenv("REGIME_INTEL_ENABLED", "true").lower() == "true"
CROSS_ASSET_ENABLED = os.getenv("CROSS_ASSET_ENABLED", "true").lower() == "true"
CB_NLP_ENABLED = os.getenv("CB_NLP_ENABLED", "true").lower() == "true"
VOL_SURFACE_ENABLED = os.getenv("VOL_SURFACE_ENABLED", "true").lower() == "true"
PAIRS_STAT_ENABLED = os.getenv("PAIRS_STAT_ENABLED", "true").lower() == "true"
NETWORK_ENABLED = os.getenv("NETWORK_ENABLED", "true").lower() == "true"
SELF_SUPERVISED_ENABLED = os.getenv("SELF_SUPERVISED_ENABLED", "true").lower() == "true"
SEQUENCE_CORE_ENABLED = os.getenv("SEQUENCE_CORE_ENABLED", "true").lower() == "true"
XAI_ENABLED = os.getenv("XAI_ENABLED", "true").lower() == "true"
VECTOR_MEMORY_ENABLED = os.getenv("VECTOR_MEMORY_ENABLED", "true").lower() == "true"
RL_BRAIN_ENABLED = os.getenv("RL_BRAIN_ENABLED", "true").lower() == "true"
CAUSAL_ENGINE_ENABLED = os.getenv("CAUSAL_ENGINE_ENABLED", "true").lower() == "true"
ATTENTION_GATE_ENABLED = os.getenv("ATTENTION_GATE_ENABLED", "true").lower() == "true"
EXEC_ALGO_ENABLED = os.getenv("EXEC_ALGO_ENABLED", "true").lower() == "true"
PORTFOLIO_RISK_ENABLED = os.getenv("PORTFOLIO_RISK_ENABLED", "true").lower() == "true"
SEQUENCE_INFERENCE_INTERVAL = int(os.getenv("SEQUENCE_INFERENCE_INTERVAL", "10"))
XAI_COMPUTE_INTERVAL = int(os.getenv("XAI_COMPUTE_INTERVAL", "50"))
CROSS_ASSET_INTERVAL = int(os.getenv("CROSS_ASSET_INTERVAL", "100"))
NETWORK_INTERVAL = int(os.getenv("NETWORK_INTERVAL", "200"))
PAIRS_STAT_INTERVAL = int(os.getenv("PAIRS_STAT_INTERVAL", "500"))
SELF_SUPERVISED_INTERVAL = int(os.getenv("SELF_SUPERVISED_INTERVAL", "1000"))
CAUSAL_ENGINE_INTERVAL = int(os.getenv("CAUSAL_ENGINE_INTERVAL", "5000"))
VPIN_TOXIC_THRESHOLD = float(os.getenv("VPIN_TOXIC_THRESHOLD", "0.70"))
VPIN_EXTREME_THRESHOLD = float(os.getenv("VPIN_EXTREME_THRESHOLD", "0.90"))
LEGENDARY_MODE_ENABLED = os.getenv("LEGENDARY_MODE_ENABLED", "true").lower() == "true"
SCALE_IN_ENABLED = os.getenv("SCALE_IN_ENABLED", "true").lower() == "true"
DEAD_ZONE_ENABLED = os.getenv("DEAD_ZONE_ENABLED", "true").lower() == "true"
DAILY_BIAS_ENABLED = os.getenv("DAILY_BIAS_ENABLED", "true").lower() == "true"
SESSION_MULTIPLIER_ENABLED = os.getenv("SESSION_MULTIPLIER_ENABLED", "true").lower() == "true"
TIME_HEATMAP_ENABLED = os.getenv("TIME_HEATMAP_ENABLED", "true").lower() == "true"
LIVE_EDGE_TRACKER_ENABLED = os.getenv("LIVE_EDGE_TRACKER_ENABLED", "true").lower() == "true"
SYSTEM_HEALTH_FILTER_ENABLED = os.getenv("SYSTEM_HEALTH_FILTER_ENABLED", "true").lower() == "true"
SCORE_CALIBRATION_ENABLED = os.getenv("SCORE_CALIBRATION_ENABLED", "true").lower() == "true"
ENTRY_SNIPER_ENABLED = os.getenv("ENTRY_SNIPER_ENABLED", "true").lower() == "true"
STRUCTURAL_SL_ENABLED = os.getenv("STRUCTURAL_SL_ENABLED", "true").lower() == "true"
LONDON_FIX_ENABLED = os.getenv("LONDON_FIX_ENABLED", "true").lower() == "true"
SPREAD_VELOCITY_ENABLED = os.getenv("SPREAD_VELOCITY_ENABLED", "true").lower() == "true"
TAPE_ACCELERATION_ENABLED = os.getenv("TAPE_ACCELERATION_ENABLED", "true").lower() == "true"
HURST_EXPONENT_ENABLED = os.getenv("HURST_EXPONENT_ENABLED", "true").lower() == "true"
BID_ASK_FLIP_ENABLED = os.getenv("BID_ASK_FLIP_ENABLED", "true").lower() == "true"
FLASH_CRASH_DETECTOR_ENABLED = os.getenv("FLASH_CRASH_DETECTOR_ENABLED", "true").lower() == "true"
SYSTEM_STATE_MACHINE_ENABLED = os.getenv("SYSTEM_STATE_MACHINE_ENABLED", "true").lower() == "true"
ANTI_MARTINGALE_ENABLED = os.getenv("ANTI_MARTINGALE_ENABLED", "true").lower() == "true"
SIGNAL_FREQUENCY_ENABLED = os.getenv("SIGNAL_FREQUENCY_ENABLED", "true").lower() == "true"
SEASONAL_PATTERNS_ENABLED = os.getenv("SEASONAL_PATTERNS_ENABLED", "true").lower() == "true"
DOM_QUOTE_STUFFING_ENABLED = os.getenv("DOM_QUOTE_STUFFING_ENABLED", "true").lower() == "true"
MICRO_REGIME_SHIFT_ENABLED = os.getenv("MICRO_REGIME_SHIFT_ENABLED", "true").lower() == "true"
DRAWDOWN_VELOCITY_ENABLED = os.getenv("DRAWDOWN_VELOCITY_ENABLED", "true").lower() == "true"
GATE_COMBOS_ENABLED = os.getenv("GATE_COMBOS_ENABLED", "true").lower() == "true"
LAYER_PERFORMANCE_ENABLED = os.getenv("LAYER_PERFORMANCE_ENABLED", "true").lower() == "true"
INITIAL_BALANCE_ENABLED = os.getenv("INITIAL_BALANCE_ENABLED", "true").lower() == "true"
MM_SPREAD_BEHAVIOR_ENABLED = os.getenv("MM_SPREAD_BEHAVIOR_ENABLED", "true").lower() == "true"
KALMAN_TRACKER_ENABLED = os.getenv("KALMAN_TRACKER_ENABLED", "true").lower() == "true"
RETAIL_SENTIMENT_ENABLED = os.getenv("RETAIL_SENTIMENT_ENABLED", "true").lower() == "true"
PCR_SCRAPER_ENABLED = os.getenv("PCR_SCRAPER_ENABLED", "true").lower() == "true"
BOND_SIGNAL_ENABLED = os.getenv("BOND_SIGNAL_ENABLED", "true").lower() == "true"
EQUITY_LEAD_ENABLED = os.getenv("EQUITY_LEAD_ENABLED", "true").lower() == "true"
SURPRISE_INDEX_ENABLED = os.getenv("SURPRISE_INDEX_ENABLED", "true").lower() == "true"
WAVELET_DECOMP_ENABLED = os.getenv("WAVELET_DECOMP_ENABLED", "true").lower() == "true"
VALUE_MIGRATION_ENABLED = os.getenv("VALUE_MIGRATION_ENABLED", "true").lower() == "true"
BAYESIAN_UPDATER_ENABLED = os.getenv("BAYESIAN_UPDATER_ENABLED", "true").lower() == "true"
ANCHORED_VWAP_ENABLED = os.getenv("ANCHORED_VWAP_ENABLED", "true").lower() == "true"
CONTRASTIVE_LEARNER_ENABLED = os.getenv("CONTRASTIVE_LEARNER_ENABLED", "true").lower() == "true"
GAMMA_SCRAPER_ENABLED = os.getenv("GAMMA_SCRAPER_ENABLED", "true").lower() == "true"
BARRIER_SCRAPER_ENABLED = os.getenv("BARRIER_SCRAPER_ENABLED", "true").lower() == "true"
DOT_PLOT_ENABLED = os.getenv("DOT_PLOT_ENABLED", "true").lower() == "true"
CB_DIVERGENCE_ENABLED = os.getenv("CB_DIVERGENCE_ENABLED", "true").lower() == "true"
CARRY_MONITOR_ENABLED = os.getenv("CARRY_MONITOR_ENABLED", "true").lower() == "true"
POLITICAL_RISK_ENABLED = os.getenv("POLITICAL_RISK_ENABLED", "true").lower() == "true"
CURRENCY_NETWORK_ENABLED = os.getenv("CURRENCY_NETWORK_ENABLED", "true").lower() == "true"
SPILLOVER_INDEX_ENABLED = os.getenv("SPILLOVER_INDEX_ENABLED", "true").lower() == "true"
TDA_PATTERNS_ENABLED = os.getenv("TDA_PATTERNS_ENABLED", "true").lower() == "true"
ONLINE_LEARNER_ENABLED = os.getenv("ONLINE_LEARNER_ENABLED", "true").lower() == "true"
BANDIT_PARAMS_ENABLED = os.getenv("BANDIT_PARAMS_ENABLED", "true").lower() == "true"
RL_EXIT_AGENT_ENABLED = os.getenv("RL_EXIT_AGENT_ENABLED", "true").lower() == "true"
MS_GARCH_ENABLED = os.getenv("MS_GARCH_ENABLED", "true").lower() == "true"
COUNTERFACTUAL_ENABLED = os.getenv("COUNTERFACTUAL_ENABLED", "true").lower() == "true"
CAUSAL_IMPORTANCE_ENABLED = os.getenv("CAUSAL_IMPORTANCE_ENABLED", "true").lower() == "true"
ES_RISK_ENABLED = os.getenv("ES_RISK_ENABLED", "true").lower() == "true"
RUIN_CALC_ENABLED = os.getenv("RUIN_CALC_ENABLED", "true").lower() == "true"
HAWKES_PROCESS_ENABLED = os.getenv("HAWKES_PROCESS_ENABLED", "true").lower() == "true"
DISPOSITION_EFFECT_ENABLED = os.getenv("DISPOSITION_EFFECT_ENABLED", "true").lower() == "true"
ANCHORING_EFFECT_ENABLED = os.getenv("ANCHORING_EFFECT_ENABLED", "true").lower() == "true"
MUTUAL_INFO_ENABLED = os.getenv("MUTUAL_INFO_ENABLED", "true").lower() == "true"
SIGNAL_ENTROPY_ENABLED = os.getenv("SIGNAL_ENTROPY_ENABLED", "true").lower() == "true"
YAHOO_NEWS_ENABLED = os.getenv("YAHOO_NEWS_ENABLED", "true").lower() == "true"
CBOE_VOL_ENABLED = os.getenv("CBOE_VOL_ENABLED", "true").lower() == "true"
COT_REPORTS_LIB_ENABLED = os.getenv("COT_REPORTS_LIB_ENABLED", "true").lower() == "true"
OANDA_FEED_ENABLED = os.getenv("OANDA_FEED_ENABLED", "true").lower() == "true"
FXSSI_WEB_ENABLED = os.getenv("FXSSI_WEB_ENABLED", "true").lower() == "true"
CQG_ENABLED = os.getenv("CQG_ENABLED", "false").lower() == "true"
OANDA_FEED_POLL_INTERVAL = float(os.getenv("OANDA_FEED_POLL_INTERVAL", "1.0"))
FOOTPRINT_PATTERNS_ENABLED = os.getenv("FOOTPRINT_PATTERNS_ENABLED", "true").lower() == "true"
NEWS_VELOCITY_ENABLED = os.getenv("NEWS_VELOCITY_ENABLED", "true").lower() == "true"
BROKER_SPREAD_COMPARISON_ENABLED = os.getenv("BROKER_SPREAD_COMPARISON_ENABLED", "true").lower() == "true"
POOR_HIGH_LOW_ENABLED = os.getenv("POOR_HIGH_LOW_ENABLED", "true").lower() == "true"
NETWORK_JITTER_MONITOR_ENABLED = os.getenv("NETWORK_JITTER_MONITOR_ENABLED", "true").lower() == "true"
SWAP_ANOMALY_ENABLED = os.getenv("SWAP_ANOMALY_ENABLED", "true").lower() == "true"


MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "3.0"))
MAX_WEEKLY_LOSS_PCT = float(os.getenv("MAX_WEEKLY_LOSS_PCT", "6.0"))
MAX_DAILY_TRADES = int(os.getenv("MAX_DAILY_TRADES", "3"))
CONSECUTIVE_LOSS_LIMIT = int(os.getenv("CONSECUTIVE_LOSS_LIMIT", "2"))


def _reconcile_positions(
    conn: sqlite3.Connection,
    exit_manager: DynamicExitManager | None,
    partial_closer: PartialCloseManager,
    trade_tracker: TradeTracker,
) -> tuple[set[str], dict[int, str]]:
    """Rebuild in-memory state from MT5 open positions after restart.

    Returns (open_symbols, ticket_to_symbol) for main loop use.
    """
    open_symbols: set[str] = set()
    ticket_to_symbol: dict[int, str] = {}

    if not MT5_ENABLED:
        _oanda_key = os.getenv("OANDA_API_KEY", "")
        _oanda_acct = os.getenv("OANDA_ACCOUNT_ID", "")
        if _oanda_key and _oanda_acct:
            if oanda_connect():
                LOGGER.info("OANDA connected — will execute via OANDA REST API")
                try:
                    oanda_positions = oanda_get_positions()
                    if oanda_positions is not None:
                        for pos in oanda_positions:
                            sym = pos.get("symbol", "")
                            ticket = pos.get("ticket", 0)
                            open_symbols.add(sym)
                            ticket_to_symbol[ticket] = sym
                        if open_symbols:
                            LOGGER.info("OANDA reconciliation: %d open positions", len(open_symbols))
                except Exception as exc:
                    LOGGER.warning("OANDA position reconciliation error: %s", exc)
            else:
                LOGGER.warning("OANDA connection failed — falling back to signal-only")
        else:
            LOGGER.info("MT5 position reconciliation skipped — signal-only mode")
        return open_symbols, ticket_to_symbol

    trade_tracker.sync_existing_positions(conn)

    from execution.mt5_executor import get_open_positions
    try:
        positions = get_open_positions()
    except RuntimeError as exc:
        LOGGER.warning("MT5 position reconciliation skipped — %s", exc)
        return open_symbols, ticket_to_symbol

    if positions is None:
        LOGGER.warning("MT5 position reconciliation skipped — positions_get() returned None")
        return open_symbols, ticket_to_symbol

    for pos in positions:
        ticket = int(pos.get("ticket", 0))
        symbol = str(pos.get("symbol", ""))
        direction = "BUY" if int(pos.get("type", 0)) == 0 else "SELL"
        entry_price = float(pos.get("price_open", 0))
        sl_price = float(pos.get("sl", 0))
        tp_price = float(pos.get("tp", 0))
        lot_size = float(pos.get("volume", 0))

        if not ticket or not symbol:
            continue

        open_symbols.add(symbol)
        ticket_to_symbol[ticket] = symbol

        try:
            trade_id_row = conn.execute(
                "SELECT trade_id FROM trade_executions WHERE symbol = ? AND exit_price IS NULL ORDER BY trade_id DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if trade_id_row:
                trade_tracker.register_trade(ticket, trade_id_row[0])
        except Exception as exc:
            LOGGER.warning("Reconcile trade_id lookup failed for %s: %s", symbol, exc)

        if exit_manager is not None:
            exit_manager.register_position(
                ticket=ticket,
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                sl_price=sl_price if sl_price > 0 else entry_price,
                tp_price=tp_price if tp_price > 0 else entry_price,
                lot_size=lot_size,
            )

        partial_closer.register_trade(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            sl_price=sl_price if sl_price > 0 else entry_price,
            lot_size=lot_size,
        )

        LOGGER.info(
            "Reconciled: ticket=%d symbol=%s direction=%s entry=%.5f lots=%.2f",
            ticket, symbol, direction, entry_price, lot_size,
        )

    if open_symbols:
        LOGGER.info("Position reconciliation complete: %d open position(s) restored", len(open_symbols))
    else:
        LOGGER.info("No open positions to reconcile")

    return open_symbols, ticket_to_symbol


def _check_risk_limits(conn: sqlite3.Connection, account_balance: float) -> tuple[bool, str]:
    daily_loss_limit = account_balance * (MAX_DAILY_LOSS_PCT / 100.0)
    weekly_loss_limit = account_balance * (MAX_WEEKLY_LOSS_PCT / 100.0)

    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN date(timestamp) = date('now') THEN pnl ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN timestamp >= datetime('now', '-7 days') THEN pnl ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN date(timestamp) = date('now') THEN 1 ELSE 0 END), 0)
        FROM trade_executions
        WHERE exit_price IS NOT NULL
        """
    ).fetchone()

    if row is None:
        return True, ""

    daily_pnl, weekly_pnl, daily_trades = row[0], row[1], row[2]

    if daily_pnl < -daily_loss_limit:
        return False, f"daily_loss_limit: pnl={daily_pnl:.2f} < -{daily_loss_limit:.2f}"

    if weekly_pnl < -weekly_loss_limit:
        return False, f"weekly_loss_limit: pnl={weekly_pnl:.2f} < -{weekly_loss_limit:.2f}"

    if daily_trades >= MAX_DAILY_TRADES:
        return False, f"max_daily_trades: {daily_trades} >= {MAX_DAILY_TRADES}"

    recent = conn.execute(
        """
        SELECT pnl FROM trade_executions
        WHERE exit_price IS NOT NULL
        ORDER BY timestamp DESC LIMIT ?
        """,
        (CONSECUTIVE_LOSS_LIMIT,),
    ).fetchall()

    if len(recent) >= CONSECUTIVE_LOSS_LIMIT and all(r[0] < 0 for r in recent):
        return False, f"consecutive_losses: {CONSECUTIVE_LOSS_LIMIT} in a row"

    return True, ""


def _get_account_balance() -> float:
    try:
        import MetaTrader5 as mt5
        info = mt5.account_info()
        if info is not None:
            return float(info.balance)
    except Exception:
        pass
    return float(os.getenv("ACCOUNT_BALANCE", "10000"))


def _compute_kelly_from_history(conn: sqlite3.Connection, account_balance: float) -> tuple[float, float, float, float]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
            COALESCE(AVG(CASE WHEN pnl > 0 THEN pnl END), 0) AS avg_win,
            COALESCE(AVG(CASE WHEN pnl < 0 THEN ABS(pnl) END), 1) AS avg_loss
        FROM trade_executions
        WHERE exit_price IS NOT NULL
        """
    ).fetchone()
    if row is None or row[0] < 10:
        return (
            float(os.getenv("KELLY_WIN_RATE", "0.55")),
            float(os.getenv("KELLY_AVG_WIN", "100")),
            float(os.getenv("KELLY_AVG_LOSS", "75")),
            account_balance,
        )
    total, wins, avg_win, avg_loss = row
    win_rate = wins / total if total > 0 else 0.55
    avg_win = max(avg_win, 1.0)
    avg_loss = max(avg_loss, 1.0)
    return win_rate, avg_win, avg_loss, account_balance


def _get_pnl_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_trades,
            COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
            COALESCE(SUM(pnl), 0) AS total_pnl,
            COALESCE(SUM(CASE WHEN date(timestamp) = date('now') THEN pnl ELSE 0 END), 0) AS daily_pnl,
            COALESCE(SUM(CASE WHEN date(timestamp) = date('now') THEN 1 ELSE 0 END), 0) AS daily_trades,
            COALESCE(AVG(pnl), 0) AS avg_pnl,
            COALESCE(MAX(pnl), 0) AS best_trade,
            COALESCE(MIN(pnl), 0) AS worst_trade
        FROM trade_executions
        WHERE exit_price IS NOT NULL
        """
    ).fetchone()

    if row is None or row[0] == 0:
        return {"total_trades": 0, "mt5_online": False}

    total, wins, total_pnl, daily_pnl, daily_trades, avg_pnl, best, worst = row
    win_rate = wins / total if total > 0 else 0.0

    return {
        "total_trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(win_rate, 4),
        "total_pnl": round(total_pnl, 2),
        "daily_pnl": round(daily_pnl, 2),
        "daily_trades": daily_trades,
        "avg_pnl": round(avg_pnl, 2),
        "best_trade": round(best, 2),
        "worst_trade": round(worst, 2),
        "mt5_online": os.getenv("MT5_ENABLED", "false").lower() == "true",
    }


def log_tick(conn: sqlite3.Connection, tick: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO tick_log (symbol, bid, ask, delta, dom_json, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            tick["symbol"],
            tick["bid"],
            tick["ask"],
            tick["delta"],
            tick.get("dom_json", json.dumps(tick.get("dom", {}))),
            tick["timestamp"],
        ),
    )


def log_trade(conn: sqlite3.Connection, tick: dict[str, Any], direction: str, gate_states: dict[str, bool], result: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO trade_executions
            (symbol, direction, entry_price, exit_price, pnl, gate_states_json, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            tick["symbol"],
            direction,
            float(result["price"]),
            None,
            0.0,
            json.dumps(gate_states, sort_keys=True),
        ),
    )
    return cursor.lastrowid


def enrich_tick(tick: dict[str, Any], previous_mid: float | None, latest_mids: dict[str, float]) -> dict[str, Any]:
    enriched = dict(tick)
    enriched["prev_mid"] = previous_mid
    symbol = enriched.get("symbol", "")
    
    from core.symbol_mapper import resolve_counterpart, resolve_futures_root, get_future_to_spot_and_reverse_map
    
    counterpart = resolve_counterpart(symbol)
    counterpart_mid = latest_mids.get(counterpart) if counterpart else None

    bid = tick.get("bid")
    ask = tick.get("ask")
    current_mid = 0.0
    if bid is not None and ask is not None:
        current_mid = (float(bid) + float(ask)) / 2.0
    else:
        current_mid = float(tick.get("price", previous_mid or 0.0))

    ask_size = float(tick.get("ask_size", 0))
    bid_size = float(tick.get("bid_size", 0))
    if ask_size > 0 or bid_size > 0:
        enriched.setdefault("direction", "BUY" if ask_size > bid_size else "SELL")
    else:
        prev_mid_val = previous_mid if previous_mid is not None else 0.0
        if current_mid > prev_mid_val and prev_mid_val > 0:
            enriched.setdefault("direction", "BUY")
        elif current_mid < prev_mid_val and prev_mid_val > 0:
            enriched.setdefault("direction", "SELL")
        else:
            enriched.setdefault("direction", tick.get("direction", "BUY"))
        
    f2s, s2f = get_future_to_spot_and_reverse_map()
    root = resolve_futures_root(symbol)
    
    if symbol in s2f:  # Spot Forex symbol
        # Spot is the deriv price, CME is the leading rithmic price
        enriched["deriv_price"] = current_mid
        enriched["rithmic_price"] = counterpart_mid if counterpart_mid is not None else current_mid
    elif root in f2s:  # CME Future symbol
        # CME is the leading rithmic price, Spot is the deriv price
        enriched["rithmic_price"] = current_mid
        enriched["deriv_price"] = counterpart_mid if counterpart_mid is not None else current_mid
    else:
        # Default fallback
        enriched["rithmic_price"] = current_mid
        enriched["deriv_price"] = current_mid

    enriched.setdefault("lag_threshold_pips", float(os.getenv("LAG_THRESHOLD_PIPS", "1.5")))
    return annotate_tick(enriched)


_prev_dom_levels: dict[str, dict[str, float]] = {}


def _infer_l2_actions(symbol: str, quote: dict, price_type: str, timestamp: int, l3_scorer: L3RealTimeScorer) -> None:
    """Convert Quantower L2 DOM quote changes into synthetic MBO events for l3_scorer.

    Quantower sends individual price-level updates (not true CME MBO).
    We track previous state per (symbol, price) to infer ADD/MODIFY/CANCEL actions:
    - New price level appearing → ADD
    - Size increasing at existing level → ADD (new orders joining)
    - Size decreasing at existing level → MODIFY
    - Size dropping to 0 or level vanishing → CANCEL
    This feeds InstitutionalFeatureEngine with enough signal for
    spoof detection (large ADD then CANCEL), queue exhaustion (attrition),
    iceberg (replenish after fill), adverse selection (short-lived CANCEL at BBO).
    """
    price = float(quote.get("Price", 0))
    new_size = float(quote.get("Size", 0))
    level_id = f"{symbol}:{price_type}:{price}"
    side = "Bid" if price_type == "Bid" else "Ask"
    prev_size = _prev_dom_levels.get(level_id, -1.0)

    if prev_size < 0:
        action = "ADD"
    elif new_size > prev_size:
        action = "ADD"
    elif new_size < prev_size and new_size > 0:
        action = "MODIFY"
    elif new_size == 0:
        action = "CANCEL"
    else:
        _prev_dom_levels[level_id] = new_size
        return

    _prev_dom_levels[level_id] = new_size

    mbo_event = {
        "action": action,
        "order_id": quote.get("Id", level_id),
        "price": price,
        "size": new_size if action != "CANCEL" else prev_size,
        "side": side,
        "number_orders": int(quote.get("NumberOrders", 0)),
        "implied_size": int(quote.get("ImpliedSize", 0)),
        "timestamp_ns": timestamp * 1_000_000 if timestamp < 1_000_000_000_000 else timestamp * 1_000,
        "source": "quantower_l2_inferred",
    }
    l3_scorer.process_mbo_event(symbol, mbo_event)

    if action == "ADD" and new_size > prev_size and prev_size >= 0:
        fill_event = {
            "action": "FILL",
            "order_id": quote.get("Id", level_id) + "_fill",
            "price": price,
            "size": prev_size,
            "side": side,
            "timestamp_ns": mbo_event["timestamp_ns"] - 1,
            "source": "quantower_l2_inferred",
        }
        l3_scorer.process_mbo_event(symbol, fill_event)


async def _drain_l3_queue(l3_queue: asyncio.Queue, l3_scorer: L3RealTimeScorer) -> None:
    while True:
        event = await l3_queue.get()
        try:
            source = event.get("source", "")
            msg_type = event.get("type", "")

            if source == "motivewave" and msg_type == "MBO_EVENT":
                _process_motivewave_mbo(event, l3_scorer)
                continue

            if source == "motivewave" and msg_type == "DOM_SNAPSHOT":
                _process_motivewave_dom(event, l3_scorer)
                continue

            if source == "motivewave" and msg_type == "TICK":
                _process_motivewave_tick_l3(event, l3_scorer)
                continue

            symbol = event.get("symbol", "?")
            quote = event.get("quote", {})
            price_type = event.get("quotePriceType", "")
            timestamp = event.get("timestamp", 0)
            if quote and price_type and timestamp:
                _infer_l2_actions(symbol, quote, price_type, timestamp, l3_scorer)
        except Exception as exc:
            LOGGER.debug("L3 queue drain error: %s", exc)


def _process_motivewave_mbo(event: dict, l3_scorer: L3RealTimeScorer) -> None:
    """Convert MotiveWave MBO_EVENT to l3_scorer format and feed directly."""
    symbol = event.get("symbol", "?")
    side = event.get("side", "")
    action = str(event.get("action", "")).upper()
    price = float(event.get("price", 0))
    size = float(event.get("size", 0))
    timestamp = int(event.get("timestamp", 0))

    mw_action_map = {"ADD": "ADD", "MODIFY": "MODIFY", "CANCEL": "CANCEL"}
    mapped_action = mw_action_map.get(action, "ADD")

    mbo_event = {
        "action": mapped_action,
        "order_id": f"mw:{side}:{price}",
        "price": price,
        "size": size,
        "side": side,
        "timestamp_ns": timestamp * 1_000_000 if timestamp < 1_000_000_000_000 else timestamp * 1_000,
        "source": "motivewave_mbo",
    }
    l3_scorer.process_mbo_event(symbol, mbo_event)

    try:
        from ml.order_book_engine import OrderBookEngine as _OBE
        if hasattr(_process_motivewave_mbo, "_obe"):
            _obe = _process_motivewave_mbo._obe
        else:
            _process_motivewave_mbo._obe = None
            _obe = None
        if _obe is not None:
            _obe.process_event(symbol, mbo_event)
    except Exception:
        pass

    if mapped_action == "ADD" and side in ("BID", "ASK"):
        prev_count = int(event.get("prev_order_count", 0))
        cur_count = int(event.get("cur_order_count", 0))
        if cur_count < prev_count:
            fill_event = {
                "action": "FILL",
                "order_id": f"mw:{side}:{price}:fill",
                "price": price,
                "size": size,
                "side": side,
                "timestamp_ns": mbo_event["timestamp_ns"] - 1,
                "source": "motivewave_mbo",
            }
            l3_scorer.process_mbo_event(symbol, fill_event)


def _process_motivewave_dom(event: dict, l3_scorer: L3RealTimeScorer) -> None:
    """Process MotiveWave DOM_SNAPSHOT — extract MBO orders per level."""
    symbol = event.get("symbol", "?")
    timestamp = int(event.get("timestamp", 0))
    ts_ns = timestamp * 1_000_000 if timestamp < 1_000_000_000_000 else timestamp * 1_000

    for bid in event.get("bids", []):
        price = float(bid.get("price", 0))
        size = float(bid.get("size", 0))
        order_count = int(bid.get("order_count", 0))
        for order in bid.get("orders", []):
            oid = str(order.get("order_id", ""))
            qty = float(order.get("quantity", 0))
            if qty > 0 and oid:
                mbo = {
                    "action": "ADD",
                    "order_id": f"mw:{oid}",
                    "price": price,
                    "size": qty,
                    "side": "BID",
                    "timestamp_ns": ts_ns,
                    "source": "motivewave_dom",
                }
                l3_scorer.process_mbo_event(symbol, mbo)

    for ask in event.get("asks", []):
        price = float(ask.get("price", 0))
        size = float(ask.get("size", 0))
        order_count = int(ask.get("order_count", 0))
        for order in ask.get("orders", []):
            oid = str(order.get("order_id", ""))
            qty = float(order.get("quantity", 0))
            if qty > 0 and oid:
                mbo = {
                    "action": "ADD",
                    "order_id": f"mw:{oid}",
                    "price": price,
                    "size": qty,
                    "side": "ASK",
                    "timestamp_ns": ts_ns,
                    "source": "motivewave_dom",
                }
                l3_scorer.process_mbo_event(symbol, mbo)


def _process_motivewave_tick_l3(event: dict, l3_scorer: L3RealTimeScorer) -> None:
    """Process MotiveWave TICK event for L3 scorer — update best bid/ask."""
    symbol = event.get("symbol", "?")
    bid = float(event.get("bid_price", 0))
    ask = float(event.get("ask_price", 0))
    if bid > 0 and ask > 0 and symbol in l3_scorer.inst_engines:
        l3_scorer.inst_engines[symbol].update_best(bid, ask)
    exch_id = event.get("exch_order_id", 0)
    if exch_id and event.get("is_ask_tick", False):
        fill_event = {
            "action": "FILL",
            "order_id": f"mw:fill:{exch_id}",
            "price": float(event.get("price", 0)),
            "size": float(event.get("volume", 0)),
            "side": "ASK",
            "timestamp_ns": int(event.get("timestamp", 0)) * 1_000_000,
            "source": "motivewave_tick",
        }
        l3_scorer.process_mbo_event(symbol, fill_event)
    elif exch_id and not event.get("is_ask_tick", False):
        fill_event = {
            "action": "FILL",
            "order_id": f"mw:fill:{exch_id}",
            "price": float(event.get("price", 0)),
            "size": float(event.get("volume", 0)),
            "side": "BID",
            "timestamp_ns": int(event.get("timestamp", 0)) * 1_000_000,
            "source": "motivewave_tick",
        }
        l3_scorer.process_mbo_event(symbol, fill_event)


def _compute_bonus_layers(
    tick: dict[str, Any],
    score: float,
    adjusted_score: float,
    gate_states: dict[str, bool],
    framework_scores: dict[str, float],
    l3_info: dict[str, Any],
    bias_breakdown: dict[str, float],
    tick_count: int,
) -> dict[str, Any]:
    result = {"total_bonus": 0.0, "total_multiplier": 1.0, "threshold_adj": 0.0, "layers": {}, "blocks": [], "size_multiplier": 1.0}
    symbol = tick.get("symbol", "")
    direction = tick.get("direction", "BUY")
    mid = (float(tick.get("bid", 0)) + float(tick.get("ask", 0))) / 2.0 if tick.get("bid") and tick.get("ask") else 0.0
    pip_size = float(tick.get("pip_size", 0.0001))
    spread_bps = float(tick.get("spread_bps", 0))
    bonus_total = 0.0
    mult_total = 1.0
    threshold_adj = 0.0
    size_mult = 1.0

    def _add(layer_name, bonus=0.0, multiplier=1.0, th_adj=0.0, sz_mult=1.0, block=None):
        nonlocal bonus_total, mult_total, threshold_adj, size_mult
        result["layers"][layer_name] = {"bonus": bonus, "multiplier": multiplier, "threshold_adj": th_adj}
        bonus_total += bonus
        mult_total *= multiplier
        threshold_adj += th_adj
        size_mult *= sz_mult
        if block:
            result["blocks"].append(block)

    if DEAD_ZONE_ENABLED:
        try:
            _dz, _dz_mult = is_dead_zone()
            _add("dead_zone", multiplier=_dz_mult, block="dead_zone" if _dz else None)
        except Exception:
            pass

    if DAILY_BIAS_ENABLED:
        try:
            _db_bonus = daily_bias.get_bonus(symbol, direction)
            _add("daily_bias", bonus=_db_bonus)
        except Exception:
            pass

    if SESSION_MULTIPLIER_ENABLED:
        try:
            _sm = get_session_multiplier(tick, killzone_quality=float(tick.get("_killzone_quality", 1.0)))
            _add("session_multiplier", multiplier=_sm)
        except Exception:
            pass

    if TIME_HEATMAP_ENABLED:
        try:
            _thm = time_heatmap.get_multiplier(symbol, direction)
            _add("time_heatmap", multiplier=_thm)
            if time_heatmap.should_block(symbol, direction):
                result["blocks"].append("time_heatmap_block")
        except Exception:
            pass

    if LIVE_EDGE_TRACKER_ENABLED:
        try:
            if live_edge_tracker.should_skip(symbol, direction):
                result["blocks"].append("live_edge_no_edge")
            _let = live_edge_tracker.get_size_multiplier(symbol, direction)
            _add("live_edge_tracker", sz_mult=_let)
        except Exception:
            pass

    if SYSTEM_HEALTH_FILTER_ENABLED:
        try:
            if should_skip_entry():
                result["blocks"].append("system_health_low")
        except Exception:
            pass

    if SCORE_CALIBRATION_ENABLED:
        try:
            _cal = score_calibrator.calibrate(score)
            result["layers"]["score_calibration"] = {"calibrated_score": _cal}
        except Exception:
            pass

    if LONDON_FIX_ENABLED:
        try:
            _lf = london_fix.get_bonus(symbol, direction)
            _add("london_fix", bonus=_lf)
        except Exception:
            pass

    if SPREAD_VELOCITY_ENABLED:
        try:
            _sv = spread_velocity.get_bonus(symbol)
            _add("spread_velocity", bonus=_sv)
        except Exception:
            pass

    if TAPE_ACCELERATION_ENABLED:
        try:
            _, _ta = tape_acceleration.get_acceleration(symbol, direction)
            _add("tape_acceleration", bonus=_ta)
        except Exception:
            pass

    if BID_ASK_FLIP_ENABLED:
        try:
            _, _bf = bid_ask_flip.detect_flip(symbol, direction)
            _add("bid_ask_flip", bonus=_bf)
        except Exception:
            pass

    if FLASH_CRASH_DETECTOR_ENABLED:
        try:
            _price_change = mid - float(tick.get("prev_mid", mid)) if tick.get("prev_mid") else 0.0
            _fc = flash_crash_detector.check_tick(symbol, _price_change, float(tick.get("cumulative_volume", 0)), spread_bps, tick_count)
            if _fc or flash_crash_detector.is_halted(symbol, tick_count):
                result["blocks"].append("flash_crash")
        except Exception:
            pass

    if SYSTEM_STATE_MACHINE_ENABLED:
        try:
            _drift_active = bias_breakdown.get("clamped_bias", 0) < -0.05
            _consec = 0
            _state, _conf = system_state_machine.evaluate(
                drift_active=_drift_active,
                spread_zscore=float(tick.get("_spread_zscore", 0)),
                consecutive_losses=_consec,
                kyle_lambda_ratio=1.0,
                system_health=get_system_health(),
                network_quality=1.0,
            )
            _ssm_mult = system_state_machine.get_size_multiplier()
            _add("system_state_machine", sz_mult=_ssm_mult)
            tick["_system_state"] = str(_state)
        except Exception:
            pass

    if ANTI_MARTINGALE_ENABLED:
        try:
            _am = anti_martingale.get_size_multiplier()
            _add("anti_martingale", sz_mult=_am)
        except Exception:
            pass

    if SIGNAL_FREQUENCY_ENABLED:
        try:
            _sf = signal_frequency.get_multiplier()
            _add("signal_frequency", multiplier=_sf)
        except Exception:
            pass

    if SEASONAL_PATTERNS_ENABLED:
        try:
            _sp = seasonal_patterns.get_hourly_multiplier(symbol, direction)
            _add("seasonal_patterns", multiplier=_sp)
        except Exception:
            pass

    if DOM_QUOTE_STUFFING_ENABLED:
        try:
            if quote_stuffing_detector.is_stuffing_active(symbol):
                result["blocks"].append("quote_stuffing")
        except Exception:
            pass

    if MICRO_REGIME_SHIFT_ENABLED:
        try:
            _shifted, _warnings = micro_regime_shift.check_shift(symbol)
            if _shifted and any("adverse" in str(w).lower() for w in _warnings):
                _add("micro_regime", bonus=-0.03)
        except Exception:
            pass

    if DRAWDOWN_VELOCITY_ENABLED:
        try:
            _dv = drawdown_velocity.get_threshold_adjustment()
            _add("drawdown_velocity", th_adj=_dv)
        except Exception:
            pass

    if GATE_COMBOS_ENABLED:
        try:
            _gc = gate_combo_memory.check_combo(gate_states, symbol, direction)
            _add("gate_combos", bonus=_gc)
        except Exception:
            pass

    if INITIAL_BALANCE_ENABLED:
        try:
            _ib = initial_balance.get_breakout_bonus(symbol, direction, mid)
            _add("initial_balance", bonus=_ib)
        except Exception:
            pass

    if MM_SPREAD_BEHAVIOR_ENABLED:
        try:
            if mm_spread_behavior.should_skip_trade(symbol):
                result["blocks"].append("mm_step_back")
            _dir, _mm = mm_spread_behavior.get_directional_lean(symbol)
            if _mm != 0:
                _add("mm_spread_behavior", bonus=_mm)
        except Exception:
            pass

    if KALMAN_TRACKER_ENABLED:
        try:
            if kalman_tracker.should_skip_signal(symbol):
                result["blocks"].append("kalman_high_uncertainty")
            _kv = kalman_tracker.update(symbol, mid)
            if _kv and kalman_tracker.velocity_confirms(symbol, direction):
                _add("kalman_tracker", bonus=0.02)
        except Exception:
            pass

    if BOND_SIGNAL_ENABLED:
        try:
            _bs = bond_signal.get_bond_bonus(symbol, direction)
            _add("bond_signal", bonus=_bs)
        except Exception:
            pass

    if EQUITY_LEAD_ENABLED:
        try:
            _el = equity_lead.get_fx_bonus(symbol, direction)
            _add("equity_lead", bonus=_el)
        except Exception:
            pass

    if NEWS_VELOCITY_ENABLED:
        try:
            _nv = news_velocity.get_bonus("forex", symbol, direction)
            _add("news_velocity", bonus=_nv)
        except Exception:
            pass

    if BROKER_SPREAD_COMPARISON_ENABLED:
        try:
            _warn, _prem, _blean = broker_spread_comparison.check_warning(symbol)
            if _warn:
                _add("broker_spread_comparison", bonus=-0.02)
        except Exception:
            pass

    if POOR_HIGH_LOW_ENABLED:
        try:
            _phl = poor_high_low.get_threshold_reduction(symbol, mid, pip_size)
            _add("poor_high_low", th_adj=_phl)
        except Exception:
            pass

    if NETWORK_JITTER_MONITOR_ENABLED:
        try:
            _jq = network_jitter_monitor.get_quality(symbol)
            if _jq == "DEGRADED":
                _add("network_jitter", bonus=-0.02)
        except Exception:
            pass

    if SWAP_ANOMALY_ENABLED:
        try:
            _sa = swap_anomaly.get_bonus(symbol, direction)
            _add("swap_anomaly", bonus=_sa)
        except Exception:
            pass

    try:
        _cc = get_crowding_bonus(symbol, direction)
        if _cc != 0:
            _add("cot_crowding", bonus=_cc)
    except Exception:
        pass

    if HURST_EXPONENT_ENABLED:
        try:
            _he = hurst_exponent.get_gating_bonus(symbol, direction)
            _add("hurst_exponent", bonus=_he)
        except Exception:
            pass

    if ANCHORED_VWAP_ENABLED:
        try:
            _aw = anchored_vwap.get_bonus(symbol, direction, mid)
            _add("anchored_vwap", bonus=_aw)
        except Exception:
            pass

    if RETAIL_SENTIMENT_ENABLED:
        try:
            _rs = retail_sentiment.get_fade_bonus(symbol, direction)
            _add("retail_sentiment", bonus=_rs)
        except Exception:
            pass

    if FXSSI_WEB_ENABLED:
        try:
            _fxssi = fxssi_fade_bonus(symbol, direction)
            _add("fxssi_sentiment", bonus=_fxssi)
        except Exception:
            pass

    if YAHOO_NEWS_ENABLED:
        try:
            _yn = yahoo_usd_sentiment() * 0.02
            _add("yahoo_news", bonus=_yn)
        except Exception:
            pass

    if CBOE_VOL_ENABLED:
        try:
            _cboe_iv = get_symbol_iv(symbol)
            _cboe_skew = get_symbol_skew(symbol)
            _add("cboe_vol", bonus=_cboe_skew * 0.5)
        except Exception:
            pass

    if COT_REPORTS_LIB_ENABLED:
        try:
            _cot_lib = cot_lib_crowding_bonus(symbol)
            _add("cot_reports_lib", bonus=_cot_lib)
        except Exception:
            pass

    if PCR_SCRAPER_ENABLED:
        try:
            _pcr = pcr_scraper.get_direction_bonus(symbol, direction)
            _add("pcr_scraper", bonus=_pcr)
        except Exception:
            pass

    if SURPRISE_INDEX_ENABLED:
        try:
            _si = surprise_index.get_bias(symbol)
            _add("surprise_index", bonus=_si * 0.04)
        except Exception:
            pass

    if WAVELET_DECOMP_ENABLED:
        try:
            _wd = wavelet_decomp.get_directional_bonus(symbol, direction)
            _add("wavelet_decomp", bonus=_wd)
        except Exception:
            pass

    if VALUE_MIGRATION_ENABLED:
        try:
            _vm = value_migration.get_bonus(symbol, direction)
            _add("value_migration", bonus=_vm)
        except Exception:
            pass

    if BAYESIAN_UPDATER_ENABLED:
        try:
            _posterior, _action = bayesian_updater.get_posterior(symbol)
            if _action == "abort":
                result["blocks"].append("bayesian_abort")
            elif _action == "skip":
                result["blocks"].append("bayesian_skip")
            elif _action == "reduce":
                size_mult *= 0.5
            elif _action == "enter_small":
                size_mult *= 0.5
        except Exception:
            pass

    if CONTRASTIVE_LEARNER_ENABLED:
        try:
            _cl = contrastive_learner.get_bonus(framework_scores)
            _add("contrastive_learner", bonus=_cl)
        except Exception:
            pass

    if GAMMA_SCRAPER_ENABLED:
        try:
            _gs = gamma_scraper.get_bonus(symbol, direction, mid)
            _add("gamma_scraper", bonus=_gs)
        except Exception:
            pass

    if BARRIER_SCRAPER_ENABLED:
        try:
            if barrier_scraper.should_avoid_breakout(symbol, mid):
                result["blocks"].append("barrier_avoid_breakout")
        except Exception:
            pass

    if DOT_PLOT_ENABLED:
        try:
            _dp = dot_plot_analyzer.get_bonus(symbol, direction)
            _add("dot_plot", bonus=_dp)
        except Exception:
            pass

    if CB_DIVERGENCE_ENABLED:
        try:
            _cbd = cb_divergence.get_bonus(symbol, direction)
            _add("cb_divergence", bonus=_cbd)
        except Exception:
            pass

    if CARRY_MONITOR_ENABLED:
        try:
            _cm = carry_monitor.get_bonus(symbol, direction)
            _add("carry_monitor", bonus=_cm)
        except Exception:
            pass

    if POLITICAL_RISK_ENABLED:
        try:
            _pr = political_risk.get_bias_modifier(symbol)
            _add("political_risk", bonus=_pr)
        except Exception:
            pass

    if CURRENCY_NETWORK_ENABLED:
        try:
            _cn = currency_network.get_centrality_bonus(symbol)
            _add("currency_network", bonus=_cn)
        except Exception:
            pass

    if SPILLOVER_INDEX_ENABLED:
        try:
            _spi = spillover_index.get_cross_pair_weight()
            _add("spillover", multiplier=_spi)
        except Exception:
            pass

    if TDA_PATTERNS_ENABLED:
        try:
            _td, _tc = tda_patterns.check_drift(symbol)
            if _td:
                _add("tda_patterns", bonus=_tc)
        except Exception:
            pass

    if ONLINE_LEARNER_ENABLED:
        try:
            _feat_list = list(framework_scores.values())[:19]
            _ol = online_learner.get_bonus(_feat_list)
            _add("online_learner", bonus=_ol)
        except Exception:
            pass

    if BANDIT_PARAMS_ENABLED:
        try:
            _bp = bandit_params.select_threshold(symbol)
            result["layers"]["bandit_threshold"] = {"threshold": _bp}
        except Exception:
            pass

    if MS_GARCH_ENABLED:
        try:
            _gv = ms_garch.forecast_vol(symbol)
            if _gv > 0:
                tick["_garch_vol"] = _gv
        except Exception:
            pass

    if COUNTERFACTUAL_ENABLED:
        try:
            _cf = counterfactual_analyzer.get_execution_alpha(symbol)
            if _cf < -0.5:
                _add("counterfactual", bonus=-0.03)
                if counterfactual_analyzer.is_execution_destroying_edge(symbol):
                    result["blocks"].append("counterfactual_edge_destroyed")
        except Exception:
            pass

    if CAUSAL_IMPORTANCE_ENABLED:
        try:
            for _fw_name in framework_scores:
                _ci_w = causal_importance.get_framework_weight(_fw_name)
                if _ci_w != 1.0 and _ci_w < 1.0:
                    framework_scores[_fw_name] = framework_scores.get(_fw_name, 0.0) * _ci_w
        except Exception:
            pass

    if ES_RISK_ENABLED:
        try:
            _es_max = es_risk.get_max_position_size(0.02)
            if _es_max < 0.01:
                result["blocks"].append("es_risk_exceeded")
        except Exception:
            pass

    if RUIN_CALC_ENABLED:
        try:
            _rc_ok, _rc_prob = ruin_calc.is_ruin_risk_acceptable(0.02)
            if not _rc_ok:
                size_mult *= 0.5
        except Exception:
            pass

    if HAWKES_PROCESS_ENABLED:
        try:
            _urg = hawkes_process.get_entry_urgency(symbol, time.time())
            if _urg == "WAIT":
                _add("hawkes_process", bonus=-0.03)
        except Exception:
            pass

    if DISPOSITION_EFFECT_ENABLED:
        try:
            _de = disposition_effect.get_penalty(symbol, direction, mid)
            _add("disposition_effect", bonus=_de)
        except Exception:
            pass

    if ANCHORING_EFFECT_ENABLED:
        try:
            _ae = anchoring_effect.get_bonus(symbol, direction, mid, pip_size)
            _add("anchoring_effect", bonus=_ae)
        except Exception:
            pass

    if SIGNAL_ENTROPY_ENABLED:
        try:
            _, _se_mult = signal_entropy.compute_entropy()
            _add("signal_entropy", multiplier=_se_mult)
        except Exception:
            pass

    if FOOTPRINT_PATTERNS_ENABLED:
        try:
            _fp = footprint_patterns.detect_patterns(symbol, direction)
            _add("footprint_patterns", bonus=_fp)
        except Exception:
            pass

    if LAYER_PERFORMANCE_ENABLED:
        try:
            for _ln in list(result["layers"].keys()):
                if not layer_performance_tracker.is_layer_enabled(_ln):
                    result["layers"].pop(_ln, None)
        except Exception:
            pass

    result["total_bonus"] = bonus_total
    result["total_multiplier"] = mult_total
    result["threshold_adj"] = threshold_adj
    result["size_multiplier"] = size_mult
    return result


async def _process_queue(
    queue: asyncio.Queue, conn: sqlite3.Connection, registry: GateRegistry,
    l3_scorer: L3RealTimeScorer, exit_manager: DynamicExitManager | None,
    candle_aggregator: CandleAggregator, dxy_calc: DXYCalculator,
    risk_regime: RiskRegimeClassifier, telegram: TelegramAlerter,
    post_news_filter: PostReleaseContinuationFilter, partial_closer: PartialCloseManager,
    trade_tracker: TradeTracker, instrument_config: InstrumentConfig,
    dom_checker: DOMQualityChecker, currency_tracker: CurrencyExposureTracker,
    risk_engine: RiskEngine, latency_tracker: LatencyTracker,
    drift_monitor: DriftMonitor, order_book_engine: OrderBookEngine,
    per_symbol_model: PerSymbolModelManager, exec_quality_logger: ExecutionQualityLogger,
    trade_replay: TradeReplay, paper_trading: PaperTradingEngine,
    dynamic_selector: DynamicPairSelector,
    toxicity_engine: ToxicityEngine | None = None,
    ofi_manager: OFIManager | None = None,
    regime_intel: RegimeIntelEngine | None = None,
    cross_asset: CrossAssetEngine | None = None,
    cb_nlp: CentralBankNLP | None = None,
    vol_surface_mgr: VolSurfaceManager | None = None,
    pairs_engine: PairsEngine | None = None,
    network_engine: NetworkEngine | None = None,
    self_supervised: SelfSupervisedEngine | None = None,
    sequence_core: SequenceCore | None = None,
    xai_explainer: XAIExplainer | None = None,
    vector_memory: VectorMemory | None = None,
    rl_brain: TabularRLBrain | None = None,
    causal_engine: CausalEngine | None = None,
    attention_gate: AttentionGateWeighting | None = None,
    exec_algo_engine: ExecutionAlgoEngine | None = None,
    portfolio_risk: PortfolioRiskEngine | None = None,
    _open_symbols: set[str] | None = None,
    _ticket_to_symbol: dict[int, str] | None = None,
    l3_queue: asyncio.Queue | None = None,
) -> None:
    latest_mids: dict[str, float] = {}
    tick_count = 0
    _commit_interval = int(os.getenv("COMMIT_INTERVAL_TICKS", "50"))
    _halt_cache_ttl = float(os.getenv("HALT_CACHE_TTL_SECONDS", "5.0"))
    _last_halt_check: float = 0.0
    _cached_halt: bool = False
    _cached_dxy_trend: str = "neutral"
    _cached_risk_regime: str = "neutral"
    _tick_buffer: list[tuple] = []
    _tick_buffer_max = int(os.getenv("TICK_BUFFER_MAX", "100"))

    _last_retrain_count: int = 0
    _last_prune_time: float = 0.0
    _load_shed_mode: bool = False
    _retrain_pending: bool = False
    if _open_symbols is None:
        _open_symbols = set()
    if _ticket_to_symbol is None:
        _ticket_to_symbol = {}
    _last_signal_tick: dict[str, int] = {}
    _cumulative_delta: dict[str, float] = {}
    _cumulative_volume: dict[str, float] = {}
    _volume_profile: dict[str, dict[float, float]] = {}
    _open_interest: dict[str, float] = {}
    _ORDERFLOW_STATE: dict[str, dict[str, Any]] = {}
    _use_oanda = bool(os.getenv("OANDA_API_KEY", "")) and bool(os.getenv("OANDA_ACCOUNT_ID", "")) and not MT5_ENABLED
    _SIGNAL_COOLDOWN_TICKS = int(os.getenv("SIGNAL_COOLDOWN_TICKS", "500"))

    def _save_orderflow_dashboard():
        try:
            with open(_log_dir / "orderflow_dashboard.json", "w") as f:
                json.dump(_ORDERFLOW_STATE, f)
        except Exception:
            pass

    _last_udp_tick = time.monotonic()
    while True:
        try:
            tick = await asyncio.wait_for(queue.get(), timeout=2.0)
            if tick.get("source") not in ("oanda_rest",):
                _last_udp_tick = time.monotonic()
        except asyncio.TimeoutError:
            if OANDA_FEED_ENABLED and _use_oanda:
                time_since_udp = time.monotonic() - _last_udp_tick
                if time_since_udp > 5.0:
                    oanda_ticks = await asyncio.to_thread(poll_oanda_prices)
                    for ot in oanda_ticks:
                        await queue.put(ot)
            continue
        if tick.get("source") == "zmq_mbo":
            symbol = tick.get("symbol", "?")
            l3_scorer.process_mbo_event(symbol, tick)
            continue

        tick_count += 1
        symbol = tick.get("symbol", "?")
        if not tick.get("bid") and not tick.get("ask"):
            continue

        if tick_count % 50 == 0:
            _src = tick.get("source", "udp")
            LOGGER.info("[TICK_FEED] #%d %s src=%s bid=%.5f ask=%.5f", tick_count, symbol, _src, float(tick.get("bid", 0)), float(tick.get("ask", 0)))
            
        tick_delta = float(tick.get("delta", 0.0))
        if symbol not in _cumulative_delta:
            _cumulative_delta[symbol] = 0.0
        _cumulative_delta[symbol] += tick_delta
        tick["cumulative_delta"] = _cumulative_delta[symbol]
        
        latency_tracker.start_tick()
        if dom_checker.check_tick(tick):
            _dom_trading_ok, _dom_reason = dom_checker.is_trading_allowed()
            if not _dom_trading_ok:
                if tick_count % 500 == 0:
                    LOGGER.warning("DOM quality block: %s", _dom_reason)
        prev_mid = latest_mids.get(symbol)
        tick = enrich_tick(tick, prev_mid, latest_mids)
        latency_tracker.mark_enriched()
        bid_val = float(tick.get("bid", 0))
        ask_val = float(tick.get("ask", 0))
        if bid_val <= 0 or ask_val <= 0:
            continue
        current_mid = (bid_val + ask_val) / 2.0
        latest_mids[symbol] = current_mid
        instrument_config.update_rolling(symbol, bid_val, ask_val)
        tick = instrument_config.enrich_tick(tick)
        if tick.get("dom") and isinstance(tick.get("dom"), dict):
            book = order_book_engine.get_book(symbol)
            book.reconcile_with_snapshot(tick["dom"])

        spread_val = ask_val - bid_val
        risk_regime.update_spread(symbol, spread_val)

        # --- Tier-1 Institutional Modules (every tick) ---
        tick_side = tick.get("direction", "BUY")
        tick_size_inst = float(tick.get("tick_size", 0.0001))
        _mw_vol = float(tick.get("mw_tick_volume", 0))
        _trade_volume = _mw_vol if _mw_vol > 0 else abs(tick_delta)

        if VPIN_ENABLED and toxicity_engine is not None:
            toxicity_engine.on_trade(symbol, tick_side, _trade_volume, time.monotonic())
            toxicity_engine.on_order_event(symbol, "TRADE", _trade_volume, time.monotonic())

        # --- Accumulate traded volume per symbol for VPIN volume buckets ---
        if symbol not in _cumulative_volume:
            _cumulative_volume[symbol] = 0.0
        _cumulative_volume[symbol] += _trade_volume
        tick["cumulative_volume"] = _cumulative_volume[symbol]

        # --- Accumulate traded volume per price level for Volume Profile ---
        if _trade_volume > 0 and current_mid > 0:
            _vp_key = round(current_mid / tick_size_inst) * tick_size_inst if tick_size_inst > 0 else round(current_mid, 5)
            if symbol not in _volume_profile:
                _volume_profile[symbol] = {}
            _volume_profile[symbol][_vp_key] = _volume_profile[symbol].get(_vp_key, 0.0) + _trade_volume

        # --- Cross-asset: feed commodity prices from GC/CL ticks ---
        if CROSS_ASSET_ENABLED and cross_asset is not None:
            _sym_root = symbol[:2] if len(symbol) >= 2 else symbol
            if _sym_root == "GC":
                cross_asset.update_commodity("gold", current_mid)
                tick["_commodity"] = "gold"
            elif _sym_root == "CL":
                cross_asset.update_commodity("oil", current_mid)
                tick["_commodity"] = "oil"

        # --- Open Interest from tick (if bridge sends it) ---
        _oi = tick.get("open_interest")
        if _oi is not None:
            if symbol not in _open_interest:
                _open_interest[symbol] = 0
            _open_interest[symbol] = float(_oi)
            tick["current_oi"] = float(_oi)
            tick["oi_change"] = float(_oi) - _open_interest.get(symbol, float(_oi))

        if OFI_ENABLED and ofi_manager is not None:
            dom_data = tick.get("dom", {})
            if dom_data and isinstance(dom_data, dict):
                try:
                    _dom_bids = dom_data.get("bids", [])
                    _dom_asks = dom_data.get("asks", [])
                    if isinstance(_dom_bids, list):
                        _ofi_bids = [(float(b.get("price", 0)), float(b.get("size", 0))) for b in _dom_bids if b.get("price") and b.get("size")]
                    elif isinstance(_dom_bids, dict):
                        _ofi_bids = [(float(p), float(s)) for p, s in _dom_bids.items()]
                    else:
                        _ofi_bids = []
                    if isinstance(_dom_asks, list):
                        _ofi_asks = [(float(a.get("price", 0)), float(a.get("size", 0))) for a in _dom_asks if a.get("price") and a.get("size")]
                    elif isinstance(_dom_asks, dict):
                        _ofi_asks = [(float(p), float(s)) for p, s in _dom_asks.items()]
                    else:
                        _ofi_asks = []
                    if _ofi_bids or _ofi_asks:
                        ofi_manager.update_book(symbol, _ofi_bids, _ofi_asks, tick_size=tick_size_inst)
                except Exception:
                    pass
            ofi_manager.on_trade(symbol, tick_side, current_mid, _trade_volume, tick_size=tick_size_inst)

        if REGIME_INTEL_ENABLED and regime_intel is not None:
            _ofi_metrics = ofi_manager.get_all_metrics().get(symbol, {}) if ofi_manager is not None else {}
            regime_intel.on_tick(
                symbol, current_mid,
                spread_bps=float(tick.get("spread_bps", spread_val / current_mid * 10000 if current_mid > 0 else 0)),
                depth=float(tick.get("depth", 0)),
                ofi=_ofi_metrics.get("ofi", 0.0),
            )

        # --- Phase A-D Bonus Module on_tick feeds (every tick) ---
        if SPREAD_VELOCITY_ENABLED:
            try:
                spread_velocity.on_tick(symbol, spread_val / current_mid * 10000 if current_mid > 0 else 0)
            except Exception:
                pass
        if TAPE_ACCELERATION_ENABLED:
            try:
                tape_acceleration.on_tick(symbol, current_mid, _trade_volume, tick_side, tick_count)
            except Exception:
                pass
        if BID_ASK_FLIP_ENABLED:
            try:
                bid_ask_flip.on_tick(symbol, float(tick.get("bid_size", 0)), float(tick.get("ask_size", 0)))
            except Exception:
                pass
        if MICRO_REGIME_SHIFT_ENABLED:
            try:
                micro_regime_shift.on_tick(
                    symbol, spread_val / current_mid * 10000 if current_mid > 0 else 0,
                    tick_delta, _trade_volume, abs(current_mid - (tick.get("prev_mid") or current_mid)),
                    int(tick.get("dom_update_count", 0)),
                )
            except Exception:
                pass
        if MM_SPREAD_BEHAVIOR_ENABLED:
            try:
                mm_spread_behavior.on_tick(symbol, bid_val, ask_val, float(tick.get("bid_size", 0)), float(tick.get("ask_size", 0)))
            except Exception:
                pass
        if ANCHORED_VWAP_ENABLED:
            try:
                anchored_vwap.on_tick(symbol, current_mid, _trade_volume)
            except Exception:
                pass
        if HURST_EXPONENT_ENABLED:
            try:
                hurst_exponent.on_tick(symbol, current_mid)
            except Exception:
                pass
        if POOR_HIGH_LOW_ENABLED:
            try:
                poor_high_low.on_tick(symbol, current_mid, tick_count, tick_size_inst, tick_count)
            except Exception:
                pass
        if NETWORK_JITTER_MONITOR_ENABLED:
            try:
                _ts_ns = int(tick.get("timestamp", time.monotonic() * 1e9))
                network_jitter_monitor.on_tick(symbol, _ts_ns)
            except Exception:
                pass
        if HAWKES_PROCESS_ENABLED:
            try:
                hawkes_process.on_tick(symbol, time.time())
            except Exception:
                pass
        if WAVELET_DECOMP_ENABLED:
            try:
                wavelet_decomp.update_single(symbol, current_mid)
            except Exception:
                pass
        if KALMAN_TRACKER_ENABLED:
            try:
                kalman_tracker.update(symbol, current_mid)
            except Exception:
                pass
        if INITIAL_BALANCE_ENABLED:
            try:
                initial_balance.on_tick(symbol, current_mid, int(time.time()))
            except Exception:
                pass
        if DOM_QUOTE_STUFFING_ENABLED:
            try:
                if tick.get("dom"):
                    quote_stuffing_detector.on_dom_update(symbol, tick_count)
            except Exception:
                pass
        if BAYESIAN_UPDATER_ENABLED:
            try:
                bayesian_updater.observe_tick(symbol, tick_side, _trade_volume)
            except Exception:
                pass
        if DISPOSITION_EFFECT_ENABLED:
            try:
                disposition_effect.set_session_open(symbol, current_mid)
                _atr_inst = float(tick.get("atr", 0))
                if _atr_inst > 0:
                    disposition_effect.set_atr(symbol, _atr_inst)
            except Exception:
                pass
        if ANCHORING_EFFECT_ENABLED:
            try:
                if tick_count % 500 == 1:
                    anchoring_effect.set_anchors(
                        symbol,
                        yearly_open=0.0, monthly_open=0.0, weekly_open=0.0,
                        prior_close=float(tick.get("prev_mid", current_mid)),
                        round_figures=[],
                    )
            except Exception:
                pass
        if FOOTPRINT_PATTERNS_ENABLED:
            try:
                _c15 = tick.get("_candles_15m", [])
                if _c15 and len(_c15) > 0:
                    _lc = _c15[-1]
                    footprint_patterns.on_candle(
                        symbol, _lc.get("open", 0), _lc.get("high", 0), _lc.get("low", 0),
                        _lc.get("close", 0), _lc.get("volume", 0), tick_delta,
                    )
            except Exception:
                pass
        if SIGNAL_ENTROPY_ENABLED:
            try:
                signal_entropy.on_signal(gate_states if 'gate_states' in locals() else {})
            except Exception:
                pass

        # Feed new components
        dxy_calc.update(symbol, current_mid)
        risk_engine.update_yen_baseline(symbol, current_mid)
        if tick_count % 10 == 0:
            _cached_dxy_trend = dxy_calc.get_dxy_trend()
            _cached_risk_regime = risk_regime.classify()
            tick["dxy_trend"] = _cached_dxy_trend
            tick["risk_regime"] = _cached_risk_regime
            candle_aggregator.process_tick(tick)

        # --- Inject candle data onto tick dict for gate access ---
        if LEGENDARY_MODE_ENABLED or tick_count % 10 == 0:
            try:
                _candle_snap = candle_aggregator.snapshot(symbol)
                tick["_candles_15m"] = [
                    {"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                    for c in _candle_snap.get("15m", [])[-50:]
                ]
                tick["_candles_1h"] = [
                    {"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                    for c in _candle_snap.get("1H", [])[-50:]
                ]
                tick["_candles_daily"] = [
                    {"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                    for c in _candle_snap.get("Daily", [])[-50:]
                ]
            except Exception:
                tick["_candles_15m"] = []
                tick["_candles_1h"] = []
                tick["_candles_daily"] = []

        # --- Kill zone quality + psychological levels + session levels ---
        if LEGENDARY_MODE_ENABLED:
            try:
                _kz = get_killzone_quality()
                tick["_killzone_quality"] = _kz["quality"]
                tick["_in_peak_killzone"] = _kz.get("is_peak_window", False)
                tick["_killzone_zone"] = _kz.get("zone", None)
                tick["_session_name"] = get_session_name()
            except Exception:
                tick["_killzone_quality"] = 0.0
                tick["_in_peak_killzone"] = False

            try:
                _roll = get_roll_status(symbol)
                tick["_roll_status"] = _roll["status"]
                tick["_roll_quality_mult"] = _roll["signal_quality_multiplier"]
            except Exception:
                tick["_roll_status"] = "ACTIVE"
                tick["_roll_quality_mult"] = 1.0

            try:
                _spread_z = get_spread_zscore(symbol, float(tick.get("spread_bps", 0)))
                tick["_spread_zscore"] = _spread_z["zscore"]
                tick["_spread_anomalous"] = _spread_z.get("anomalous", False)
            except Exception:
                tick["_spread_zscore"] = 0.0
                tick["_spread_anomalous"] = False

            try:
                _pip = float(tick.get("pip_size", 0.0001))
                _psych = classify_level(current_mid, _pip)
                tick["_psych_level"] = _psych
                _hunt = get_stop_hunt_probability(current_mid, tick.get("direction", "BUY"), _pip)
                tick["_stop_hunt_prob"] = _hunt
            except Exception:
                tick["_psych_level"] = {"type": "NONE", "significance": 0.0, "at_level": False}
                tick["_stop_hunt_prob"] = {"hunt_likely": False}

            try:
                _sess_signal = session_levels.get_proximity_signal(
                    symbol, current_mid, tick.get("direction", "BUY"), float(tick.get("pip_size", 0.0001))
                )
                tick["_session_level_proximity"] = _sess_signal
            except Exception:
                tick["_session_level_proximity"] = {"proximity": "NONE"}

            # --- Tier-2: Cross-asset + portfolio risk (every 10 ticks) ---
            if CROSS_ASSET_ENABLED and cross_asset is not None:
                cross_asset.update_fx(symbol, current_mid)
            if PORTFOLIO_RISK_ENABLED and portfolio_risk is not None:
                _prev_mid_for_ret = latest_mids.get(symbol, current_mid)
                if _prev_mid_for_ret > 0:
                    portfolio_risk.update_symbol_return(symbol, (current_mid - _prev_mid_for_ret) / _prev_mid_for_ret)
            if VOL_SURFACE_ENABLED and vol_surface_mgr is not None:
                _vol_engine = vol_surface_mgr.get_engine(symbol)
                _vol_engine.update_realized_vol(current_mid)
                _iv_data = {}
                try:
                    _iv_data = scrape_options_iv.__wrapped__ if hasattr(scrape_options_iv, '__wrapped__') else {}
                except Exception:
                    pass
                if isinstance(_iv_data, dict) and _iv_data:
                    _atm = _iv_data.get("atm_iv", 0)
                    if _atm > 0:
                        _vol_engine.update_atm_iv("1M", _atm)
                    _rr25 = _iv_data.get("rr_25d", 0)
                    if _rr25 != 0:
                        _vol_engine.update_skew(rr_25d=_rr25)

        closed = []
        if MT5_ENABLED and tick_count % 50 == 0:
            closed = trade_tracker.check_closed_positions(conn)
            for ct in closed:
                sym = _ticket_to_symbol.pop(ct.get("ticket", 0), "")
                _open_symbols.discard(sym)
                try:
                    _ct_pnl = float(ct.get("pnl", 0))
                    if ANTI_MARTINGALE_ENABLED:
                        anti_martingale.record_outcome(_ct_pnl)
                    if DRAWDOWN_VELOCITY_ENABLED:
                        drawdown_velocity.record_pnl(_ct_pnl)
                    if ES_RISK_ENABLED:
                        es_risk.update_pnl(_ct_pnl)
                    if RUIN_CALC_ENABLED:
                        ruin_calc.update_from_trade(_ct_pnl)
                except Exception:
                    pass
        if closed and AUTORETRAIN_TRADES > 0:
            stats = _get_pnl_stats(conn)
            new_closed = stats.get("total_trades", 0) - _last_retrain_count
            if new_closed >= AUTORETRAIN_TRADES:
                _last_retrain_count = stats["total_trades"]
                _retrain_pending = True

        # --- OANDA position monitoring: detect closed positions ---
        if _use_oanda and tick_count % 50 == 0:
            try:
                _oanda_pos = oanda_get_positions()
                if _oanda_pos is not None:
                    _oanda_open_syms = set()
                    for _op in _oanda_pos:
                        _oanda_open_syms.add(_op.get("symbol", ""))
                    for _closed_sym in list(_open_symbols):
                        if _closed_sym not in _oanda_open_syms:
                            _open_symbols.discard(_closed_sym)
                            LOGGER.info("[OANDA_MONITOR] Position closed: %s", _closed_sym)
            except Exception:
                pass

        if _retrain_pending:
            _retrain_pending = False
            try:
                from ml.train_model import train

                def _do_retrain():
                    train()
                    reload_model()

                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, _do_retrain)
                LOGGER.info("Auto-retrain dispatched to background thread after %d new closed trades", new_closed)
                asyncio.create_task(telegram.send_system_alert(
                    f"Model retraining started: {new_closed} new trades processed."
                ))
            except Exception as e:
                LOGGER.error("Auto-retrain dispatch failed: %s", e)
        _tick_buffer.append((
            tick["symbol"], tick["bid"], tick["ask"], tick["delta"],
            json.dumps(tick.get("dom", {})), tick["timestamp"],
        ))

        if current_mid > 0:
            update_mid_price(tick["symbol"], current_mid, tick_count)

        from ml.signal_logger import _pending_outcomes as _po
        if tick_count % 10 == 0 or (_po and tick_count % 5 == 0):
            check_outcomes(conn, tick_count)

        if len(_tick_buffer) >= _tick_buffer_max or tick_count % _commit_interval == 0:
            if _tick_buffer:
                conn.executemany(
                    """
                    INSERT INTO tick_log (symbol, bid, ask, delta, dom_json, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    _tick_buffer,
                )
                _tick_buffer.clear()
            conn.commit()

        if tick_count % 1000 == 0:
            # --- Bottom-Up Learning: Mistake Audit ---
            try:
                from ml.mistake_analyzer import run_analysis
                _mistake_report = run_analysis()
                LOGGER.info("Learning from Mistakes:\n%s", _mistake_report)
            except Exception as e:
                LOGGER.error("Mistake Audit failed: %s", e)

        if tick_count % 500 == 0:
            # --- Database Pruning (Daily Auto-Clear) ---
            _now_time = time.time()
            if _now_time - _last_prune_time > 21600: # Every 6 hours
                _prune_database(conn)
                _last_prune_time = _now_time

            from ml.autonomous_optimizer import run_autonomous_optimization
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, run_autonomous_optimization)

            # --- System Health: Load Shedder ---
            _health = get_system_health()
            if _health < 0.80 and not _load_shed_mode:
                LOGGER.warning("System: CRITICAL CPU LOAD detected. Activating Emergency Load Shedder...")
                _load_shed_mode = True
            elif _health > 0.95 and _load_shed_mode:
                LOGGER.info("System: CPU Load stabilized. Deactivating Load Shedder.")
                _load_shed_mode = False

            if TIME_HEATMAP_ENABLED:
                try:
                    time_heatmap.refresh(DB_PATH)
                except Exception:
                    pass
            if SEASONAL_PATTERNS_ENABLED:
                try:
                    seasonal_patterns.load_from_db(DB_PATH)
                except Exception:
                    pass
            if GATE_COMBOS_ENABLED:
                try:
                    gate_combo_memory.refresh_from_db(DB_PATH)
                except Exception:
                    pass
            if SCORE_CALIBRATION_ENABLED:
                try:
                    score_calibrator.fit_from_db(DB_PATH)
                except Exception:
                    pass
            if CONTRASTIVE_LEARNER_ENABLED:
                try:
                    contrastive_learner.maybe_refresh(DB_PATH)
                except Exception:
                    pass
            if CURRENCY_NETWORK_ENABLED:
                try:
                    currency_network.maybe_refresh()
                except Exception:
                    pass
            if CAUSAL_IMPORTANCE_ENABLED:
                try:
                    causal_importance.fit_from_db(DB_PATH)
                except Exception:
                    pass
            if MUTUAL_INFO_ENABLED:
                try:
                    mutual_info_audit.audit_from_db(DB_PATH)
                except Exception:
                    pass
            if SURPRISE_INDEX_ENABLED:
                try:
                    surprise_index.load_from_calendar_scraper()
                except Exception:
                    pass
            if RETAIL_SENTIMENT_ENABLED:
                try:
                    retail_sentiment.refresh(symbol)
                except Exception:
                    pass
            if PCR_SCRAPER_ENABLED:
                try:
                    pcr_scraper.refresh(symbol)
                except Exception:
                    pass
            if GAMMA_SCRAPER_ENABLED:
                try:
                    gamma_scraper.refresh(symbol)
                except Exception:
                    pass
            if FXSSI_WEB_ENABLED:
                try:
                    scrape_fxssi_sentiment()
                except Exception:
                    pass
            if DOT_PLOT_ENABLED:
                try:
                    dot_plot_analyzer.refresh()
                except Exception:
                    pass
            if POLITICAL_RISK_ENABLED:
                try:
                    political_risk.refresh()
                except Exception:
                    pass
            if BARRIER_SCRAPER_ENABLED:
                try:
                    barrier_scraper.refresh(symbol)
                except Exception:
                    pass
            if BOND_SIGNAL_ENABLED:
                try:
                    bond_signal.refresh()
                except Exception:
                    pass
            if EQUITY_LEAD_ENABLED:
                try:
                    equity_lead.refresh()
                except Exception:
                    pass
            if SPILLOVER_INDEX_ENABLED:
                try:
                    spillover_index.compute_index()
                except Exception:
                    pass
            if CARRY_MONITOR_ENABLED:
                try:
                    carry_monitor.update_rates({})
                except Exception:
                    pass
            if CB_DIVERGENCE_ENABLED:
                try:
                    cb_divergence.refresh()
                except Exception:
                    pass
            if BROKER_SPREAD_COMPARISON_ENABLED:
                try:
                    broker_spread_comparison.update_market_spread(symbol, float(tick.get("spread_bps", 0)))
                except Exception:
                    pass
            if SWAP_ANOMALY_ENABLED:
                try:
                    swap_anomaly.refresh()
                except Exception:
                    pass
            if TDA_PATTERNS_ENABLED:
                try:
                    tda_patterns.compute_topology(symbol)
                except Exception:
                    pass
            if MS_GARCH_ENABLED:
                try:
                    ms_garch.update_returns(symbol, 0.0)
                except Exception:
                    pass
            if HAWKES_PROCESS_ENABLED:
                try:
                    hawkes_process.decay_all()
                except Exception:
                    pass

            candle_aggregator.flush_to_db(conn)
            if exit_manager is not None:
                for sym in exit_manager.open_positions.values():
                    s = sym.get("symbol", "")
                    if s:
                        hvn = candle_aggregator.get_hvn_levels(s)
                        if hvn:
                            exit_manager.load_hvn_levels({s: hvn})
            loop.run_in_executor(None, scrape_options_iv, candle_aggregator)
            loop.run_in_executor(None, scrape_fred)
            loop.run_in_executor(None, scrape_ecb)
            loop.run_in_executor(None, scrape_finnhub)
            if YAHOO_NEWS_ENABLED:
                loop.run_in_executor(None, scrape_yahoo_news)
            if CBOE_VOL_ENABLED:
                loop.run_in_executor(None, scrape_cboe_vol)
            if COT_REPORTS_LIB_ENABLED:
                loop.run_in_executor(None, scrape_cot_reports)
            if FXSSI_WEB_ENABLED:
                loop.run_in_executor(None, scrape_fxssi_sentiment)
            
            stats = _get_pnl_stats(conn)
            if stats.get("total_trades", 0) > 0:
                asyncio.create_task(telegram.send_alert(
                    f"<b>P&L Report</b>\n\n"
                    f"Trades: {stats['total_trades']} W/L: {stats['wins']}/{stats['losses']}\n"
                    f"Win Rate: {stats['win_rate']:.1%}\n"
                    f"Total P&L: ${stats['total_pnl']:.2f}\n"
                    f"Today: ${stats['daily_pnl']:.2f} ({stats['daily_trades']} trades)\n"
                    f"Avg: ${stats['avg_pnl']:.2f} Best: ${stats['best_trade']:.2f} Worst: ${stats['worst_trade']:.2f}"
                ))

            # --- Tier-2/3/4: Slow periodic institutional modules ---
            if NETWORK_ENABLED and network_engine is not None:
                for _ns, _nm in latest_mids.items():
                    network_engine.update_price(_ns, _nm)
            if PAIRS_STAT_ENABLED and pairs_engine is not None:
                for _ns, _nm in latest_mids.items():
                    pairs_engine.update_price(_ns, _nm)
                try:
                    _active_pairs = pairs_engine.scan_all_pairs()
                    if _active_pairs:
                        tick["_pairs_signals"] = _active_pairs
                except Exception:
                    pass
            if CB_NLP_ENABLED and cb_nlp is not None:
                try:
                    _cb_surprise = cb_nlp.get_surprise_signal()
                    if _cb_surprise.get("is_surprise", False):
                        LOGGER.info("[CB_NLP] Policy surprise detected: %s", _cb_surprise)
                except Exception:
                    pass
            if SELF_SUPERVISED_ENABLED and self_supervised is not None and tick_count % SELF_SUPERVISED_INTERVAL == 0:
                try:
                    _all_mids_list = list(latest_mids.values())[:20]
                    if len(_all_mids_list) >= 5:
                        import numpy as _np
                        _ss_features = _np.array(_all_mids_list).reshape(1, -1)
                        _ss_result = self_supervised.process_features(_ss_features)
                        if _ss_result.get("is_anomaly") or _ss_result.get("is_outlier"):
                            LOGGER.warning("[SELF_SUPERVISED] Anomaly detected: zscore=%.2f iso_score=%.2f",
                                           _ss_result.get("anomaly_zscore", 0), _ss_result.get("isolation_score", 0))
                except Exception:
                    pass
            if CAUSAL_ENGINE_ENABLED and causal_engine is not None and tick_count % CAUSAL_ENGINE_INTERVAL == 0:
                try:
                    loop.run_in_executor(None, causal_engine.run_from_db)
                except Exception:
                    pass
            if VPIN_ENABLED and toxicity_engine is not None:
                _all_tox = toxicity_engine.get_all_metrics()
                for _tox_sym, _tox_m in _all_tox.items():
                    if _tox_m.get("is_toxic"):
                        LOGGER.warning("[VPIN] Toxic flow: %s composite=%.3f vpin=%.3f",
                                       _tox_sym, _tox_m.get("toxicity_composite", 0), _tox_m.get("vpin", 0))

        # --- Gate Throttling Logic ---
        _effective_eval_interval = 10 if _load_shed_mode else GATE_EVAL_INTERVAL
        _skip = (tick_count % _effective_eval_interval != 0)
        l3_status = f" L3={'warm' if l3_scorer.warm else 'cold'}" if tick_count >= 1 else ""
        LOGGER.info("Ticks: %s symbol=%s gates=%s%s", tick_count, tick["symbol"], "skip" if _skip else "eval", l3_status)
        _now = time.monotonic()
        if _now - _last_halt_check > _halt_cache_ttl:
            _cached_halt = check_halt_status(DB_PATH)
            _last_halt_check = _now
        if _cached_halt:
            LOGGER.warning("System halted. Skipping trade attempt.")
            if tick_count % _commit_interval == 0:
                if _tick_buffer:
                    conn.executemany(
                        """
                        INSERT INTO tick_log (symbol, bid, ask, delta, dom_json, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        _tick_buffer,
                    )
                    _tick_buffer.clear()
                conn.commit()
            continue

        has_open = bool(exit_manager and exit_manager.open_positions) if exit_manager else False
        skip_gates = (not has_open) and (tick_count % GATE_EVAL_INTERVAL != 0)
        if skip_gates:
            if tick_count % _commit_interval == 0:
                if _tick_buffer:
                    conn.executemany(
                        """
                        INSERT INTO tick_log (symbol, bid, ask, delta, dom_json, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        _tick_buffer,
                    )
                    _tick_buffer.clear()
                conn.commit()
            continue

        l3_info = l3_scorer.score(tick)
        for _l3_key, _l3_val in l3_info.items():
            if _l3_key not in ("l3_prediction", "l3_confidence", "l3_ready"):
                tick[_l3_key] = _l3_val
        tick["_l3_features"] = l3_info

        gate_states = registry.evaluate(tick)
        tick["_gate_states_cache"] = gate_states
        latency_tracker.mark_gates_done()
        framework_scores = aggregate_framework_scores(gate_states, direction=tick.get("direction", "BUY"))

        # --- Attention Gate Weighting: dynamically reweight frameworks per context ---
        if ATTENTION_GATE_ENABLED and attention_gate is not None:
            try:
                _attn_context = {
                    "session": tick.get("session", ""),
                    "risk_regime": tick.get("risk_regime", "neutral"),
                    "dxy_trend": tick.get("dxy_trend", "neutral"),
                    "symbol": symbol,
                }
                framework_scores = attention_gate.adjust_framework_scores(
                    framework_scores, direction=tick.get("direction", "BUY"), context=_attn_context
                )
            except Exception:
                pass

        # --- Sequence Core (every Nth tick when XGB > threshold) ---
        _sequence_result = {}
        if SEQUENCE_CORE_ENABLED and sequence_core is not None and tick_count % SEQUENCE_INFERENCE_INTERVAL == 0:
            try:
                import numpy as _np
                _seq_features = sequence_core.build_features(tick, framework_scores)
                sequence_core.push_features(symbol, _seq_features)
                _sequence_result = sequence_core.predict(symbol, xgb_score=0.0)
            except Exception:
                pass

        if drift_monitor.should_check(tick_count):
            try:
                drift_monitor.check(conn, tick_count)
            except Exception as exc:
                LOGGER.debug("Drift monitor check error: %s", exc)

        gate_d = gate_states.get("gate_D", False)
        gate_z7 = gate_states.get("gate_Z7", False)
        _GATE_QUICK_REJECT = os.getenv("GATE_QUICK_REJECT", "true").lower() == "true"
        if _GATE_QUICK_REJECT and (not gate_d or not gate_z7):
            if tick_count % _commit_interval == 0:
                if _tick_buffer:
                    conn.executemany(
                        """
                        INSERT INTO tick_log (symbol, bid, ask, delta, dom_json, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        _tick_buffer,
                    )
                _tick_buffer.clear()
                conn.commit()
            continue

        l3_bias = l3_info["l3_prediction"] * l3_info["l3_confidence"] if l3_info["l3_ready"] else 0.0
        spoof_bias = l3_info.get("spoof_reversal_signal", 0.0) * float(os.getenv("BIAS_SPOOF", "0.15"))
        queue_bias = l3_info.get("queue_exhaustion_signal", 0.0) * float(os.getenv("BIAS_QUEUE", "0.10"))
        iceberg_bias = l3_info.get("iceberg_detected", 0.0) * float(os.getenv("BIAS_ICEBERG", "0.05"))
        adverse_bias = -l3_info.get("adverse_selection_risk", 0.0) * float(os.getenv("BIAS_ADVERSE", "0.20"))
        hft_bias = l3_info.get("hft_cluster_detected", 0.0) * float(os.getenv("BIAS_HFT", "0.08"))
        vacuum_bias = -l3_info.get("liquidity_vacuum_signal", 0.0) * float(os.getenv("BIAS_VACUUM", "0.12"))
        total_l3_bias = l3_bias + spoof_bias + queue_bias + iceberg_bias + adverse_bias + hft_bias + vacuum_bias

        iv_skew = get_skew_score(tick.get("symbol", ""))
        iv_bias = iv_skew * float(os.getenv("BIAS_IV_SKEW", "0.10"))

        bias_breakdown = {
            "l3_bias": l3_bias,
            "spoof_bias": spoof_bias,
            "queue_bias": queue_bias,
            "iceberg_bias": iceberg_bias,
            "adverse_bias": adverse_bias,
            "hft_bias": hft_bias,
            "vacuum_bias": vacuum_bias,
            "iv_bias": iv_bias,
            "raw_bias": total_l3_bias + iv_bias,
            "clamped_bias": max(-float(os.getenv("BIAS_MAX_SHIFT", "0.15")), min(float(os.getenv("BIAS_MAX_SHIFT", "0.15")), total_l3_bias + iv_bias)),
        }
        tick["_bias_breakdown"] = bias_breakdown

        try:
            score = predict_trade_quality(gate_states, tick)
        except Exception:
            score = 0.0
        if per_symbol_model.has_model(symbol):
            try:
                score = per_symbol_model.predict(symbol, gate_states, tick)
            except Exception:
                pass
        latency_tracker.mark_scored()
        tick["_raw_model_score"] = score

        if tick_count % 100 == 0:
            passing = sum(1 for v in gate_states.values() if v)
            LOGGER.info("[SCORE_DEBUG] #%d %s score=%.4f gates_pass=%d/%d", tick_count, symbol, score, passing, len(gate_states))

        _BIAS_MAX_SHIFT = float(os.getenv("BIAS_MAX_SHIFT", "0.15"))
        raw_bias = total_l3_bias + iv_bias
        clamped_bias = max(-_BIAS_MAX_SHIFT, min(_BIAS_MAX_SHIFT, raw_bias))

        direction = tick.get("direction", "BUY")
        try:
            fund_bias = get_fundamental_bias_adjustment(symbol, direction)
        except Exception:
            fund_bias = 0.0
        tick["_fundamental_bias"] = fund_bias
        bias_breakdown["fundamental_bias"] = fund_bias

        adjusted_score = max(0.0, min(1.0, score + clamped_bias + fund_bias))

        # --- VPIN Toxicity Pre-Filter: block trades on toxic flow ---
        if VPIN_ENABLED and toxicity_engine is not None:
            _tox = toxicity_engine.get_toxicity_for_symbol(symbol)
            tick["_vpin_metrics"] = _tox
            if _tox.get("is_extreme_toxic"):
                LOGGER.warning("[VPIN] EXTREME toxic flow %s — blocking trade (composite=%.3f)", symbol, _tox.get("toxicity_composite", 0))
                continue
            if _tox.get("is_toxic"):
                adjusted_score = max(0.0, adjusted_score - 0.05)
                bias_breakdown["vpin_penalty"] = -0.05

        # --- Sequence Core: combine LSTM with XGB ---
        if SEQUENCE_CORE_ENABLED and sequence_core is not None and _sequence_result:
            try:
                _seq_combined = sequence_core.combined_score(symbol, score)
                if _seq_combined.get("sequence_confidence", 0) > 0.3:
                    score = _seq_combined["final_score"]
                    adjusted_score = max(0.0, min(1.0, adjusted_score * 0.7 + _seq_combined["final_score"] * 0.3))
                    bias_breakdown["sequence_boost"] = _seq_combined.get("sequence_boost", 0.0)
            except Exception:
                pass

        # --- Vector Memory: check similar past states ---
        if VECTOR_MEMORY_ENABLED and vector_memory is not None:
            try:
                _vm_result = vector_memory.check_experience(symbol, framework_scores, l3_info, tick, score)
                if _vm_result.get("score_adjustment", 0) != 0:
                    adjusted_score = max(0.0, min(1.0, adjusted_score + _vm_result["score_adjustment"]))
                    bias_breakdown["vector_memory_adj"] = _vm_result["score_adjustment"]
                    if _vm_result.get("similar_losses", 0) > _vm_result.get("similar_wins", 0) * 2:
                        LOGGER.info("[VECTOR_MEM] %s: %d similar losses vs %d wins — penalty %.3f",
                                    symbol, _vm_result["similar_losses"], _vm_result["similar_wins"],
                                    _vm_result["score_adjustment"])
            except Exception:
                pass

        # --- Regime Intelligence: inject regime info (model decides, no hard block) ---
        if REGIME_INTEL_ENABLED and regime_intel is not None:
            try:
                _ri_regime = regime_intel.get_regime(symbol)
                tick["_regime_intel"] = _ri_regime
                if not _ri_regime.get("trade_allowed", True):
                    if tick_count % 200 == 0:
                        LOGGER.info("[REGIME_INTEL] %s: unfavorable — composite=%s vol=%s (model decides)",
                            symbol, _ri_regime.get("composite_regime", "?"), _ri_regime.get("vol_regime", "?"))
            except Exception:
                pass

        # --- Cross-Asset Signal: inject into tick for downstream ---
        if CROSS_ASSET_ENABLED and cross_asset is not None:
            try:
                _rate_diff = float(tick.get("_fundamental_bias", 0))
                _ca_signal = cross_asset.get_composite_signal(symbol, rate_diff=_rate_diff)
                tick["_cross_asset_signal"] = _ca_signal
                if _ca_signal.get("composite_cross_asset_score", 0) < -0.5:
                    adjusted_score = max(0.0, adjusted_score - 0.03)
                    bias_breakdown["cross_asset_penalty"] = -0.03
            except Exception:
                pass

        # --- Phase A-D Bonus Layer Computation ---
        _bonus_result = _compute_bonus_layers(
            tick=tick, score=score, adjusted_score=adjusted_score,
            gate_states=gate_states, framework_scores=framework_scores,
            l3_info=l3_info, bias_breakdown=bias_breakdown, tick_count=tick_count,
        )
        _bonus_total = _bonus_result["total_bonus"]
        _bonus_mult = _bonus_result["total_multiplier"]
        _bonus_threshold_adj = _bonus_result["threshold_adj"]
        _bonus_size_mult = _bonus_result["size_multiplier"]
        _bonus_blocks = _bonus_result["blocks"]

        adjusted_score = max(0.0, min(1.0, (adjusted_score + _bonus_total) * _bonus_mult))
        bias_breakdown["bonus_total"] = _bonus_total
        bias_breakdown["bonus_multiplier"] = _bonus_mult
        bias_breakdown["bonus_size_mult"] = _bonus_size_mult
        bias_breakdown["bonus_threshold_adj"] = _bonus_threshold_adj
        try:
            _cc_layer = _bonus_result.get("layers", {}).get("cot_crowding", {})
            bias_breakdown["bias_crowding"] = _cc_layer.get("bonus", 0.0)
        except Exception:
            bias_breakdown["bias_crowding"] = 0.0
        tick["_bonus_layers"] = _bonus_result

        # --- Block trades on bonus layer filter signals ---
        if _bonus_blocks:
            if tick_count % 100 == 0:
                LOGGER.info("[BONUS_BLOCK] %s %s | Blocks: %s", symbol, direction, ", ".join(_bonus_blocks))
            continue

        # Calculate Order Flow Sentiment for Dashboard
        def get_sent(val, thresh=0.05):
            if val > thresh * 2: return "STRONG BUY"
            if val > thresh: return "BUY"
            if val < -thresh * 2: return "STRONG SELL"
            if val < -thresh: return "SELL"
            return "NEUTRAL"

        cvd_val = _cumulative_delta.get(symbol, 0.0)
        _ORDERFLOW_STATE[symbol] = {
            "symbol": symbol,
            "combined": get_sent(total_l3_bias, 0.1),
            "cvd": "BUY" if cvd_val > 0 else "SELL" if cvd_val < 0 else "NEUTRAL",
            "spoof": get_sent(spoof_bias, 0.03),
            "vacuum": get_sent(vacuum_bias, 0.03),
            "iceberg": get_sent(iceberg_bias, 0.03),
            "absorption": get_sent(queue_bias, 0.03),
            "hft": get_sent(hft_bias, 0.03),
            "adverse": "RISK" if adverse_bias < -0.05 else "SAFE",
            "divergence": "PASS" if gate_states.get("gate_DD", True) else "DIVERGENCE",
            "last_update": time.time()
        }
        if OFI_ENABLED and ofi_manager is not None:
            try:
                _ofi_m = ofi_manager.get_all_metrics().get(symbol, {})
                if _ofi_m:
                    _ORDERFLOW_STATE[symbol]["ofi"] = _ofi_m.get("ofi", 0)
                    _ORDERFLOW_STATE[symbol]["ofi_direction"] = _ofi_m.get("ofi_imbalance_direction", "neutral")
                    _ORDERFLOW_STATE[symbol]["micro_price_dev"] = _ofi_m.get("micro_price_deviation_pips", 0)
                    _ORDERFLOW_STATE[symbol]["informed_flow"] = _ofi_m.get("informed_flow_detected", False)
            except Exception:
                pass
        if VPIN_ENABLED and toxicity_engine is not None:
            try:
                _tox_m = toxicity_engine.get_toxicity_for_symbol(symbol)
                if _tox_m:
                    _ORDERFLOW_STATE[symbol]["vpin"] = _tox_m.get("vpin", 0)
                    _ORDERFLOW_STATE[symbol]["toxicity"] = _tox_m.get("toxicity_composite", 0)
                    _ORDERFLOW_STATE[symbol]["is_toxic"] = _tox_m.get("is_toxic", False)
            except Exception:
                pass
        if tick_count % 10 == 0:
            _save_orderflow_dashboard()

        vol_prof, cot, candle, imbal = 0.0, 0.0, 0.0, 0.0
        cum_delta = _cumulative_delta.get(symbol, 0.0)
        dd_gate = False
        
        if adjusted_score > 0.20:
            vol_prof = framework_scores.get("FW17_volume_profile", 0.0)
            cot = framework_scores.get("FW09_cot_positioning", 0.0)
            candle = framework_scores.get("FW02_price_action", 0.0)
            imbal = framework_scores.get("FW03_volume", 0.0)
            dd_gate = gate_states.get("gate_DD", False)

        LOGGER.info(
            "[SIGNAL_STRENGTH] %s %s | Raw: %.1f%% Adj: %.1f%% | L3/Orderflow: %s%.2f | Spoof: %s%.2f | Vac: %s%.2f | Ice: %s%.2f | VolProf: %.2f | COT: %.2f | Candle: %.2f | Imbal: %.2f | CumDelta: %+.1f | Div: %s | Bonus: %+.3f x%.2f",
            symbol, direction, score * 100, adjusted_score * 100,
            "+" if l3_bias >= 0 else "", l3_bias,
            "+" if spoof_bias >= 0 else "", spoof_bias,
            "+" if vacuum_bias >= 0 else "", vacuum_bias,
            "+" if iceberg_bias >= 0 else "", iceberg_bias,
            vol_prof, cot, candle, imbal, cum_delta, "PASS" if dd_gate else "FAIL",
            _bonus_total, _bonus_mult
            )

        # --- 10. Dynamic Threshold Engine ---
        from ml.dynamic_threshold import get_threshold_for
        dyn_thresh, dyn_tradable = get_threshold_for(symbol, direction)
        _base_threshold = float(os.getenv("QUALITY_SCORE_MIN", "0.60"))

        regime = tick.get("risk_regime", "neutral")
        tick_spread_bps = float(tick.get("spread_bps", 0))

        # FORCE 0.60 for High Movement Session
        effective_threshold = _base_threshold

        if tick_spread_bps >= 4.0:
            effective_threshold = 0.99
        
        effective_threshold = max(_base_threshold, effective_threshold + _bonus_threshold_adj)

        if BANDIT_PARAMS_ENABLED:
            try:
                _bt = bandit_params.select_threshold(symbol)
                effective_threshold = max(effective_threshold, _bt)
            except Exception:
                pass

        # --- 11. High Quality Filter: only trade with real CME DOM data ---
        _tick_source = tick.get("source", "udp")
        _has_dom = bool(tick.get("dom") or tick.get("dom_json", "[]") != "[]")
        _is_hq = _tick_source != "oanda_rest" and _has_dom

        if score <= effective_threshold:
            rejection_reason = "score_below_threshold"
            if gate_states.get("gate_D") is False: rejection_reason = "momentum_fail"
            if gate_states.get("gate_Z7") is False: rejection_reason = "lag_excessive"
            if clamped_bias < -0.05: rejection_reason = "adverse_l3_flow"
            if not _is_hq: rejection_reason = "no_dom_oanda_only"

            if tick_count % 100 == 0:
                LOGGER.info("[REJECTION] %s %s | Score: %.4f | Thresh: %.4f | %s | src=%s dom=%s",
                    symbol, direction, score, effective_threshold, rejection_reason, _tick_source, _has_dom)

            trade_replay.log_trade_decision(symbol, direction, score, score, adjusted_score,
                gate_states=gate_states, l3_features=l3_info, bias_breakdown=bias_breakdown,
                dom_health=dom_checker.get_status().get("status", "unknown"),
                rejection_reason=rejection_reason)
            continue

        # --- BLOCK: No DOM = No trade. Only execute on real CME order flow ---
        if not _is_hq and AUTO_EXECUTE:
            if tick_count % 50 == 0:
                LOGGER.info("[HQ_FILTER] %s %s | Score: %.4f | BLOCKED: no DOM (src=%s) signal-only",
                    symbol, direction, score, _tick_source)
            log_signal(conn, tick, direction, score, adjusted_score, gate_states, l3_info, bias_breakdown, executed=False, tick_count=tick_count)
            continue

        if score > effective_threshold:
            LOGGER.info("[ABOVE_THRESHOLD] %s %s | Score: %.4f > Threshold: %.4f", symbol, direction, score, effective_threshold)

            # --- Signal frequency tracking ---
            if SIGNAL_FREQUENCY_ENABLED:
                try:
                    signal_frequency.record_signal()
                except Exception:
                    pass

                # --- Entry sniper: register signal for pullback watching ---
                if ENTRY_SNIPER_ENABLED:
                    try:
                        entry_sniper.register_signal(symbol, direction, current_mid, float(tick.get("pip_size", 0.0001)), tick_count)
                    except Exception:
                        pass

                # --- Bayesian updater: start observation window ---
                if BAYESIAN_UPDATER_ENABLED:
                    try:
                        bayesian_updater.start_observation(symbol, score, direction)
                    except Exception:
                        pass

            # --- XAI Explainer: decompose signal (every Nth signal) ---
            if XAI_ENABLED and xai_explainer is not None:
                try:
                    _xai_result = xai_explainer.explain_signal(framework_scores, tick, score, gate_states)
                    tick["_xai_explanation"] = _xai_result
                    if tick_count % XAI_COMPUTE_INTERVAL == 0 or score > 0.90:
                        LOGGER.info("[XAI] %s %s score=%.3f | Top+: %s | Top-: %s | %s",
                                    symbol, direction, score,
                                    _xai_result.get("top_positive", []),
                                    _xai_result.get("top_negative", []),
                                    _xai_result.get("explanation", "")[:120])
                except Exception:
                    pass
            try:
                selector_decision = dynamic_selector.decide(
                symbol=symbol,
                direction=direction,
                tick=tick,
                score=score,
                adjusted_score=adjusted_score,
                framework_scores=framework_scores,
                l3_features=l3_info,
                bias_breakdown=bias_breakdown,
            )
            except Exception as selector_exc:
                LOGGER.error("Dynamic selector exception: %s %s - %s", symbol, direction, selector_exc)
                from ml.dynamic_pair_selector import SelectorDecision as _SD
                selector_decision = _SD(
                    status=STATUS_WATCHLIST, symbol=symbol, direction=direction,
                    rule_match=False, reason=f"selector_error: {selector_exc}")

            selector_risk_result = {
                "allowed": False,
                "reason": selector_decision.reason,
                "dynamic_selector_status": selector_decision.status,
                "dynamic_selector_rule_match": selector_decision.rule_match,
            }
            LOGGER.info("[SELECTOR_DECISION] %s %s status=%s rule_match=%s reason=%s", symbol, direction, selector_decision.status, selector_decision.rule_match, selector_decision.reason[:80])

            if selector_decision.is_block:
                last_t = _last_signal_tick.get(symbol, 0)
                if tick_count - last_t < _SIGNAL_COOLDOWN_TICKS:
                    continue
                _last_signal_tick[symbol] = tick_count
                if tick_count % 100 == 0:
                    LOGGER.info("Dynamic selector BLOCKED: %s %s (score=%.4f) - %s", direction, symbol, score, selector_decision.reason)
                log_signal(conn, tick, direction, score, adjusted_score,
                    gate_states, l3_info, bias_breakdown, executed=False, tick_count=tick_count)
                conn.commit()
                continue
            if selector_decision.status == STATUS_WATCHLIST:
                last_t = _last_signal_tick.get(symbol, 0)
                if tick_count - last_t < _SIGNAL_COOLDOWN_TICKS:
                    continue
                _last_signal_tick[symbol] = tick_count
                LOGGER.info(
                    "Dynamic selector WATCHLIST signal-only: %s %s score=%.4f adj=%.4f reason=%s",
                    direction, symbol, score, adjusted_score, selector_decision.reason,
                )
                log_signal(conn, tick, direction, score, adjusted_score,
                    gate_states, l3_info, bias_breakdown, executed=False, tick_count=tick_count)
                conn.commit()
                trade_replay.log_trade_decision(symbol, direction, score, score, adjusted_score,
                    gate_states=gate_states, l3_features=l3_info, bias_breakdown=bias_breakdown,
                    dom_health=dom_checker.get_status().get("status", "unknown"),
                    risk_checks=selector_risk_result, rejection_reason="dynamic_selector_watchlist")
                continue
            if selector_decision.status == STATUS_TRADE_CANDIDATE_SIGNAL_ONLY:
                last_t = _last_signal_tick.get(symbol, 0)
                if tick_count - last_t < _SIGNAL_COOLDOWN_TICKS:
                    continue
                _last_signal_tick[symbol] = tick_count
                LOGGER.info(
                    "Dynamic selector %s signal-only: %s %s score=%.4f adj=%.4f reason=%s",
                    selector_decision.status, direction, symbol, score, adjusted_score, selector_decision.reason,
                )
                log_signal(conn, tick, direction, score, adjusted_score,
                    gate_states, l3_info, bias_breakdown, executed=False, tick_count=tick_count)
                conn.commit()
                trade_replay.log_trade_decision(symbol, direction, score, score, adjusted_score,
                    gate_states=gate_states, l3_features=l3_info, bias_breakdown=bias_breakdown,
                    dom_health=dom_checker.get_status().get("status", "unknown"),
                    risk_checks=selector_risk_result, rejection_reason="dynamic_selector_signal_only")
                continue

            if selector_decision.status != STATUS_TRADE_CANDIDATE:
                if tick_count % 100 == 0:
                    LOGGER.info(
                        "Dynamic selector BLOCK: %s %s score=%.4f adj=%.4f reason=%s",
                        direction, symbol, score, adjusted_score, selector_decision.reason,
                    )
                trade_replay.log_trade_decision(symbol, direction, score, score, adjusted_score,
                    gate_states=gate_states, l3_features=l3_info, bias_breakdown=bias_breakdown,
                    dom_health=dom_checker.get_status().get("status", "unknown"),
                    risk_checks=selector_risk_result, rejection_reason=selector_decision.reason)
                continue

            account_balance = _get_account_balance()
            risk_sl_pips = float(tick.get("sl_pips", os.getenv("SL_PIPS", "5")))
            risk_spread_bps = float(tick.get("spread_bps", 0))
            risk_allowed, risk_reason_text = risk_engine.check_all(
                conn=conn, symbol=symbol, direction=direction,
                account_balance=account_balance,
                lot_size=float(os.getenv("PAPER_LOT_SIZE", "0.01")),
                sl_pips=risk_sl_pips,
                spread_bps=risk_spread_bps,
            )
            risk_result = {
                "allowed": risk_allowed,
                "reason": risk_reason_text,
                "sl_pips": risk_sl_pips,
                "spread_bps": risk_spread_bps,
            }
            risk_ok = risk_result.get("allowed", True)
            risk_reason = risk_result.get("reason", "")
            drift_ok, drift_reason = drift_monitor.is_trading_allowed()
            if not drift_ok:
                risk_ok = False
                risk_reason = f"drift: {drift_reason}"
            dom_ok, dom_reason = dom_checker.is_trading_allowed()
            if not dom_ok:
                risk_ok = False
                risk_reason = f"dom: {dom_reason}"
            latency_tracker.mark_decision()
            _mt5_enabled = MT5_ENABLED
            _auto_exec = AUTO_EXECUTE
            _oanda_enabled = bool(os.getenv("OANDA_API_KEY", "")) and bool(os.getenv("OANDA_ACCOUNT_ID", ""))
            _use_oanda = _oanda_enabled and not _mt5_enabled

            if not risk_ok:
                LOGGER.warning("Trade blocked by risk limit: %s", risk_reason)
                _last_signal_tick[symbol] = tick_count
                log_signal(conn, tick, direction, score, adjusted_score,
                    gate_states, l3_info, bias_breakdown, executed=False, tick_count=tick_count)
                conn.commit()
                exec_quality_logger.log_rejection(symbol, direction, 0.01, risk_reason,
                    spread_at_entry=float(tick.get("spread_bps", 0)), score=score, raw_score=score)
                trade_replay.log_trade_decision(symbol, direction, score, score, adjusted_score,
                    gate_states=gate_states, l3_features=l3_info, bias_breakdown=bias_breakdown,
                    dom_health=dom_checker.get_status().get("status", "unknown"),
                    risk_checks=risk_result, rejection_reason=risk_reason)
                continue
        if symbol in _open_symbols:
            LOGGER.warning("Trade blocked: already have open position on %s", symbol)
            continue

        # --- LEGENDARY MODE: Druckenmiller approach ---
        _is_legendary_trade = False
        _legendary_conviction = 0
        if LEGENDARY_MODE_ENABLED:
            is_leg, conviction, leg_reason = legendary_mode.is_legendary(
                gate_states, score, symbol, tick
            )
            if is_leg:
                from datetime import datetime as _dt, timezone as _tz
                _current_date = _dt.now(_tz.utc).strftime("%Y-%m-%d")
                if not legendary_mode.can_fire_today(symbol, _current_date):
                    LOGGER.info("[LEGENDARY] %s %s already fired today — standing down", direction, symbol)
                    continue
                _is_legendary_trade = True
                _legendary_conviction = conviction
                legendary_mode.mark_fired(symbol, direction, _current_date)
                LOGGER.info(
                    "[LEGENDARY] %s %s score=%.4f conviction=%d/100 %s",
                    direction, symbol, score, conviction, leg_reason,
                )
            elif score > 0.90:
                near_info = legendary_mode.get_near_legendary_info(gate_states, score, symbol)
                if near_info:
                    LOGGER.info(
                        "[NEAR-LEGENDARY] %s %s score=%.4f platinum=%d/6 failed=%s supporting=%d",
                        direction, symbol, score,
                        near_info["platinum_passed"], near_info["platinum_failed"],
                        near_info["supporting_count"],
                    )

        if not _mt5_enabled or not _auto_exec:
            last_t = _last_signal_tick.get(symbol, 0)
            if tick_count - last_t < _SIGNAL_COOLDOWN_TICKS:
                continue
            _last_signal_tick[symbol] = tick_count
        if _use_oanda and _auto_exec:
            sl_pips = float(tick.get("sl_pips", os.getenv("SL_PIPS", "5")))
            tp_pips = float(tick.get("tp_pips", os.getenv("TP_PIPS", "12.5")))
            _exec_lot = 0.01

            # --- Apply bonus layer size multiplier (anti-martingale, state machine, etc.) ---
            _exec_lot = max(0.01, _exec_lot * _bonus_size_mult)

            # --- Legendary sizing override ---
            if _is_legendary_trade:
                tp_pips = legendary_mode.compute_legendary_tp(sl_pips)
                account_bal = _get_account_balance()
                _exec_lot = legendary_mode.compute_legendary_lots(
                    0.90, tp_pips, sl_pips, account_bal
                )
                if SCALE_IN_ENABLED and scale_in_engine is not None:
                    _exec_lot = scale_in_engine.get_initial_lot(_exec_lot)
                LOGGER.info(
                    "[LEGENDARY EXEC] %s %s sl=%.1f tp=%.1f (4:1 RR) lot=%.2f",
                    direction, symbol, sl_pips, tp_pips, _exec_lot,
                )

            # --- Entry Sniper: wait for micro-pullback fill ---
            if ENTRY_SNIPER_ENABLED:
                try:
                    _sniper_ready, _sniper_fill = entry_sniper.on_tick(symbol, current_mid, float(tick.get("pip_size", 0.0001)), tick_count)
                    if not _sniper_ready:
                        if tick_count % 20 == 0:
                            LOGGER.info("[ENTRY_SNIPER] %s %s: waiting for pullback", direction, symbol)
                        continue
                    if _sniper_fill:
                        tick["_sniper_fill_price"] = _sniper_fill
                except Exception:
                    pass

            # --- Structural SL: compute optimal stop-loss placement ---
            if STRUCTURAL_SL_ENABLED:
                try:
                    _default_sl = float(tick.get("sl_pips", sl_pips))
                    _struct_sl = structural_sl.compute_sl(symbol, direction, current_mid, float(tick.get("pip_size", 0.0001)), _default_sl)
                    if _struct_sl > 0:
                        if direction == "BUY":
                            _derived_sl_pips = (current_mid - _struct_sl) / float(tick.get("pip_size", 0.0001))
                        else:
                            _derived_sl_pips = (_struct_sl - current_mid) / float(tick.get("pip_size", 0.0001))
                        if _derived_sl_pips > 0 and _derived_sl_pips < sl_pips * 2:
                            sl_pips = _derived_sl_pips
                            tick["_structural_sl_pips"] = sl_pips
                except Exception:
                    pass

            # --- RL Brain: choose execution action ---
            if RL_BRAIN_ENABLED and rl_brain is not None:
                try:
                    _rl_action_idx, _rl_action_name = rl_brain.select_action(
                        spread_bps=float(tick.get("spread_bps", 0)),
                        delta=float(tick.get("delta", 0)),
                        queue_depth=float(tick.get("depth", 0)),
                        time_since_print_ms=0.0,
                    )
                    tick["_rl_action"] = _rl_action_name
                    if _rl_action_name == "wait":
                        LOGGER.info("[RL_BRAIN] %s %s: RL says WAIT — deferring execution", direction, symbol)
                        log_signal(conn, tick, direction, score, adjusted_score, gate_states, l3_info, bias_breakdown, executed=False, tick_count=tick_count)
                        conn.commit()
                        continue
                    if _rl_action_name == "limit":
                        LOGGER.info("[RL_BRAIN] %s %s: RL suggests LIMIT order (falling back to market)", direction, symbol)
                except Exception:
                    pass

            # --- Execution Algo Engine: estimate market impact ---
            if EXEC_ALGO_ENABLED and exec_algo_engine is not None:
                try:
                    _impact = exec_algo_engine.estimate_impact(symbol, _exec_lot)
                    if _impact.get("total_impact_bps", 0) > 5.0:
                        LOGGER.warning("[EXEC_ALGO] %s: high market impact %.1f bps — reducing lot size", symbol, _impact["total_impact_bps"])
                        _exec_lot = max(0.01, _exec_lot * 0.5)
                    tick["_exec_impact"] = _impact
                except Exception:
                    pass

            # --- Portfolio Risk: VaR/CVaR check before execution ---
            if PORTFOLIO_RISK_ENABLED and portfolio_risk is not None:
                try:
                    _portfolio_blocked = False
                    _var_result = portfolio_risk.parametric_var(confidence=0.95)
                    if _var_result.get("var", 0) < -0.02:
                        LOGGER.warning("[PORTFOLIO_RISK] VaR=%.4f exceeds 2%% limit — blocking trade", _var_result["var"])
                        log_signal(conn, tick, direction, score, adjusted_score, gate_states, l3_info, bias_breakdown, executed=False, tick_count=tick_count)
                        conn.commit()
                        _portfolio_blocked = True
                    if not _portfolio_blocked:
                        _stress = portfolio_risk.stress_test()
                        for _scenario, _s_result in _stress.items():
                            if _s_result.get("portfolio_impact_pct", 0) < -5.0:
                                LOGGER.warning("[PORTFOLIO_RISK] Stress scenario '%s': %.1f%% impact — blocking", _scenario, _s_result["portfolio_impact_pct"])
                                log_signal(conn, tick, direction, score, adjusted_score, gate_states, l3_info, bias_breakdown, executed=False, tick_count=tick_count)
                                conn.commit()
                                _portfolio_blocked = True
                                break
                    if _portfolio_blocked:
                        continue
                except Exception:
                    pass

            result = oanda_execute_trade(symbol, direction, lot_size=_exec_lot, sl_pips=sl_pips, tp_pips=tp_pips, tick=tick)
        if result and result.get("status") == "filled":
            LOGGER.info("OANDA EXECUTED: %s %s fill=%.5f ticket=%s", direction, symbol, result["fill_price"], result["ticket"])
            _open_symbols.add(symbol)
            _ticket_to_symbol[result["ticket"]] = symbol
            log_signal(conn, tick, direction, score, adjusted_score, gate_states, l3_info, bias_breakdown, executed=True, tick_count=tick_count)
            conn.commit()
            # --- Register with exit manager (legendary trail if applicable) ---
            if exit_manager is not None:
                _fill = result.get("fill_price", float(tick.get("mid", 0)))
                _pip = float(tick.get("pip_size", 0.0001))
                if direction == "BUY":
                    _sl_p = _fill - sl_pips * _pip
                    _tp_p = _fill + tp_pips * _pip
                else:
                    _sl_p = _fill + sl_pips * _pip
                    _tp_p = _fill - tp_pips * _pip
                exit_manager.register_position(
                    ticket=int(result["ticket"]),
                    symbol=symbol,
                    direction=direction,
                    entry_price=_fill,
                    sl_price=_sl_p,
                    tp_price=_tp_p,
                    lot_size=_exec_lot,
                    is_legendary=_is_legendary_trade,
                    sl_pips=sl_pips,
                )
                exit_manager.set_entry_tick_count(int(result["ticket"]), tick_count)
            # --- Scale-in: register first tranche ---
            if SCALE_IN_ENABLED and scale_in_engine is not None and _is_legendary_trade:
                scale_in_engine.start_scale_in(
                    symbol, direction, _exec_lot / 0.33 if _exec_lot > 0.01 else 0.03,
                    result["fill_price"], _pip, gate_states,
                )
                # --- Vector Memory: store this signal for future similarity checks ---
                if VECTOR_MEMORY_ENABLED and vector_memory is not None:
                    try:
                        vector_memory.store_signal(
                            signal_id=f"{symbol}_{direction}_{tick_count}",
                            framework_scores=framework_scores, l3_features=l3_info, tick=tick, score=score,
                        )
                    except Exception:
                        pass
                else:
                    LOGGER.info("OANDA signal-only (execution failed): %s %s score=%.4f", direction, symbol, score)
                    log_signal(conn, tick, direction, score, adjusted_score, gate_states, l3_info, bias_breakdown, executed=False, tick_count=tick_count)
                    conn.commit()
            else:
                LOGGER.info("Signal-only: %s %s score=%.4f adj=%.4f (MT5=%s OANDA=%s AUTO=%s)", direction, symbol, score, adjusted_score, _mt5_enabled, _use_oanda, _auto_exec)
                log_signal(conn, tick, direction, score, adjusted_score,
                    gate_states, l3_info, bias_breakdown, executed=False, tick_count=tick_count)
                conn.commit()
                trade_replay.log_trade_decision(symbol, direction, score, score, adjusted_score,
                    gate_states=gate_states, l3_features=l3_info, bias_breakdown=bias_breakdown,
                    dom_health=dom_checker.get_status().get("status", "unknown"),
                    risk_checks=risk_result)
                if paper_trading.is_enabled() and symbol not in _open_symbols:
                    try:
                        pip_size_pt = float(tick.get("pip_size", 0.01 if "JPY" in symbol or symbol.startswith("XAU") else 0.0001))
                        sl_pips_pt = float(tick.get("sl_pips", os.getenv("SL_PIPS", "5")))
                        tp_pips_pt = float(tick.get("tp_pips", os.getenv("TP_PIPS", "12.5")))
                        paper_trading.execute_paper_trade(
                            symbol=symbol, direction=direction,
                            sl_pips=sl_pips_pt, tp_pips=tp_pips_pt,
                            tick=tick, tick_count=tick_count,
                            score=score, raw_score=score,
                            gate_states=gate_states,
                        )
                    except Exception as exc:
                        LOGGER.debug("Paper trade error: %s", exc)
                continue
            kelly_wr, kelly_aw, kelly_al, kelly_bal = _compute_kelly_from_history(conn, account_balance)
            lot_size = kelly_lot_size(
                win_rate=kelly_wr,
                avg_win=kelly_aw,
                avg_loss=kelly_al,
                account_balance=kelly_bal,
            )
            pip_size = float(tick.get("pip_size", 0.01 if "JPY" in tick["symbol"] or tick["symbol"].startswith("XAU") else 0.0001))
            sl_pips = float(tick.get("sl_pips", os.getenv("SL_PIPS", "5")))
            tp_pips = float(tick.get("tp_pips", os.getenv("TP_PIPS", "12.5")))
            result = execute_trade(
                symbol=os.getenv("MT5_SYMBOL", tick.get("execution_symbol", tick["symbol"])),
                direction=direction,
                lot_size=lot_size,
                sl_pips=sl_pips,
                tp_pips=tp_pips,
            )
            if result:
                latency_tracker.mark_fill()
                exec_quality_logger.log_fill(
                    symbol=symbol, direction=direction, lot_size=lot_size,
                    requested_price=float(tick.get("ask" if direction == "BUY" else "bid", 0)),
                    fill_price=float(result["price"]),
                    slippage_pips=float(result.get("slippage_pips", 0)),
                    spread_at_entry=float(tick.get("spread_bps", 0)),
                    fill_latency_ms=0,
                    ticket=int(result["ticket"]),
                    retcode=int(result.get("retcode", 0)),
                    score=score, raw_score=score, adjusted_score=adjusted_score,
                    l3_spoof_signal=float(l3_info.get("spoof_reversal_signal", 0)),
                    l3_adverse_risk=float(l3_info.get("adverse_selection_risk", 0)),
                    dom_health=dom_checker.get_status().get("status", "unknown"),
                )
                trade_replay.log_trade_decision(symbol, direction, score, score, adjusted_score,
                    gate_states=gate_states, l3_features=l3_info, bias_breakdown=bias_breakdown,
                    dom_health=dom_checker.get_status().get("status", "unknown"),
                    risk_checks=risk_result, ticket=int(result["ticket"]))
                trade_id = log_trade(conn, tick, direction, gate_states, result)
                trade_tracker.register_trade(int(result["ticket"]), trade_id)
                log_signal(conn, tick, direction, score, adjusted_score,
                    gate_states, l3_info, bias_breakdown, executed=True,
                    entry_price=float(result["price"]), tick_count=tick_count)
                conn.commit()
                if exit_manager is not None and "ticket" in result:
                    bid = float(tick.get("bid", 0))
                    ask = float(tick.get("ask", 0))
                    if direction == "BUY":
                        sl_price = result["price"] - sl_pips * pip_size
                        tp_price = result["price"] + tp_pips * pip_size
                    else:
                        sl_price = result["price"] + sl_pips * pip_size
                        tp_price = result["price"] - tp_pips * pip_size
                exit_manager.register_position(
                    ticket=int(result["ticket"]),
                    symbol=tick["symbol"],
                    direction=direction,
                    entry_price=result["price"],
                    sl_price=sl_price,
                    tp_price=tp_price,
                    lot_size=lot_size,
                    is_legendary=_is_legendary_trade,
                    sl_pips=sl_pips,
                )
        exit_manager.set_entry_tick_count(int(result["ticket"]), tick_count)
        partial_closer.register_trade(
            ticket=int(result["ticket"]),
            symbol=tick["symbol"],
            direction=direction,
            entry_price=result["price"],
            sl_price=sl_price,
            lot_size=lot_size,
        )
        asyncio.create_task(telegram.send_trade_alert({
            "symbol": tick["symbol"],
            "direction": direction,
            "entry_price": result["price"],
            "sl_price": sl_price,
            "lot_size": lot_size,
            "quality_score": adjusted_score,
            "iv_skew": iv_skew,
            "rr_25d": get_rr_25d(tick.get("symbol", "")),
        }))
        _open_symbols.add(symbol)
        _ticket_to_symbol[int(result["ticket"])] = symbol
        LOGGER.info("Trade executed: %s score=%.4f adj=%.4f bias=%.4f(clamped from %.4f) ticket=%s",
            tick["symbol"], score, adjusted_score, clamped_bias, raw_bias, result["ticket"])

    if tick_count % 10 == 0:
        for ticket in partial_closer.active_tickets:
            pc_result = partial_closer.check_partial_close(ticket, current_mid)

    if paper_trading.is_enabled() and tick_count % 5 == 0:
        try:
            paper_trading.check_sl_tp(tick, tick_count)
        except Exception as exc:
            LOGGER.debug("Paper trading SL/TP check error: %s", exc)

        if exit_manager is not None and tick_count % 10 == 0:
            for ticket in list(exit_manager.open_positions.keys()):
                exit_result = exit_manager.evaluate_exit(ticket, tick)

                if RL_EXIT_AGENT_ENABLED:
                    try:
                        _pos_info = exit_manager.open_positions.get(ticket, {})
                        _rl_state = {
                            "pnl_pips": exit_result.get("pnl_pips", 0),
                            "ticks_held": tick_count - exit_manager.get_entry_tick_count(ticket, 0),
                            "is_legendary": _pos_info.get("is_legendary", False),
                        }
                        _rl_exit_action = rl_exit_agent.get_action(_rl_state)
                        if _rl_exit_action == "EXIT_NOW":
                            exit_result = {"should_exit": True, "reason": "rl_exit_agent"}
                        elif _rl_exit_action == "MOVE_SL_BE":
                            _entry = _pos_info.get("entry_price", 0)
                            if _entry > 0:
                                exit_result = {"should_exit": False, "reason": "move_breakeven", "new_sl": _entry}
                    except Exception:
                        pass

                if exit_result.get("should_exit"):
                    _exit_sym = _ticket_to_symbol.pop(ticket, "")
                    if _use_oanda:
                        closed = oanda_close_trade(ticket)
                    else:
                        from execution.mt5_executor import close_trade
                        closed = close_trade(ticket)
                    if closed:
                        exit_manager.unregister_position(ticket)
                        _open_symbols.discard(_exit_sym)
                        LOGGER.warning("Dynamic exit triggered: ticket=%d reason=%s", ticket, exit_result["reason"])
                        try:
                            _exit_pnl = float(closed.get("pnl", 0)) if isinstance(closed, dict) else 0.0
                            if ANTI_MARTINGALE_ENABLED:
                                anti_martingale.record_outcome(_exit_pnl)
                            if DRAWDOWN_VELOCITY_ENABLED:
                                drawdown_velocity.record_pnl(_exit_pnl)
                            if ES_RISK_ENABLED:
                                es_risk.update_pnl(_exit_pnl)
                            if RUIN_CALC_ENABLED:
                                ruin_calc.update_from_trade(_exit_pnl)
                            if LAYER_PERFORMANCE_ENABLED:
                                _active_layers = list(tick.get("_bonus_layers", {}).get("layers", {}).keys()) if isinstance(tick, dict) else []
                                layer_performance_tracker.record_trade(_active_layers, "WIN" if _exit_pnl > 0 else "LOSS")
                            if COUNTERFACTUAL_ENABLED:
                                try:
                                    counterfactual_analyzer.record_trade(_exit_sym, 0.0, 0, 0.0, 0, _exit_pnl)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                elif exit_result.get("reason") in ("move_breakeven", "move_trailing_sl", "activate_trailing"):
                    new_sl = exit_result.get("new_sl")
                    reason = exit_result["reason"]
                    if reason == "activate_trailing" and new_sl is None:
                        exit_manager.confirm_sl_update(ticket, 0.0, reason)
                        LOGGER.info("Trailing activated: ticket=%d", ticket)
                    elif new_sl is not None:
                        if _use_oanda:
                            sl_ok = oanda_modify_sl(ticket, new_sl)
                        else:
                            sl_ok = modify_sl(ticket, new_sl)
                        if sl_ok:
                            exit_manager.confirm_sl_update(ticket, new_sl, reason)
                            LOGGER.info("SL adjusted: ticket=%d reason=%s new_sl=%.5f", ticket, reason, new_sl)
                        else:
                            LOGGER.error("SL modify FAILED: ticket=%d — state not updated", ticket)

        conn.commit()


def _prune_database(conn: sqlite3.Connection) -> None:
    """Delete massive tick data older than 24 hours to prevent disk explosion."""
    try:
        now_ms = int(time.time() * 1000)
        cutoff_ms = now_ms - (24 * 60 * 60 * 1000)
        LOGGER.info("System: Pruning massive tables (tick_log, trade_audit) older than %s...", cutoff_ms)
        
        # 1. Prune tick_log
        conn.execute("DELETE FROM tick_log WHERE timestamp < ?", (cutoff_ms,))
        # 2. Prune trade_audit
        conn.execute("DELETE FROM trade_audit WHERE timestamp < ?", (cutoff_ms,))
        
        conn.commit()
        LOGGER.info("System: Database deletion complete. Starting VACUUM to reclaim space...")
        # 3. Optimize database file size
        conn.execute("VACUUM")
        LOGGER.info("System: Database pruning and VACUUM complete.")
    except Exception as e:
        LOGGER.error("System: Pruning failed: %s", e)


def _run_vanguard_cli(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [VANGUARD_PYTHON, VANGUARD_CLI, command],
        cwd=str(VANGUARD_ROOT),
        text=True,
        capture_output=True,
        timeout=30,
    )


def _start_vanguard_for_overseer() -> bool:
    if not VANGUARD_AUTO_START:
        LOGGER.info("VANGUARD auto-start disabled by VANGUARD_AUTO_START=false")
        return False

    if not Path(VANGUARD_PYTHON).exists() or not Path(VANGUARD_CLI).exists():
        LOGGER.warning(
            "VANGUARD auto-start skipped: missing python=%s cli=%s",
            VANGUARD_PYTHON,
            VANGUARD_CLI,
        )
        return False

    try:
        result = _run_vanguard_cli("start")
    except Exception as exc:
        LOGGER.error("VANGUARD auto-start failed: %s", exc)
        return False

    output = (result.stdout or "") + (result.stderr or "")
    for line in output.splitlines():
        LOGGER.info("VANGUARD start: %s", line)

    if result.returncode != 0:
        LOGGER.error("VANGUARD auto-start command failed with code %s", result.returncode)
        return False

    return "started successfully" in output.lower()


def _stop_vanguard_for_overseer(started_by_overseer: bool) -> None:
    if not started_by_overseer:
        LOGGER.info("VANGUARD was not started by this OVERSEER run; leaving it untouched.")
        return

    try:
        result = _run_vanguard_cli("stop")
    except Exception as exc:
        LOGGER.error("VANGUARD auto-stop failed: %s", exc)
        return

    output = (result.stdout or "") + (result.stderr or "")
    for line in output.splitlines():
        LOGGER.info("VANGUARD stop: %s", line)
    if result.returncode != 0:
        LOGGER.error("VANGUARD auto-stop command failed with code %s", result.returncode)


def _start_cqg_bridge_for_overseer() -> subprocess.Popen[Any] | None:
    """Spawn the CQG WebAPI bridge as a subprocess when CQG_ENABLED=true."""
    if not CQG_ENABLED:
        return None

    bridge_script = Path(__file__).resolve().parent / "tools" / "cqg_mbo_bridge.py"
    python_exe = sys.executable
    if not bridge_script.exists():
        LOGGER.warning("CQG bridge script not found: %s", bridge_script)
        return None

    try:
        proc = subprocess.Popen(
            [python_exe, str(bridge_script)],
            cwd=str(Path(__file__).resolve().parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        LOGGER.info("CQG bridge subprocess started (pid=%s)", proc.pid)
        return proc
    except Exception as exc:
        LOGGER.error("CQG bridge auto-start failed: %s", exc)
        return None


def _stop_cqg_bridge_for_overseer(proc: subprocess.Popen[Any] | None) -> None:
    if proc is None:
        return
    try:
        if sys.platform == "win32":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
        proc.wait(timeout=5)
        LOGGER.info("CQG bridge subprocess stopped")
    except Exception as exc:
        LOGGER.warning("CQG bridge subprocess kill error: %s", exc)
        try:
            proc.kill()
        except Exception:
            pass


async def run() -> None:
    init_db(DB_PATH)
    
    while True: # Outer supervisor loop
        LOGGER.info("Starting OVERSEER v12 backend supervisor...")
        vanguard_started_by_overseer = _start_vanguard_for_overseer()
        queue: asyncio.Queue = asyncio.Queue(maxsize=100_000)
        l3_queue: asyncio.Queue = asyncio.Queue(maxsize=200_000)
        event_queue: asyncio.Queue = asyncio.Queue()
        
        transport = None
        watch_task = None
        zmq_task = None
        dashboard_server = None
        mt5_conn = None
        cqg_proc = None

        try:
            transport, _, watch_task = await start_udp_listener(queue, event_queue=event_queue, l3_queue=l3_queue)

            if CQG_ENABLED:
                cqg_proc = _start_cqg_bridge_for_overseer()

            if ZMQ_ENABLED or CQG_ENABLED:
                zmq_task = await start_zmq_subscriber(queue, event_queue=event_queue)
                if zmq_task:
                    LOGGER.info("ZMQ bridge activated.")

            registry = GateRegistry()
            l3_scorer = L3RealTimeScorer()
            if l3_queue is not None:
                asyncio.create_task(_drain_l3_queue(l3_queue, l3_scorer))
                LOGGER.info("L3 raw event drain task started (UDP→l3_scorer)")
            
            exit_manager = DynamicExitManager() if DYNAMIC_EXIT_ENABLED else None
            instrument_config = InstrumentConfig.get_instance()

            candle_aggregator = CandleAggregator()
            dxy_calc = DXYCalculator()
            risk_regime = RiskRegimeClassifier()
            telegram = TelegramAlerter()
            post_news_filter = PostReleaseContinuationFilter()
            partial_closer = PartialCloseManager()
            trade_tracker = TradeTracker()

            dom_checker = DOMQualityChecker()
            currency_tracker = CurrencyExposureTracker()
            risk_engine = RiskEngine(exposure_tracker=currency_tracker)
            latency_tracker = LatencyTracker()
            drift_monitor = DriftMonitor()
            order_book_engine = OrderBookEngine()
            per_symbol_model = PerSymbolModelManager()
            exec_quality_logger = ExecutionQualityLogger()
            trade_replay = TradeReplay()
            paper_trading = PaperTradingEngine()
            dynamic_selector = DynamicPairSelector()

            # --- 16 Institutional Modules ---
            toxicity_engine = ToxicityEngine() if VPIN_ENABLED else None
            ofi_manager = OFIManager() if OFI_ENABLED else None
            regime_intel = RegimeIntelEngine() if REGIME_INTEL_ENABLED else None
            cross_asset = CrossAssetEngine() if CROSS_ASSET_ENABLED else None
            cb_nlp = CentralBankNLP() if CB_NLP_ENABLED else None
            vol_surface_mgr = VolSurfaceManager() if VOL_SURFACE_ENABLED else None
            pairs_engine = PairsEngine() if PAIRS_STAT_ENABLED else None
            network_engine = NetworkEngine() if NETWORK_ENABLED else None
            self_supervised = SelfSupervisedEngine() if SELF_SUPERVISED_ENABLED else None
            sequence_core = SequenceCore() if SEQUENCE_CORE_ENABLED else None
            xai_explainer = XAIExplainer() if XAI_ENABLED else None
            vector_memory = VectorMemory() if VECTOR_MEMORY_ENABLED else None
            rl_brain = TabularRLBrain() if RL_BRAIN_ENABLED else None
            causal_engine = CausalEngine() if CAUSAL_ENGINE_ENABLED else None
            attention_gate = AttentionGateWeighting() if ATTENTION_GATE_ENABLED else None
            exec_algo_engine = ExecutionAlgoEngine() if EXEC_ALGO_ENABLED else None
            portfolio_risk = PortfolioRiskEngine() if PORTFOLIO_RISK_ENABLED else None

            session_levels = SessionLevels()
            scale_in_engine = ScaleInEngine() if SCALE_IN_ENABLED else None

            _inst_module_names = []
            if toxicity_engine: _inst_module_names.append("VPIN")
            if ofi_manager: _inst_module_names.append("OFI")
            if regime_intel: _inst_module_names.append("RegimeIntel")
            if cross_asset: _inst_module_names.append("CrossAsset")
            if cb_nlp: _inst_module_names.append("CB_NLP")
            if vol_surface_mgr: _inst_module_names.append("VolSurface")
            if pairs_engine: _inst_module_names.append("PairsStat")
            if network_engine: _inst_module_names.append("Network")
            if self_supervised: _inst_module_names.append("SelfSupervised")
            if sequence_core: _inst_module_names.append("SeqCore")
            if xai_explainer: _inst_module_names.append("XAI")
            if vector_memory: _inst_module_names.append("VectorMem")
            if rl_brain: _inst_module_names.append("RL_Brain")
            if causal_engine: _inst_module_names.append("Causal")
            if attention_gate: _inst_module_names.append("Attention")
            if exec_algo_engine: _inst_module_names.append("ExecAlgo")
            if portfolio_risk: _inst_module_names.append("PortfolioRisk")
            if _inst_module_names:
                LOGGER.info("Institutional modules active: %s", " ".join(_inst_module_names))

            # Backfill vector memory from existing signal_log on startup
            if VECTOR_MEMORY_ENABLED and vector_memory is not None:
                try:
                    loop = asyncio.get_running_loop()
                    loop.run_in_executor(None, vector_memory.backfill_from_db)
                    LOGGER.info("Vector memory backfill dispatched to background thread")
                except Exception:
                    pass

            # Start scrapers in the background to avoid blocking tick processing
            asyncio.create_task(asyncio.to_thread(scrape_calendar, force=True))
            asyncio.create_task(asyncio.to_thread(scrape_options_iv, force=True, candle_aggregator=candle_aggregator))
            asyncio.create_task(asyncio.to_thread(scrape_fred, force=True))
            asyncio.create_task(asyncio.to_thread(scrape_ecb, force=True))
            asyncio.create_task(asyncio.to_thread(scrape_finnhub, force=True))
            
            asyncio.create_task(telegram.send_system_alert("OVERSEER v12 backend started/restarted."))

            if DASHBOARD_ENABLED:
                try:
                    from core.dashboard import start_dashboard
                    dashboard_server = start_dashboard()
                    import threading
                    dashboard_thread = threading.Thread(target=dashboard_server.serve_forever, daemon=True)
                    dashboard_thread.start()
                    LOGGER.info("Dashboard: http://localhost:%s", os.getenv("DASHBOARD_PORT", "8080"))
                except Exception as e:
                    LOGGER.warning("Dashboard failed to start: %s", e)

            if MT5_ENABLED:
                try:
                    mt5_conn = MT5ConnectionManager(
                        os.environ["MT5_ACCOUNT"],
                        os.environ["MT5_PASSWORD"],
                        os.environ["MT5_SERVER"],
                    )
                    mt5_conn.connect()
                    asyncio.create_task(mt5_conn.heartbeat_loop())
                except Exception as e:
                    LOGGER.error("Failed to connect to MT5: %s", e)

            LOGGER.info("OVERSEER v12 backend online. ZMQ=%s DynamicExit=%s", ZMQ_ENABLED, DYNAMIC_EXIT_ENABLED)
            
            with sqlite3.connect(DB_PATH, timeout=10, isolation_level=None) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                load_pending_from_db(conn)
                _open_symbols, _ticket_to_symbol = _reconcile_positions(
                    conn, exit_manager, partial_closer, trade_tracker,
                )
                await _process_queue(
            queue, conn, registry, l3_scorer, exit_manager,
            candle_aggregator, dxy_calc, risk_regime, telegram,
            post_news_filter, partial_closer, trade_tracker, instrument_config,
            dom_checker, currency_tracker, risk_engine, latency_tracker,
            drift_monitor, order_book_engine, per_symbol_model,
            exec_quality_logger, trade_replay, paper_trading,
            dynamic_selector,
            toxicity_engine=toxicity_engine,
            ofi_manager=ofi_manager,
            regime_intel=regime_intel,
            cross_asset=cross_asset,
            cb_nlp=cb_nlp,
            vol_surface_mgr=vol_surface_mgr,
            pairs_engine=pairs_engine,
            network_engine=network_engine,
            self_supervised=self_supervised,
            sequence_core=sequence_core,
            xai_explainer=xai_explainer,
            vector_memory=vector_memory,
            rl_brain=rl_brain,
            causal_engine=causal_engine,
            attention_gate=attention_gate,
            exec_algo_engine=exec_algo_engine,
            portfolio_risk=portfolio_risk,
            _open_symbols=_open_symbols, _ticket_to_symbol=_ticket_to_symbol,
            l3_queue=l3_queue,
        )
        except Exception as e:
            LOGGER.error("Main loop crashed: %s. Restarting in 5s...", e, exc_info=True)
            await asyncio.sleep(5.0)
        finally:
            if watch_task: watch_task.cancel()
            if zmq_task: zmq_task.cancel()
            if transport: transport.close()
            if dashboard_server: 
                try: dashboard_server.shutdown()
                except: pass
            shutdown_mt5()
            _stop_vanguard_for_overseer(vanguard_started_by_overseer)
            _stop_cqg_bridge_for_overseer(cqg_proc)
            LOGGER.info("Supervisor cleaned up resources.")


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        LOGGER.info("KeyboardInterrupt received. Shutdown complete.")
