from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from long_term_scorer import (
    LongTermScore,
    classify_score,
    score_long_term_candidate,
)
from sentiment_analyzer import analyze_news_sentiment, score_text


def make_daily_df() -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=80, freq="B")
    close = pd.Series([100 + i * 0.4 for i in range(80)], index=index)

    return pd.DataFrame(
        {
            "Close": close,
            "Volume": 1_000_000,
            "EMA20": close - 1,
            "SMA200": close - 10,
            "MACD": pd.Series([0.1 + i * 0.01 for i in range(80)], index=index),
            "RSI": 52,
            "DRAWDOWN_52W": 0.20,
            "DRAWDOWN_6M": 0.12,
            "REBOUND_FROM_3M_LOW": 0.08,
        },
        index=index,
    )


def make_fundamentals() -> dict:
    return {
        "revenue_growth": 0.28,
        "free_cashflow": 12_000_000_000,
        "gross_margins": 0.72,
        "return_on_equity": 0.27,
        "market_cap": 1_500_000_000_000,
        "peg_ratio": 0.9,
        "forward_pe": 22,
        "price_to_sales": 6,
    }


def test_score_long_term_candidate_produces_serializable_result():
    result = score_long_term_candidate(
        "TEST",
        {
            "daily_df": make_daily_df(),
            "fundamentals": make_fundamentals(),
            "news": [],
        },
        {"score": 0.3, "label": "positive", "top_headlines": []},
    )

    assert isinstance(result, LongTermScore)
    assert result.ticker == "TEST"
    assert result.total_score == 91
    assert result.quality_score == 50
    assert result.valuation_score == 24
    assert result.discount_score == 9
    assert result.technical_score == 5
    assert result.rating == "A"

    payload = asdict(result)
    assert payload["factors"]["quality"]["revenue_growth"]["points"] == 15


def test_score_long_term_candidate_blocks_severe_negative_news():
    result = score_long_term_candidate(
        "RISK",
        {
            "daily_df": make_daily_df(),
            "fundamentals": make_fundamentals(),
            "news": [],
        },
        {"score": -0.75, "label": "negative", "top_headlines": []},
    )

    assert result is not None
    assert result.rating == "Blocked"
    assert result.risk == "High"
    assert result.total_score == 83


def test_classify_score_blocks_structural_breaks_before_accumulation_rating():
    rating, action, risk = classify_score(
        total=90,
        sentiment_score=0.0,
        drawdown_52w=0.65,
    )

    assert rating == "Blocked"
    assert "Severe drawdown" in action
    assert risk == "High"


def test_sentiment_analyzer_is_conservative_and_keyword_based():
    assert score_text("Company beats estimates on strong cloud growth") == 1.0
    assert score_text("Company faces lawsuit and regulatory pressure") == -1.0

    sentiment = analyze_news_sentiment(
        [
            {"title": "Company beats estimates", "summary": "Strong profit growth"},
            {"title": "Analyst cuts target", "summary": "Margin pressure"},
        ]
    )

    assert sentiment["headline_count"] == 2
    assert sentiment["positive_count"] == 1
    assert sentiment["negative_count"] == 1
    assert sentiment["label"] == "neutral"
