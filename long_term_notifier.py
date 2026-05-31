"""
long_term_notifier.py

Telegram alert formatting for long-term accumulation scanner.
"""

from __future__ import annotations

import os
import requests

from config.settings import TELEGRAM_BOT_TOKEN_ENV, TELEGRAM_CHAT_ID_ENV


def _send_telegram(message: str) -> bool:
    token = os.getenv(TELEGRAM_BOT_TOKEN_ENV)
    chat_id = os.getenv(TELEGRAM_CHAT_ID_ENV)

    if not token or not chat_id:
        print("Telegram credentials missing. Message below:")
        print(message)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        response.raise_for_status()
        return True

    except Exception as exc:
        print(f"Telegram send failed: {exc}")
        print(message)
        return False


def _format_number(value) -> str:
    if value is None:
        return "NA"

    try:
        value = float(value)
    except Exception:
        return str(value)

    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"

    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"

    return f"{value:.2f}"


def _format_percent(value) -> str:
    if value is None:
        return "NA"

    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return str(value)


def _format_headlines(headlines: list[dict]) -> str:
    if not headlines:
        return "No recent headlines found."

    lines = []

    for item in headlines[:3]:
        title = item.get("title", "Untitled")
        publisher = item.get("publisher") or "Unknown"
        score = item.get("score", 0)
        lines.append(f"- {title} ({publisher}, sentiment {score})")

    return "\n".join(lines)


def send_long_term_alert(result) -> bool:
    f = result.fundamentals or {}

    message = f"""
🧭 *LONG-TERM ACCUMULATION RADAR*

*{result.ticker}* — ${result.price}
Rating: *{result.rating}*
Action: *{result.action}*
Risk: *{result.risk}*

*Total Score:* {result.total_score}/100
- Quality: {result.quality_score}/50
- Valuation: {result.valuation_score}/30
- Discount: {result.discount_score}/15
- Technical: {result.technical_score}/5

*Key Metrics*
- PEG: {_format_number(f.get("peg_ratio"))}
- Forward P/E: {_format_number(f.get("forward_pe"))}
- Revenue growth: {_format_percent(f.get("revenue_growth"))}
- Gross margin: {_format_percent(f.get("gross_margins"))}
- Free cash flow: {_format_number(f.get("free_cashflow"))}

*News Sentiment*
- Label: {result.sentiment_label}
- Score: {result.sentiment_score}

*Latest Headlines*
{_format_headlines(result.headlines)}

_Not financial advice. Long-term accumulation scanner._
""".strip()

    return _send_telegram(message)


def send_long_term_summary(results: list) -> bool:
    if not results:
        return _send_telegram(
            "🧭 *Long-term accumulation scan complete*: No candidates met the threshold today."
        )

    rows = []

    for r in results[:10]:
        rows.append(
            f"{r.ticker}: {r.total_score}/100 | {r.rating} | "
            f"Q {r.quality_score}, V {r.valuation_score}, "
            f"D {r.discount_score}, T {r.technical_score} | "
            f"Sent {r.sentiment_label}"
        )

    message = "🧭 *Long-term Accumulation Top Candidates*\n\n" + "\n".join(rows)

    return _send_telegram(message)
