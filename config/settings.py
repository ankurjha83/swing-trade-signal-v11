"""
config/settings.py — Swing Scanner v1.1 Configuration
======================================================
Version 1.1 — Do NOT change VERSION without updating CHANGELOG.
"""

VERSION = "1.1"

CHANGELOG = {
    "1.1": [
        "SPY hard gate replaces soft warning",
        "Volume tier system: confirmed vs watchlist alerts",
        "Negative sentiment hard block on confirmed alerts",
        "Geopolitical risk -8pt score penalty",
        "Manual ticker veto via vetoed_tickers.json",
        "RSI upper ceiling raised 65→70",
        "Sector ETF overlay gate (CIBR, SOXX, WCLD, UFO)",
    ]
}

# ---------------------------------------------------------------------------
# Watchlist (identical to v1.0 — do not change without parallel v1.0 update)
# ---------------------------------------------------------------------------
WATCHLIST_GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1yxmvO8ohAxkVspojw8PZoc3PwV5OEcEGu7AMiTL-Njc/export?format=csv&gid=0"

WATCHLIST_FALLBACK = [
    "CRWD", "PLTR", "NET", "NVDA", "AMD", "MU",
    "QCOM", "TSM", "COHR", "SHOP", "RKLB",
    "MSFT", "META", "GOOGL", "AMZN", "NFLX",
]

def load_watchlist():
    import requests, logging
    logger = logging.getLogger(__name__)
    SKIP_HEADERS = {"TICKER", "SYMBOL", "NAME", "STOCK"}
    SKIP_SECTORS = {"—", "-", "", "n/a"}
    try:
        resp = requests.get(WATCHLIST_GOOGLE_SHEET_URL, timeout=10)
        resp.raise_for_status()
        lines = resp.text.strip().splitlines()
        tickers = []
        sheet_sector_map = {}
        for line in lines:
            cols = line.split(",")
            ticker = cols[0].strip().strip('"').upper()
            sector = cols[1].strip().strip('"').lower() if len(cols) > 1 else ""
            if ticker and ticker.isalpha() and ticker not in SKIP_HEADERS and len(ticker) <= 5:
                tickers.append(ticker)
                if sector and sector not in SKIP_SECTORS:
                    sheet_sector_map[ticker] = sector
        if tickers:
            logger.info(f"Watchlist loaded: {len(tickers)} tickers")
            return tickers, sheet_sector_map
        raise ValueError("Empty ticker list")
    except Exception as exc:
        logger.warning(f"Google Sheet fetch failed ({exc}) — using fallback")
        return WATCHLIST_FALLBACK, {}

WATCHLIST, SHEET_SECTOR_MAP = load_watchlist()

# ---------------------------------------------------------------------------
# RSI thresholds  (CHANGE 6: upper ceiling raised 65 → 70)
# ---------------------------------------------------------------------------
RSI_MOMENTUM_LOWER = 50
RSI_MOMENTUM_UPPER = 70          # was 65 in v1.0
RSI_OVERBOUGHT = 71              # > this value = fail
RSI_OVERSOLD_LOWER = 30
RSI_OVERSOLD_UPPER = 45

# ---------------------------------------------------------------------------
# Volume thresholds  (CHANGE 2: tier system)
# ---------------------------------------------------------------------------
VOLUME_CONFIRMED_THRESHOLD = 1.3        # vol ratio to qualify for confirmed
VOLUME_DEAD_THRESHOLD = 0.5             # vol ratio below which always suppress

# Alert tier score thresholds
TIER_CONFIRMED_MIN_SCORE = 75           # confirmed alert floor
TIER_MEDIUM_MIN_SCORE = 60              # medium — log only, no alert
TIER_WATCHLIST_MIN_SCORE = 80           # unconfirmed-high watchlist alert

# ---------------------------------------------------------------------------
# Sentiment  (CHANGE 3)
# ---------------------------------------------------------------------------
SENTIMENT_BLOCK_THRESHOLD = 0           # < 0 → blocked from confirmed

# ---------------------------------------------------------------------------
# Geopolitical risk penalty  (CHANGE 4)
# ---------------------------------------------------------------------------
GEO_RISK_PENALTY = 8                    # points subtracted if geo risk flagged
GEO_RISK_MAX_SCORE = 100 - GEO_RISK_PENALTY  # 92

# ---------------------------------------------------------------------------
# SPY gate  (CHANGE 1)
# ---------------------------------------------------------------------------
SPY_EMA_PERIOD = 20
SPY_LOOKBACK_DAYS = 30
SPY_TOP_TICKERS_IN_GATE_MSG = 3

# ---------------------------------------------------------------------------
# Sector ETF overlay  (CHANGE 7)
# ---------------------------------------------------------------------------
SECTOR_ETF_MAP = {
    "cybersecurity": {
        "etf": "CIBR",
        "tickers": ["CRWD", "PLTR", "NET", "PANW", "ZS", "OKTA"],
        "ema_period": 10,
    },
    "semiconductors": {
        "etf": "SOXX",
        "tickers": ["NVDA", "AMD", "MU", "QCOM", "TSM", "COHR"],
        "ema_period": 10,
    },
    "cloud": {
        "etf": "WCLD",
        "tickers": ["SHOP", "NET", "CRWD", "SNOW", "DDOG"],
        "ema_period": 10,
    },
    "space": {
        "etf": "UFO",
        "tickers": ["RKLB", "ASTS", "MNTS"],
        "ema_period": 10,
    },
}

# ---------------------------------------------------------------------------
# Deduplication  (identical 5-day cooldown from v1.0)
# ---------------------------------------------------------------------------
DEDUP_COOLDOWN_DAYS = 5

# ---------------------------------------------------------------------------
# Log paths
# ---------------------------------------------------------------------------
LOG_DIR = "logs/v1.1"                   # v1.1 logs go here, NOT logs/
SENT_SIGNALS_FILE = "sent_signals.json"
VETOED_TICKERS_FILE = "config/vetoed_tickers.json"

# ---------------------------------------------------------------------------
# Scoring weights (identical to v1.0 — do not change)
# ---------------------------------------------------------------------------
SCORE_WEIGHTS = {
    "rsi": 15,
    "ema_alignment": 20,
    "volume": 12,
    "breakout": 15,
    "macd": 10,
    "relative_strength": 8,
    "atr_volatility": 5,
    "sentiment": 8,
    "key_levels": 5,
    "geo_risk_raw": 2,  # raw score component (penalty applied separately)
}
# Sum = 100

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
SECTOR_ETF_LOOKBACK_DAYS = 15
DATA_FETCH_RETRIES = 3
DATA_FETCH_BATCH_SIZE = 5
