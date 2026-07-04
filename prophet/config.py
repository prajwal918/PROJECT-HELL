import os
from dotenv import load_dotenv

load_dotenv()

# ── Deriv Credentials ───────────────────────────────────────────────────────────
DERIV_API_TOKEN = os.path.expandvars(os.getenv("DERIV_API_TOKEN", "").strip())
DERIV_APP_ID    = os.getenv("DERIV_APP_ID", "").strip()
DERIV_API_BASE  = os.getenv("DERIV_API_BASE", "https://api.derivws.com").rstrip("/")

# ── Olymp Trade Credentials (Legacy) ──────────────────────────────────────────
OLYMP_EMAIL     = os.getenv("OLYMP_EMAIL", "")
OLYMP_PASSWORD  = os.getenv("OLYMP_PASSWORD", "")
DEMO_MODE       = os.getenv("DEMO_MODE", "true").lower() == "true"

# ── Trading Parameters ─────────────────────────────────────────────────────────
ASSET           = os.getenv("ASSET", "frxEURUSD")
STAKE_USD       = float(os.getenv("STAKE_USD", "10.0"))
TRADE_DURATION  = int(os.getenv("TRADE_DURATION", "300"))

# ── Risk Management ────────────────────────────────────────────────────────────
MAX_DAILY_TRADES    = int(os.getenv("MAX_DAILY_TRADES", "1"))
MAX_DAILY_LOSS_USD  = float(os.getenv("MAX_DAILY_LOSS_USD", "50.0"))

# ── Signal Engine Parameters ───────────────────────────────────────────────────
# Strict one-trade 15-minute binary configuration.
VOLUME_PROFILE_LOOKBACK     = int(os.getenv("VOLUME_PROFILE_LOOKBACK", "96"))
KEY_LEVEL_TOLERANCE_PIPS    = float(os.getenv("KEY_LEVEL_TOLERANCE_PIPS", "2"))
MIN_VOLUME_ZSCORE           = float(os.getenv("MIN_VOLUME_ZSCORE", "2.5"))
CVD_DIVERGENCE_THRESHOLD    = float(os.getenv("CVD_DIVERGENCE_THRESHOLD", "0.35"))
MIN_CANDLES_FOR_SIGNAL      = int(os.getenv("MIN_CANDLES_FOR_SIGNAL", "96"))
CANDLE_INTERVAL_SECONDS     = int(os.getenv("CANDLE_INTERVAL_SECONDS", "900"))
MIN_SIGNAL_CONFIDENCE       = float(os.getenv("MIN_SIGNAL_CONFIDENCE", "0.85"))

MIN_SIGNAL_BODY_RATIO       = float(os.getenv("MIN_SIGNAL_BODY_RATIO", "0.40"))
MIN_REJECTION_WICK_RATIO    = float(os.getenv("MIN_REJECTION_WICK_RATIO", "0.45"))
MIN_TREND_STRENGTH          = float(os.getenv("MIN_TREND_STRENGTH", "0.55"))
MAX_SPREAD_PIPS             = float(os.getenv("MAX_SPREAD_PIPS", "2.0"))
ICEBERG_RELOAD_MIN          = int(os.getenv("ICEBERG_RELOAD_MIN", "5"))
ORDERID_DEPTH_THRESHOLD     = float(os.getenv("ORDERID_DEPTH_THRESHOLD", "0.60"))
LOCATION_HISTORY_RESPECT    = int(os.getenv("LOCATION_HISTORY_RESPECT", "4"))
CORRELATED_ASSETS_CHECK     = os.getenv(
    "CORRELATED_ASSETS_CHECK", "false"
).lower() == "true"
SESSION_WINDOW_RESTRICT     = os.getenv(
    "SESSION_WINDOW_RESTRICT", "true"
).lower() == "true"
LONDON_OPEN_TIME            = "08:00"   # EST time
LONDON_CLOSE_TIME           = "11:00"   # EST time
HTF_ALIGNMENT_CHECK         = os.getenv(
    "HTF_ALIGNMENT_CHECK", "false"
).lower() == "true"

# ── WebSocket URLs ─────────────────────────────────────────────────────────────
OLYMP_WS_URL    = "wss://ws.olymptrade.com/"
OLYMP_API_URL   = "https://api.olymptrade.com"

# ── Broker Selection ───────────────────────────────────────────────────────────
_TOKEN_PLACEHOLDERS = {"", "$CLEAN_TOKEN", "your_token_here", "your_deriv_token_here"}
USE_DERIV = DERIV_API_TOKEN not in _TOKEN_PLACEHOLDERS

# ── Logging ────────────────────────────────────────────────────────────────────
DB_PATH         = "prophet_trades.db"
LOG_FILE        = "prophet.log"
LOG_LEVEL       = "INFO"

# ── Process Resource Limits ────────────────────────────────────────────────────
MAX_MEMORY_MB   = 512       # Maximum memory usage in MB
MAX_CPU_PERCENT = 30        # Maximum CPU usage percentage
UDP_PORT        = 12346     # CME Level 3 UDP port (different from OVERSEER's 12345)
UDP_HOST        = "127.0.0.1"
