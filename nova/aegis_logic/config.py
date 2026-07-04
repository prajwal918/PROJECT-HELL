import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
AEGIS_DIR = Path(__file__).parent

ASSET = "EUR/USD"
TRADE_DURATION = 900
STAKE_USD = 10.0
MAX_DAILY_TRADES = 3
MAX_DAILY_LOSS_USD = 50.0

ABSORPTION_WINDOW_TICKS = 1000
MIN_ABSORPTION_VOLUME = 500.0
MIN_DEPTH_RETENTION_PCT = 70.0
MIN_REJECTION_RATIO = 2.0

CONFLUENCE_POINTS = {
    "absorption_detection": 25,
    "depth_retention": 25,
    "rejection_ratio": 25,
    "breakout_confirmation": 25,
}

MIN_CONFIDENCE_SCORE = 75.0

OVERSEER_DIR = PROJECT_ROOT / "overseer"
OVERSEER_DATA_DIR = OVERSEER_DIR / "data"

NEXUS_WS_URL = os.getenv("NEXUS_WS_URL", "ws://localhost:9001")

DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN", "")
DERIV_APP_ID = os.getenv("DERIV_APP_ID", "1089")
DERIV_API_BASE = os.getenv("DERIV_API_BASE", "https://api.derivws.com").rstrip("/")

USE_DEMO_MODE = os.getenv("USE_DEMO_MODE", "true").lower() == "true"

LOG_FILE = os.path.join(AEGIS_DIR, "aegis.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

OVERSEER_L3_DATA_PATH = OVERSEER_DATA_DIR / "l3_mbo.json"
OVERSEER_SIGNALS_PATH = OVERSEER_DATA_DIR / "signals.json"