"""
long_term_fetcher.py

Fetches:
- 1Y daily OHLCV
- long-term technical indicators
- yfinance fundamental snapshot
- latest yfinance news
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd
import yfinance as yf


FUNDAMENTAL_FIELDS = {
    "market_cap": "marketCap",
    "enterprise_value": "enterpriseValue",
    "revenue_growth": "revenueGrowth",
    "earnings_growth": "earningsGrowth",
    "gross_margins": "grossMargins",
    "operating_margins": "operatingMargins",
    "profit_margins": "profitMargins",
    "free_cashflow": "freeCashflow",
    "operating_cashflow": "operatingCashflow",
    "total_cash": "totalCash",
    "total_debt": "totalDebt",
    "debt_to_equity": "debtToEquity",
    "forward_pe": "forwardPE",
    "trailing_pe": "trailingPE",
    "peg_ratio": "pegRatio",
    "price_to_sales": "priceToSalesTrailing12Months",
    "price_to_book": "priceToBook",
    "return_on_equity": "returnOnEquity",
    "return_on_assets": "returnOnAssets",
    "recommendation_mean": "recommendationMean",
    "number_of_analyst_opinions": "numberOfAnalystOpinions",
    "current_price": "currentPrice",
    "regular_market_price": "regularMarketPrice",
    "fifty_two_week_high": "fiftyTwoWeekHigh",
    "fifty_two_week_low": "fiftyTwoWeekLow",
    "target_mean_price": "targetMeanPrice",
    "target_median_price": "targetMedianPrice",
}


def _safe_float(value: Any) -> Any:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return value


def _normalize_yfinance_df(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return df

    df = df.copy()

    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)

    return df.dropna()


@lru_cache(maxsize=512)
def fetch_fundamentals(ticker: str) -> dict:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        fundamentals = {
            clean_name: _safe_float(info.get(yf_name))
            for clean_name, yf_name in FUNDAMENTAL_FIELDS.items()
        }

        fundamentals.update(
            {
                "short_name": info.get("shortName"),
                "long_name": info.get("longName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "currency": info.get("currency"),
                "exchange": info.get("exchange"),
            }
        )

        return fundamentals

    except Exception as exc:
        return {"error": f"fundamentals_failed: {exc}"}


@lru_cache(maxsize=512)
def fetch_daily_history(ticker: str, period: str = "1y") -> pd.DataFrame | None:
    try:
        df = yf.download(
            ticker,
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=True,
            threads=False,
        )

        return _normalize_yfinance_df(df)

    except Exception:
        return None


def enrich_daily_indicators(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return df

    df = df.copy()

    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["SMA50"] = df["Close"].rolling(window=50).mean()
    df["SMA100"] = df["Close"].rolling(window=100).mean()
    df["SMA200"] = df["Close"].rolling(window=200).mean()

    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()

    df["MACD"] = ema12 - ema26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()

    rs = gain / loss.replace(0, pd.NA)
    df["RSI"] = 100 - (100 / (1 + rs))

    df["VOLUME_AVG_20"] = df["Volume"].rolling(window=20).mean()
    df["VOLUME_RATIO"] = df["Volume"] / df["VOLUME_AVG_20"]

    high_52w = df["Close"].rolling(window=252, min_periods=60).max()
    high_6m = df["Close"].rolling(window=126, min_periods=60).max()
    low_3m = df["Close"].rolling(window=63, min_periods=30).min()

    df["DRAWDOWN_52W"] = (high_52w - df["Close"]) / high_52w
    df["DRAWDOWN_6M"] = (high_6m - df["Close"]) / high_6m
    df["REBOUND_FROM_3M_LOW"] = (df["Close"] - low_3m) / low_3m

    return df.dropna()


@lru_cache(maxsize=512)
def fetch_latest_news(ticker: str, limit: int = 5) -> list[dict]:
    try:
        stock = yf.Ticker(ticker)
        raw_news = stock.news or []
        cleaned = []

        for item in raw_news[:limit]:
            content = item.get("content", item) if isinstance(item, dict) else {}

            title = content.get("title") or item.get("title") or ""
            publisher = item.get("publisher")

            if isinstance(content.get("provider"), dict):
                publisher = content.get("provider", {}).get("displayName") or publisher

            link = item.get("link")

            if isinstance(content.get("canonicalUrl"), dict):
                link = content.get("canonicalUrl", {}).get("url") or link

            summary = content.get("summary") or item.get("summary") or ""
            published_at = (
                content.get("pubDate")
                or item.get("providerPublishTime")
                or item.get("published")
            )

            cleaned.append(
                {
                    "title": title,
                    "summary": summary,
                    "publisher": publisher,
                    "link": link,
                    "published_at": published_at,
                }
            )

        return cleaned

    except Exception:
        return []


def fetch_long_term_data(ticker: str) -> dict:
    fundamentals = fetch_fundamentals(ticker)
    daily_df = enrich_daily_indicators(fetch_daily_history(ticker))
    news = fetch_latest_news(ticker)

    error = None

    if daily_df is None or daily_df.empty:
        error = "no_daily_price_data"

    return {
        "ticker": ticker,
        "fundamentals": fundamentals,
        "daily_df": daily_df,
        "news": news,
        "error": error,
    }
