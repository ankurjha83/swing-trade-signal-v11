"""
config/settings.py

Long-term accumulation scanner configuration.

This intentionally replaces the old swing-scanner settings because the scanner
is now focused on quality + valuation + discount + sentiment.
"""

from __future__ import annotations

import logging
import requests


VERSION = "2.0-long-term"

WATCHLIST_GOOGLE_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1yxmvO8ohAxkVspojw8PZoc3PwV5OEcEGu7AMiTL-Njc/export?format=csv&gid=0"
)

WATCHLIST_FALLBACK = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "COST", "NFLX",
    "ADBE", "CRM", "NOW", "INTU", "AMD", "QCOM", "MU", "TSM", "ASML",
    "CRWD", "PANW", "ZS", "DDOG", "SNOW", "NET", "SHOP", "PLTR",
    "TSLA", "UBER", "ABNB", "MELI", "COIN", "RKLB", "ASTS", "IONQ", "QBTS",
]

MIN_ALERT_SCORE = 70
SEND_INDIVIDUAL_ALERTS = True
SEND_SUMMARY_ALERT = True

LOG_DIR = "logs/long_term"

TELEGRAM_BOT_TOKEN_ENV = "V11_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "V11_TELEGRAM_CHAT_ID"


def load_watchlist() -> list[str]:
    """
    Load tickers from the Google Sheet if available.
    Falls back to WATCHLIST_FALLBACK.
    """
    logger = logging.getLogger(__name__)

    skip_headers = {"TICKER", "SYMBOL", "NAME", "STOCK"}
    tickers = []

    try:
        response = requests.get(WATCHLIST_GOOGLE_SHEET_URL, timeout=10)
        response.raise_for_status()

        for line in response.text.strip().splitlines():
            cols = line.split(",")
            if not cols:
                continue

            ticker = cols[0].strip().strip('"').upper()

            if (
                ticker
                and ticker not in skip_headers
                and ticker.replace(".", "").replace("-", "").isalpha()
                and len(ticker) <= 8
            ):
                tickers.append(ticker)

        if tickers:
            logger.info("Loaded %s tickers from Google Sheet", len(tickers))
            return sorted(set(tickers))

        raise ValueError("Google Sheet did not contain valid tickers")

    except Exception as exc:
        logger.warning("Watchlist fetch failed (%s). Using fallback.", exc)
        return WATCHLIST_FALLBACK


WATCHLIST = load_watchlist()
