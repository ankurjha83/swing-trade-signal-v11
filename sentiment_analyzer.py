"""
sentiment_analyzer.py

Lightweight news sentiment module.

No external API key required.
Uses simple keyword scoring on latest yfinance news.
"""

from __future__ import annotations


POSITIVE_KEYWORDS = {
    "beat", "beats", "strong", "surge", "surges", "rally", "rallies",
    "upgrade", "upgraded", "outperform", "buy rating", "raises target",
    "record", "growth", "profit", "profits", "expands", "partnership",
    "ai demand", "cloud growth", "margin expansion", "free cash flow",
}

NEGATIVE_KEYWORDS = {
    "miss", "misses", "weak", "falls", "slumps", "downgrade", "downgraded",
    "underperform", "sell rating", "cuts target", "lawsuit", "probe",
    "investigation", "antitrust", "layoffs", "slowdown", "guidance cut",
    "margin pressure", "recession", "tariff", "ban", "export restriction",
    "accounting", "fraud", "sec", "regulatory pressure",
}


def score_text(text: str) -> float:
    if not text:
        return 0.0

    lower = text.lower()
    positive_hits = sum(1 for word in POSITIVE_KEYWORDS if word in lower)
    negative_hits = sum(1 for word in NEGATIVE_KEYWORDS if word in lower)
    total_hits = positive_hits + negative_hits

    if total_hits == 0:
        return 0.0

    raw = (positive_hits - negative_hits) / total_hits
    return max(-1.0, min(1.0, raw))


def analyze_news_sentiment(news_items: list[dict]) -> dict:
    if not news_items:
        return {
            "score": 0.0,
            "label": "neutral",
            "headline_count": 0,
            "positive_count": 0,
            "negative_count": 0,
            "top_headlines": [],
        }

    scores = []
    top_headlines = []

    for item in news_items:
        title = item.get("title", "") or ""
        summary = item.get("summary", "") or ""
        text = f"{title}. {summary}"
        item_score = score_text(text)
        scores.append(item_score)

        if title:
            top_headlines.append(
                {
                    "title": title,
                    "publisher": item.get("publisher"),
                    "link": item.get("link"),
                    "score": round(item_score, 3),
                }
            )

    avg_score = sum(scores) / len(scores) if scores else 0.0

    if avg_score >= 0.25:
        label = "positive"
    elif avg_score <= -0.25:
        label = "negative"
    else:
        label = "neutral"

    return {
        "score": round(avg_score, 4),
        "label": label,
        "headline_count": len(news_items),
        "positive_count": sum(1 for s in scores if s > 0),
        "negative_count": sum(1 for s in scores if s < 0),
        "top_headlines": top_headlines[:5],
    }
