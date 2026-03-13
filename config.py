import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
BASE_URL = "https://api.the-odds-api.com/v4"
BOOKMAKERS = "pmu_fr,winamax_fr,unibet_fr,betclic_fr,parionssport_fr"
REGIONS = "eu"
BANKROLL = 1000.0
MIN_EDGE = 0.08
MAX_BET_FRACTION = 0.05
KELLY_FRACTION = 0.5
POLL_INTERVAL_SECONDS = 300

# Database
DB_PATH = os.getenv("DB_PATH", "pmu_bot.db")

# Odds movement detection
MOVEMENT_WINDOW_MINUTES = 30
MOVEMENT_THRESHOLD = 0.15  # 15% drop = smart money signal

# Web interface
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "5000"))
