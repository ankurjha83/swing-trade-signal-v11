"""
screener.py — Pre-Run Gate Checks (v1.1)
==========================================
Handles two market-level gates BEFORE any per-ticker scoring:

  1. SPY Hard Gate (CHANGE 1)
     - Fetches SPY daily OHLCV (30 days)
     - Computes SPY 20-day EMA
     - Returns gate_open=True/False

  2. Sector ETF Overlay Gate (CHANGE 7)
     - For each sector in SECTOR_ETF_MAP, fetches last 15 days of ETF close
     - Computes 10-day EMA per ETF
     - Returns {sector: True/False} indicating whether sector is in caution mode
     - Sectors in caution → their tickers get DOWNGRADED from CONFIRMED → WATCHLIST only
     - (SPY gate is harder: if SPY is below, everything is blocked regardless)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from config.settings import (
    SECTOR_ETF_MAP,
    SECTOR_ETF_LOOKBACK_DAYS,
    SPY_EMA_PERIOD,
    SPY_LOOKBACK_DAYS,
)
from fetcher import fetch_sector_etf, fetch_spy_daily

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SPY gate
# ---------------------------------------------------------------------------

@dataclass
class SpyGateResult:
    gate_open: bool          # True = market healthy, proceed with alerts
    spy_close: float = 0.0
    spy_ema: float = 0.0
    pct_vs_ema: float = 0.0  # (close - ema) / ema * 100


def check_spy_gate() -> SpyGateResult:
    """
    Fetches SPY data, computes 20-day EMA, returns SpyGateResult.

    CHANGE 1: This is a HARD gate. If gate_open=False, main.py must NOT
    send any CONFIRMED or WATCHLIST alerts. Only a single summary message
    is sent listing the top 3 tickers by score.
    """
    df = fetch_spy_daily(lookback_days=SPY_LOOKBACK_DAYS)
    if df is None or df.empty:
        logger.warning("SPY data unavailable — defaulting gate to OPEN (fail-safe)")
        return SpyGateResult(gate_open=True)
    
    if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.droplevel(1)
    close = df["Close"]
    ema = close.ewm(span=SPY_EMA_PERIOD, adjust=False).mean()

    latest_close = float(close.iloc[-1])
    latest_ema = float(ema.iloc[-1])
    pct = (latest_close - latest_ema) / latest_ema * 100

    gate_open = latest_close >= latest_ema

    result = SpyGateResult(
        gate_open=gate_open,
        spy_close=latest_close,
        spy_ema=latest_ema,
        pct_vs_ema=pct,
    )

    if gate_open:
        logger.info(
            f"SPY Gate OPEN: close ${latest_close:.2f} >= "
            f"{SPY_EMA_PERIOD}EMA ${latest_ema:.2f} (+{pct:.2f}%)"
        )
    else:
        logger.warning(
            f"SPY Gate CLOSED: close ${latest_close:.2f} < "
            f"{SPY_EMA_PERIOD}EMA ${latest_ema:.2f} ({pct:.2f}%)"
        )

    return result


# ---------------------------------------------------------------------------
# Sector ETF gate
# ---------------------------------------------------------------------------

@dataclass
class SectorGateStatus:
    etf: str
    ema_period: int
    etf_close: float
    etf_ema: float
    in_caution: bool    # True = sector ETF below 10 EMA → sector headwind


def check_sector_gates() -> dict[str, SectorGateStatus]:
    """
    For each sector in SECTOR_ETF_MAP, fetch ETF data and determine
    whether the sector is in caution mode (ETF close < 10 EMA).

    CHANGE 7: Sectors in caution mode mean their tickers CANNOT qualify
    for CONFIRMED alerts — they can still appear in WATCHLIST alerts.

    Returns {sector_name: SectorGateStatus}
    """
    results: dict[str, SectorGateStatus] = {}

    for sector, cfg in SECTOR_ETF_MAP.items():
        etf = cfg["etf"]
        ema_period = cfg["ema_period"]
        df = fetch_sector_etf(etf, lookback_days=SECTOR_ETF_LOOKBACK_DAYS)

        if df is None or df.empty:
            logger.warning(
                f"Sector ETF {etf} ({sector}) data unavailable — "
                f"defaulting sector to healthy (no caution)"
            )
            results[sector] = SectorGateStatus(
                etf=etf,
                ema_period=ema_period,
                etf_close=0.0,
                etf_ema=0.0,
                in_caution=False,
            )
            continue

        close = df["Close"]
        ema = close.ewm(span=ema_period, adjust=False).mean()
        latest_close = float(close.iloc[-1])
        latest_ema = float(ema.iloc[-1])
        in_caution = latest_close < latest_ema

        status = SectorGateStatus(
            etf=etf,
            ema_period=ema_period,
            etf_close=latest_close,
            etf_ema=latest_ema,
            in_caution=in_caution,
        )

        if in_caution:
            logger.warning(
                f"Sector CAUTION — {sector} ({etf}): "
                f"close ${latest_close:.2f} < {ema_period}EMA ${latest_ema:.2f}"
            )
        else:
            logger.info(
                f"Sector HEALTHY — {sector} ({etf}): "
                f"close ${latest_close:.2f} >= {ema_period}EMA ${latest_ema:.2f}"
            )

        results[sector] = status

    return results


def get_ticker_sector(ticker: str) -> str | None:
    """Return the sector name for a ticker, or None if not mapped."""
    for sector, cfg in SECTOR_ETF_MAP.items():
        if ticker in cfg["tickers"]:
            return sector
    return None


def is_ticker_sector_in_caution(
    ticker: str,
    sector_gates: dict[str, SectorGateStatus],
) -> tuple[bool, str | None]:
    """
    Returns (in_caution, etf_symbol).
    If ticker has no sector mapping, returns (False, None) — no caution.
    """
    sector = get_ticker_sector(ticker)
    if sector is None:
        return False, None
    status = sector_gates.get(sector)
    if status is None:
        return False, None
    return status.in_caution, status.etf
