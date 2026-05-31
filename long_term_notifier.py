"""
long_term_notifier.py

Telegram alert formatting for long-term accumulation scanner.
Uses:
    V11_TELEGRAM_BOT_TOKEN
    V11_TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import os
import requests


def _send_telegram(message: str) -> bool:
    token = os.getenv("V11_TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("V11_TELEGRAM_CHAT_ID")

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
- PEG: {f.get("peg_ratio")}
- Forward P/E: {f.get("forward_pe")}
- Revenue growth: {f.get("revenue_growth")}
- Gross margin: {f.get("gross_margins")}
- Free cash flow: {f.get("free_cashflow")}

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
        return _send_telegram("🧭 *Long-term accumulation scan complete*: No candidates met the threshold today.")

    rows = []
    for r in results[:10]:
        rows.append(
            f"{r.ticker}: {r.total_score}/100 | {r.rating} | "
            f"Q {r.quality_score}, V {r.valuation_score}, D {r.discount_score}, T {r.technical_score} | "
            f"Sent {r.sentiment_label}"
        )

    message = "🧭 *Long-term Accumulation Top Candidates*\n\n" + "\n".join(rows)
    return _send_telegram(message)
