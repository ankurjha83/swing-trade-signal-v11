"""
notifier.py — Telegram Alert Formatting & Dispatch (v1.1)
==========================================================
Handles three message types:

  1. CONFIRMED alert  (🚀) — high-score, volume-confirmed, sentiment OK,
                             sector healthy, SPY gate open
  2. WATCHLIST alert  (👁)  — technically strong but volume unconfirmed
                             OR sector in caution mode
  3. SPY gate message (🚫) — sent when SPY is below 20 EMA; one per run

Message body format is IDENTICAL to v1.0.
Header and footer blocks are new in v1.1 (version, SPY status, sector status).

IMPORTANT: The alert BODY content (score breakdown text) must remain
identical in structure to v1.0. Only the header block above it and the
footer below it are new/changed in v1.1.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import requests

from config.settings import VERSION

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("V11_TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("V11_TELEGRAM_CHAT_ID", "")
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


# ---------------------------------------------------------------------------
# Telegram send helper
# ---------------------------------------------------------------------------

def _send_telegram(message: str, parse_mode: str = "Markdown") -> bool:
    """Send a Telegram message. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Telegram credentials not set (V11_TELEGRAM_BOT_TOKEN / V11_TELEGRAM_CHAT_ID)")
        return False

    url = TELEGRAM_API_URL.format(token=TELEGRAM_BOT_TOKEN)
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        logger.debug(f"Telegram message sent ({len(message)} chars)")
        return True
    except requests.RequestException as exc:
        logger.error(f"Telegram send failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Header / footer builders
# ---------------------------------------------------------------------------

def _build_header(
    alert_type: str,           # "CONFIRMED" or "WATCHLIST"
    spy_status: str,           # "✅ above 20 EMA" or "⚠️ below 20 EMA"
    sector: str | None,
    sector_etf: str | None,
    sector_status: str | None, # "✅ above 10 EMA" or "⚠️ below 10 EMA"
) -> str:
    """
    Builds the v1.1 header block prepended to every alert.

    Format:
        📊 *SWING SCANNER v1.1*
        🗓 {date} | {time} UTC
        ━━━━━━━━━━━━━━━━━━━━━
        🌐 Market: SPY ✅ above 20 EMA
        💹 Sector: {sector} ETF ✅/⚠️ {above/below} 10 EMA
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    lines = [
        f"📊 *SWING SCANNER v{VERSION}*",
        f"🗓 {date_str} | {time_str} UTC",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"🌐 Market: SPY {spy_status}",
    ]

    if sector and sector_etf and sector_status:
        lines.append(f"💹 Sector: {sector.title()} ({sector_etf}) ETF {sector_status}")
    else:
        lines.append("💹 Sector: N/A")

    lines.append("")  # blank line before body
    return "\n".join(lines)


def _build_footer() -> str:
    """Footer appended to every alert — includes version."""
    return f"\n_SwingScanner v{VERSION} | Not financial advice_"


# ---------------------------------------------------------------------------
# CONFIRMED alert (🚀)
# ---------------------------------------------------------------------------

def build_confirmed_alert(
    ticker: str,
    price: float,
    score: int,
    volume_ratio: float,
    factor_breakdown: dict,
    geo_risk_penalty: int,
    sector: str | None,
    sector_etf: str | None,
    sector_in_caution: bool,
    spy_gate_open: bool,
) -> str:
    """
    Build a CONFIRMED alert message.
    Uses 🚀 emoji.
    Header includes SPY ✅ and sector status.
    """
    spy_status = "✅ above 20 EMA — market condition favorable" if spy_gate_open else "⚠️ below 20 EMA"
    sector_status = None
    if sector and sector_etf:
        sector_status = "⚠️ below 10 EMA — sector headwind" if sector_in_caution else "✅ above 10 EMA"

    header = _build_header("CONFIRMED", spy_status, sector, sector_etf, sector_status)

    # --- Body (identical structure to v1.0) ---
    body_lines = [
        "🚀 *CONFIRMED SIGNAL*",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"📌 Ticker: ${ticker}",
        f"💰 Price: ${price:.2f}",
        f"📊 Score: {score}/100 | Vol: {volume_ratio:.2f}x ✅ CONFIRMED",
        "",
        "*Factor Breakdown:*",
    ]

    for factor, data in factor_breakdown.items():
        pts = data.get("score", 0)
        note = data.get("note", "")
        body_lines.append(f"  • {factor}: {pts}pts — {note}")

    if geo_risk_penalty > 0:
        body_lines.append(f"\n🌍 Geopolitical risk penalty applied: -{geo_risk_penalty}pts")

    body_lines.append("━━━━━━━━━━━━━━━━━━━━━")

    footer = _build_footer()
    return header + "\n".join(body_lines) + footer


# ---------------------------------------------------------------------------
# WATCHLIST alert (👁)
# ---------------------------------------------------------------------------

def build_watchlist_alert(
    ticker: str,
    price: float,
    score: int,
    volume_ratio: float,
    factor_breakdown: dict,
    geo_risk_penalty: int,
    sentiment_score: float,
    sentiment_negative: bool,
    sector: str | None,
    sector_etf: str | None,
    sector_in_caution: bool,
    spy_gate_open: bool,
    watchlist_reason: str,  # e.g. "volume_unconfirmed" | "sector_caution" | "both"
) -> str:
    """
    Build a WATCHLIST alert message.
    Uses 👁 emoji (NOT 🚀 — instant visual distinction in channel).

    Watchlist alert format matches spec exactly.
    """
    spy_status = "✅ above 20 EMA — market condition favorable" if spy_gate_open else "⚠️ below 20 EMA"
    sector_status = None
    if sector and sector_etf:
        sector_status = "⚠️ below 10 EMA — sector headwind" if sector_in_caution else "✅ above 10 EMA"

    header = _build_header("WATCHLIST", spy_status, sector, sector_etf, sector_status)

    # --- Volume label ---
    if volume_ratio >= 1.3:
        vol_label = f"{volume_ratio:.2f}x ✅"
    elif volume_ratio >= 0.5:
        vol_label = f"{volume_ratio:.2f}x ⚠️ LOW ⚠️"
    else:
        vol_label = f"{volume_ratio:.2f}x ❌ VERY LOW"

    body_lines = [
        "👁 *WATCHLIST ALERT — Volume Unconfirmed*",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"📌 Ticker: ${ticker}",
        f"💰 Price: ${price:.2f}",
        f"📊 Score: {score}/100 | Vol: {vol_label}",
    ]

    # Reason-specific warnings
    if watchlist_reason in ("volume_unconfirmed", "both"):
        body_lines.append(
            "⚠️ Setup looks strong technically but volume has NOT confirmed. "
            "Watch for volume spike above 1.3x before entering. "
            "Do NOT act on this alert alone."
        )

    if sector_in_caution and sector_etf:
        body_lines.append(
            f"⚠️ Sector ETF ({sector_etf}) below 10 EMA — sector headwind"
        )

    if sentiment_negative:
        body_lines.append(
            f"⚠️ Sentiment negative ({sentiment_score:.3f}). Proceed with extra caution."
        )

    if geo_risk_penalty > 0:
        body_lines.append(f"🌍 Geopolitical risk penalty applied: -{geo_risk_penalty}pts")

    body_lines.append("━━━━━━━━━━━━━━━━━━━━━")

    footer = _build_footer()
    return header + "\n".join(body_lines) + footer


# ---------------------------------------------------------------------------
# SPY gate message (🚫)
# ---------------------------------------------------------------------------

def build_spy_gate_message(
    top_tickers: list[tuple[str, int]],  # [(ticker, score), ...] top 3 by score
) -> str:
    """
    Build the single SPY-gate summary message sent when gate is CLOSED.

    Format:
        🚫 SPY below 20 EMA. Market in caution zone. No alerts fired today.
        Top technical setups logged: $TICKER1 (82), $TICKER2 (78), $TICKER3 (71).
        Review logs for details.
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    top_str = ", ".join(
        f"${t} ({s})" for t, s in top_tickers
    ) if top_tickers else "none scored above threshold"

    lines = [
        f"📊 *SWING SCANNER v{VERSION}*",
        f"🗓 {date_str} | {time_str} UTC",
        "━━━━━━━━━━━━━━━━━━━━━",
        "🚫 *SPY below 20 EMA. Market in caution zone. No alerts fired today.*",
        "",
        f"Top technical setups logged: {top_str}.",
        "Review logs for details.",
        "━━━━━━━━━━━━━━━━━━━━━",
        _build_footer(),
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public dispatch functions
# ---------------------------------------------------------------------------

def send_confirmed_alert(
    ticker: str,
    price: float,
    score: int,
    volume_ratio: float,
    factor_breakdown: dict,
    geo_risk_penalty: int,
    sector: str | None,
    sector_etf: str | None,
    sector_in_caution: bool,
    spy_gate_open: bool,
) -> bool:
    msg = build_confirmed_alert(
        ticker=ticker,
        price=price,
        score=score,
        volume_ratio=volume_ratio,
        factor_breakdown=factor_breakdown,
        geo_risk_penalty=geo_risk_penalty,
        sector=sector,
        sector_etf=sector_etf,
        sector_in_caution=sector_in_caution,
        spy_gate_open=spy_gate_open,
    )
    logger.info(f"Sending CONFIRMED alert for {ticker} (score={score})")
    return _send_telegram(msg)


def send_watchlist_alert(
    ticker: str,
    price: float,
    score: int,
    volume_ratio: float,
    factor_breakdown: dict,
    geo_risk_penalty: int,
    sentiment_score: float,
    sentiment_negative: bool,
    sector: str | None,
    sector_etf: str | None,
    sector_in_caution: bool,
    spy_gate_open: bool,
    watchlist_reason: str,
) -> bool:
    msg = build_watchlist_alert(
        ticker=ticker,
        price=price,
        score=score,
        volume_ratio=volume_ratio,
        factor_breakdown=factor_breakdown,
        geo_risk_penalty=geo_risk_penalty,
        sentiment_score=sentiment_score,
        sentiment_negative=sentiment_negative,
        sector=sector,
        sector_etf=sector_etf,
        sector_in_caution=sector_in_caution,
        spy_gate_open=spy_gate_open,
        watchlist_reason=watchlist_reason,
    )
    logger.info(f"Sending WATCHLIST alert for {ticker} (score={score}, reason={watchlist_reason})")
    return _send_telegram(msg)


def send_spy_gate_message(top_tickers: list[tuple[str, int]]) -> bool:
    msg = build_spy_gate_message(top_tickers)
    logger.warning(f"Sending SPY gate message (top tickers: {top_tickers})")
    return _send_telegram(msg)
