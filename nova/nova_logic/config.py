import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
NOVA_DIR = Path(__file__).parent

ASSET = "EUR/USD"
TRADE_DURATION = 60
STAKE_USD = 10.0
MAX_DAILY_TRADES = 3
MAX_DAILY_LOSS_USD = 30.0

ENTRY_DELAY_SEC = 90
PRE_NEWS_WINDOW_SEC = 15
POST_NEWS_WINDOW_SEC = 30

BOOK_THINNING_THRESHOLD = 25.0
ANCHOR_RATIO_THRESHOLD = 60.0
MIN_CONFIDENCE_SCORE = 75.0

CONFLUENCE_POINTS = {
    "event_impact": 25,
    "directional_bias": 25,
    "book_thinning": 25,
    "anchor_survival": 25,
}

OVERSEER_DIR = PROJECT_ROOT / "overseer"
OVERSEER_DATA_DIR = OVERSEER_DIR / "data"

NEXUS_WS_URL = os.getenv("NEXUS_WS_URL", "ws://localhost:9001")
OVERSEER_UDP_HOST = os.getenv("OVERSEER_UDP_HOST", "127.0.0.1")
OVERSEER_UDP_PORT = int(os.getenv("OVERSEER_UDP_PORT", "12347"))

DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN", "")
DERIV_APP_ID = os.getenv("DERIV_APP_ID", "1089")
DERIV_API_BASE = os.getenv("DERIV_API_BASE", "https://api.derivws.com").rstrip("/")

USE_DEMO_MODE = os.getenv("USE_DEMO_MODE", "true").lower() == "true"

LOG_FILE = os.path.join(NOVA_DIR, "nova.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

TIMEZONE = "America/New_York"

NEWS_CALENDARS = ["FF", "ECB", "BOE", "SNB", "BOJ", "RBA", "RBNZ", "BANK_OF_CANADA"]

OVERSEER_L3_DATA_PATH = OVERSEER_DATA_DIR / "l3_mbo.json"
OVERSEER_SIGNALS_PATH = OVERSEER_DATA_DIR / "signals.json"