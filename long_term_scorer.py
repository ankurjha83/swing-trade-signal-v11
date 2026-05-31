"""
long_term_scorer.py

Long-term accumulation score.

Scoring:
    Quality      50
    Valuation    30
    Discount     15
    Technical     5
    ----------------
    Total       100
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class LongTermScore:
    ticker: str
    price: float
    total_score: int
    quality_score: int
    valuation_score: int
    discount_score: int
    technical_score: int
    sentiment_score: float
    sentiment_label: str
    rating: str
    action: str
    risk: str
    factors: dict = field(default_factory=dict)
    fundamentals: dict = field(default_factory=dict)
    headlines: list[dict] = field(default_factory=list)


def _num(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def score_quality(f: dict) -> tuple[int, dict]:
    score = 0
    notes = {}

    revenue_growth = _num(f.get("revenue_growth"))
    free_cashflow = _num(f.get("free_cashflow"))
    gross_margins = _num(f.get("gross_margins"))
    roe = _num(f.get("return_on_equity"))
    market_cap = _num(f.get("market_cap"))

    if revenue_growth is not None:
        if revenue_growth >= 0.25:
            pts = 15
        elif revenue_growth >= 0.18:
            pts = 12
        elif revenue_growth >= 0.10:
            pts = 9
        elif revenue_growth >= 0.05:
            pts = 5
        else:
            pts = 0
        score += pts
        notes["revenue_growth"] = {"value": revenue_growth, "points": pts, "max": 15}
    else:
        notes["revenue_growth"] = {"value": None, "points": 0, "max": 15}

    if free_cashflow is not None:
        if free_cashflow >= 10_000_000_000:
            pts = 10
        elif free_cashflow >= 3_000_000_000:
            pts = 8
        elif free_cashflow > 0:
            pts = 5
        else:
            pts = 0
        score += pts
        notes["free_cashflow"] = {"value": free_cashflow, "points": pts, "max": 10}
    else:
        notes["free_cashflow"] = {"value": None, "points": 0, "max": 10}

    if gross_margins is not None:
        if gross_margins >= 0.70:
            pts = 10
        elif gross_margins >= 0.55:
            pts = 8
        elif gross_margins >= 0.40:
            pts = 5
        elif gross_margins >= 0.25:
            pts = 2
        else:
            pts = 0
        score += pts
        notes["gross_margins"] = {"value": gross_margins, "points": pts, "max": 10}
    else:
        notes["gross_margins"] = {"value": None, "points": 0, "max": 10}

    if roe is not None:
        if roe >= 0.25:
            pts = 5
        elif roe >= 0.15:
            pts = 4
        elif roe >= 0.08:
            pts = 2
        else:
            pts = 0
        score += pts
        notes["return_on_equity"] = {"value": roe, "points": pts, "max": 5}
    else:
        notes["return_on_equity"] = {"value": None, "points": 0, "max": 5}

    if market_cap is not None:
        if market_cap >= 1_000_000_000_000:
            pts = 10
        elif market_cap >= 200_000_000_000:
            pts = 8
        elif market_cap >= 50_000_000_000:
            pts = 6
        elif market_cap >= 10_000_000_000:
            pts = 3
        else:
            pts = 0
        score += pts
        notes["market_cap"] = {"value": market_cap, "points": pts, "max": 10}
    else:
        notes["market_cap"] = {"value": None, "points": 0, "max": 10}

    return min(score, 50), notes


def score_valuation(f: dict) -> tuple[int, dict]:
    score = 0
    notes = {}

    peg = _num(f.get("peg_ratio"))
    forward_pe = _num(f.get("forward_pe"))
    price_to_sales = _num(f.get("price_to_sales"))
    revenue_growth = _num(f.get("revenue_growth"))

    if peg is not None and peg > 0:
        if peg <= 0.8:
            pts = 15
        elif peg <= 1.2:
            pts = 12
        elif peg <= 1.5:
            pts = 9
        elif peg <= 2.0:
            pts = 5
        else:
            pts = 0
        score += pts
        notes["peg_ratio"] = {"value": peg, "points": pts, "max": 15}
    else:
        notes["peg_ratio"] = {"value": peg, "points": 0, "max": 15}

    if forward_pe is not None and forward_pe > 0:
        if forward_pe <= 18:
            pts = 10
        elif forward_pe <= 25:
            pts = 8
        elif forward_pe <= 35:
            pts = 5
        elif forward_pe <= 45:
            pts = 2
        else:
            pts = 0
        score += pts
        notes["forward_pe"] = {"value": forward_pe, "points": pts, "max": 10}
    else:
        notes["forward_pe"] = {"value": forward_pe, "points": 0, "max": 10}

    if price_to_sales is not None and price_to_sales > 0:
        if price_to_sales <= 5:
            pts = 5
        elif price_to_sales <= 8 and revenue_growth and revenue_growth >= 0.10:
            pts = 4
        elif price_to_sales <= 12 and revenue_growth and revenue_growth >= 0.18:
            pts = 3
        elif price_to_sales <= 15 and revenue_growth and revenue_growth >= 0.25:
            pts = 2
        else:
            pts = 0
        score += pts
        notes["price_to_sales"] = {"value": price_to_sales, "points": pts, "max": 5}
    else:
        notes["price_to_sales"] = {"value": price_to_sales, "points": 0, "max": 5}

    return min(score, 30), notes


def score_discount(latest: pd.Series) -> tuple[int, dict]:
    drawdown_52w = _num(latest.get("DRAWDOWN_52W"), 0.0)
    drawdown_6m = _num(latest.get("DRAWDOWN_6M"), 0.0)

    if drawdown_52w >= 0.35:
        pts = 15
    elif drawdown_52w >= 0.25:
        pts = 12
    elif drawdown_52w >= 0.18:
        pts = 9
    elif drawdown_52w >= 0.12:
        pts = 5
    elif drawdown_6m >= 0.10:
        pts = 3
    else:
        pts = 0

    return min(pts, 15), {
        "drawdown_52w": {"value": drawdown_52w, "points": pts, "max": 15},
        "drawdown_6m": {"value": drawdown_6m, "points": 0, "max": 0},
    }


def score_technical(latest: pd.Series, previous: pd.Series) -> tuple[int, dict]:
    score = 0

    rsi = _num(latest.get("RSI"))
    macd = _num(latest.get("MACD"))
    prev_macd = _num(previous.get("MACD"))
    close = _num(latest.get("Close"))
    ema20 = _num(latest.get("EMA20"))
    sma200 = _num(latest.get("SMA200"))
    rebound = _num(latest.get("REBOUND_FROM_3M_LOW"), 0.0)

    if rsi is not None and 35 <= rsi <= 60:
        score += 1

    if macd is not None and prev_macd is not None and macd >= prev_macd:
        score += 1

    if close is not None and ema20 is not None and close >= ema20:
        score += 1

    if close is not None and sma200 is not None and close >= sma200 * 0.80:
        score += 1

    if rebound >= 0.05:
        score += 1

    return min(score, 5), {
        "technical": {
            "rsi": rsi,
            "macd_stabilizing": (
                macd is not None
                and prev_macd is not None
                and macd >= prev_macd
            ),
            "above_ema20": (
                close is not None
                and ema20 is not None
                and close >= ema20
            ),
            "not_broken_vs_sma200": (
                close is not None
                and sma200 is not None
                and close >= sma200 * 0.80
            ),
            "rebound_from_3m_low": rebound,
            "points": score,
            "max": 5,
        }
    }


def classify_score(total: int, sentiment_score: float, drawdown_52w: float) -> tuple[str, str, str]:
    if sentiment_score <= -0.50:
        return "Blocked", "Negative news flow — manual review required", "High"

    if drawdown_52w >= 0.60:
        return "Blocked", "Severe drawdown — possible structural break", "High"

    if total >= 85:
        return "A", "Aggressive accumulation candidate", "Medium"

    if total >= 75:
        return "B", "Strong accumulation candidate", "Medium"

    if total >= 65:
        return "C", "Gradual accumulation candidate", "Medium-High"

    if total >= 55:
        return "Watch", "Watchlist only", "Medium-High"

    return "Avoid", "No action", "High"


def score_long_term_candidate(ticker: str, long_term_data: dict, sentiment: dict) -> LongTermScore | None:
    daily_df = long_term_data.get("daily_df")
    fundamentals = long_term_data.get("fundamentals", {})

    if daily_df is None or daily_df.empty or len(daily_df) < 30:
        return None

    latest = daily_df.iloc[-1]
    previous = daily_df.iloc[-2]

    price = float(latest["Close"])
    drawdown_52w = _num(latest.get("DRAWDOWN_52W"), 0.0)

    quality_score, quality_notes = score_quality(fundamentals)
    valuation_score, valuation_notes = score_valuation(fundamentals)
    discount_score, discount_notes = score_discount(latest)
    technical_score, technical_notes = score_technical(latest, previous)

    total_score = quality_score + valuation_score + discount_score + technical_score

    sentiment_score = float(sentiment.get("score", 0.0))
    sentiment_label = sentiment.get("label", "neutral")

    if sentiment_score <= -0.25:
        total_score = max(0, total_score - 5)
    elif sentiment_score >= 0.25:
        total_score = min(100, total_score + 3)

    rating, action, risk = classify_score(total_score, sentiment_score, drawdown_52w)

    return LongTermScore(
        ticker=ticker,
        price=round(price, 2),
        total_score=int(total_score),
        quality_score=int(quality_score),
        valuation_score=int(valuation_score),
        discount_score=int(discount_score),
        technical_score=int(technical_score),
        sentiment_score=sentiment_score,
        sentiment_label=sentiment_label,
        rating=rating,
        action=action,
        risk=risk,
        factors={
            "quality": quality_notes,
            "valuation": valuation_notes,
            "discount": discount_notes,
            "technical": technical_notes,
        },
        fundamentals=fundamentals,
        headlines=sentiment.get("top_headlines", []),
    )
