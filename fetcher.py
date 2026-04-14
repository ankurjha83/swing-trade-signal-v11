"""
fetcher.py — Data Fetching Layer (IDENTICAL to v1.0)
=====================================================
Uses yfinance with batching and retry logic.
Do NOT modify this file as part of v1.1 changes — data layer is frozen.
"""

import time
import logging
from typing import Optional

import yfinance as yf
import pandas as pd

from config.settings import DATA_FETCH_RETRIES, DATA_FETCH_BATCH_SIZE

logger = logging.getLogger(__name__)


def _fetch_with_retry(tickers: list[str], period: str, interval: str = "1d") -> dict:
    """
    Fetch OHLCV data for a list of tickers with retry logic.
    Returns a dict: {ticker: DataFrame or None}
    """
    results = {}
    for attempt in range(1, DATA_FETCH_RETRIES + 1):
        try:
            raw = yf.download(
                tickers=tickers,
                period=period,
                interval=interval,
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if len(tickers) == 1:
                ticker = tickers[0]
                if not raw.empty:
                    if isinstance(raw.columns, pd.MultiIndex):
                        raw.columns = raw.columns.droplevel(1)
                    results[ticker] = raw
                else:
                    results[ticker] = None
            else:
                for ticker in tickers:
                    try:
                        df = raw[ticker].dropna()
                        results[ticker] = df if not df.empty else None
                    except (KeyError, TypeError):
                        results[ticker] = None
            return results
        except Exception as exc:
            logger.warning(f"Attempt {attempt}/{DATA_FETCH_RETRIES} failed for {tickers}: {exc}")
            if attempt < DATA_FETCH_RETRIES:
                time.sleep(2 ** attempt)  # exponential backoff
    # All retries exhausted — return Nones
    return {t: None for t in tickers}


def fetch_ohlcv(ticker: str, period: str = "60d", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Fetch daily OHLCV for a single ticker."""
    result = _fetch_with_retry([ticker], period=period, interval=interval)
    return result.get(ticker)


def fetch_ohlcv_batch(tickers: list[str], period: str = "60d") -> dict:
    """
    Fetch daily OHLCV for a list of tickers in batches.
    Returns {ticker: DataFrame or None}
    """
    all_results = {}
    for i in range(0, len(tickers), DATA_FETCH_BATCH_SIZE):
        batch = tickers[i : i + DATA_FETCH_BATCH_SIZE]
        logger.debug(f"Fetching batch {i // DATA_FETCH_BATCH_SIZE + 1}: {batch}")
        batch_results = _fetch_with_retry(batch, period=period)
        all_results.update(batch_results)
        if i + DATA_FETCH_BATCH_SIZE < len(tickers):
            time.sleep(0.5)  # polite rate limiting
    return all_results


def fetch_spy_daily(lookback_days: int = 30) -> Optional[pd.DataFrame]:
    """Fetch SPY daily OHLCV for SPY gate computation."""
    period = f"{lookback_days + 10}d"  # buffer for weekends/holidays
    df = fetch_ohlcv("SPY", period=period)
    if df is not None:
        return df.tail(lookback_days)
    return None


def fetch_sector_etf(etf: str, lookback_days: int = 15) -> Optional[pd.DataFrame]:
    """Fetch sector ETF daily close for sector gate computation."""
    period = f"{lookback_days + 10}d"
    df = fetch_ohlcv(etf, period=period)
    if df is not None:
        return df.tail(lookback_days)
    return None


def get_latest_close(df: Optional[pd.DataFrame]) -> Optional[float]:
    """Safely extract the most recent closing price from a DataFrame."""
    if df is None or df.empty:
        return None
    try:
        return float(df["Close"].iloc[-1])
    except (KeyError, IndexError, TypeError):
        return None


def get_latest_volume(df: Optional[pd.DataFrame]) -> Optional[float]:
    """Safely extract the most recent volume."""
    if df is None or df.empty:
        return None
    try:
        return float(df["Volume"].iloc[-1])
    except (KeyError, IndexError, TypeError):
        return None
