"""
main.py — Swing Scanner v1.1 Orchestrator
==========================================
Run order:
  1. Load vetoed_tickers.json  (CHANGE 5)
  2. Fetch SPY → SPY hard gate  (CHANGE 1)
  3. Fetch sector ETFs → sector gate statuses  (CHANGE 7)
  4. Fetch OHLCV + sentiment + geo-risk for each non-vetoed ticker
  5. Score each ticker (scorer.py)
  6. Determine alert tier per ticker  (CHANGE 2, 3, 7)
  7. Dispatch alerts (or SPY gate summary) via notifier.py
  8. Write daily JSON log to logs/v1.1/YYYY-MM-DD.json
  9. Update sent_signals.json deduplication state

Gating hierarchy (highest to lowest priority):
  a) Ticker in vetoed_tickers.json → skip entirely
  b) SPY below 20 EMA → no per-ticker alerts; send one SPY gate message
  c) Volume < 0.5x → suppress regardless of score
  d) Negative sentiment → blocked from CONFIRMED; can appear in WATCHLIST
  e) Sector ETF below 10 EMA → downgraded from CONFIRMED to WATCHLIST
  f) Deduplication cooldown (5 days) → skip alert (still log)
  g) Volume / score tier logic → CONFIRMED vs WATCHLIST vs log-only
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from config.settings import (
    DEDUP_COOLDOWN_DAYS,
    LOG_DIR,
    SECTOR_ETF_MAP,
    SENT_SIGNALS_FILE,
    SPY_TOP_TICKERS_IN_GATE_MSG,
    TIER_CONFIRMED_MIN_SCORE,
    TIER_MEDIUM_MIN_SCORE,
    TIER_WATCHLIST_MIN_SCORE,
    VETOED_TICKERS_FILE,
    VERSION,
    VOLUME_CONFIRMED_THRESHOLD,
    VOLUME_DEAD_THRESHOLD,
    WATCHLIST,
    SENTIMENT_BLOCK_THRESHOLD,
)
from fetcher import fetch_ohlcv_batch, fetch_spy_daily
from scorer import SentimentResult, score_ticker
from screener import check_sector_gates, check_spy_gate, get_ticker_sector, is_ticker_sector_in_caution
from notifier import send_confirmed_alert, send_spy_gate_message, send_watchlist_alert

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Helpers: veto management
# ---------------------------------------------------------------------------

def load_vetoed_tickers() -> dict:
    """
    Load config/vetoed_tickers.json.
    Returns {ticker: {"vetoed_until": "YYYY-MM-DD", "reason": str}}

    CHANGE 5: Vetoed tickers are COMPLETELY skipped — not analyzed, not alerted,
    not logged in top picks.
    """
    path = Path(VETOED_TICKERS_FILE)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        # Strip meta keys starting with _
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Could not load {VETOED_TICKERS_FILE}: {exc}")
        return {}


def is_ticker_vetoed(ticker: str, vetoed: dict) -> bool:
    """Return True if ticker is currently under veto (vetoed_until in future)."""
    entry = vetoed.get(ticker)
    if not entry:
        return False
    try:
        until = date.fromisoformat(entry["vetoed_until"])
        return date.today() <= until
    except (KeyError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Helpers: deduplication
# ---------------------------------------------------------------------------

def load_sent_signals() -> dict:
    path = Path(SENT_SIGNALS_FILE)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_sent_signals(signals: dict) -> None:
    with open(SENT_SIGNALS_FILE, "w") as f:
        json.dump(signals, f, indent=2)


def is_in_cooldown(ticker: str, signals: dict) -> bool:
    """Return True if ticker was alerted within the last DEDUP_COOLDOWN_DAYS days."""
    entry = signals.get(ticker)
    if not entry:
        return False
    try:
        last_alerted = date.fromisoformat(entry["last_alerted"])
        return (date.today() - last_alerted).days < DEDUP_COOLDOWN_DAYS
    except (KeyError, ValueError):
        return False


def mark_as_alerted(ticker: str, signals: dict, alert_type: str = "confirmed") -> None:
    """Update sent_signals.json entry for ticker."""
    if ticker not in signals:
        signals[ticker] = {}
    signals[ticker]["last_alerted"] = date.today().isoformat()
    signals[ticker]["alert_type"] = alert_type
    signals[ticker].setdefault("consecutive_misses", 0)


# ---------------------------------------------------------------------------
# Helpers: sentiment & geo risk (stub — replace with real API integration)
# ---------------------------------------------------------------------------

def fetch_sentiment(ticker: str) -> SentimentResult:
    """
    Fetch news sentiment for a ticker.
    Replace this stub with your preferred news API (e.g. NewsAPI, Benzinga).
    Returns a SentimentResult with score in range ~[-1, 1].
    """
    # Stub: returns neutral for all tickers.
    # In production: call your news sentiment API here.
    return SentimentResult(score=0.0, label="neutral", source="stub")


def fetch_geo_risk(ticker: str) -> bool:
    """
    Return True if geopolitical risk signal is detected for this ticker.
    Replace stub with your data source (e.g. geopolitical risk index API).
    """
    # Stub: no geo risk by default.
    return False


# ---------------------------------------------------------------------------
# Helpers: daily log
# ---------------------------------------------------------------------------

def write_daily_log(run_date: str, records: list[dict], skipped: list[str], spy_status: str) -> None:
    """
    Write structured JSON log to logs/v1.1/YYYY-MM-DD.json.

    CHANGE: Log directory is logs/v1.1/ (not logs/) for v1.1 runs.
    """
    log_dir = Path(LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{run_date}.json"

    payload = {
        "version": VERSION,
        "run_date": run_date,
        "run_ts": datetime.now(timezone.utc).isoformat(),
        "spy_gate": spy_status,
        "skipped_vetoed": skipped,
        "tickers": records,
    }

    with open(log_path, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Daily log written to {log_path}")


# ---------------------------------------------------------------------------
# Alert tier determination  (CHANGE 2, 3, 7)
# ---------------------------------------------------------------------------

def determine_alert_tier(
    ticker: str,
    final_score: int,
    volume_ratio: float,
    sentiment_score: float,
    sector_in_caution: bool,
) -> tuple[str, list[str]]:
    """
    Determine the alert dispatch tier for a ticker.

    Returns (tier, block_reasons) where tier is one of:
      "confirmed"   → send CONFIRMED alert  (🚀)
      "watchlist"   → send WATCHLIST alert  (👁)
      "log_only"    → do not send any alert
      "suppressed"  → do not send, do not log in top picks

    Block reasons are appended to the daily log entry.
    """
    block_reasons: list[str] = []

    # Hard suppress: dead volume
    if volume_ratio < VOLUME_DEAD_THRESHOLD:
        return "suppressed", ["dead_volume"]

    # Sentiment block on CONFIRMED (CHANGE 3)
    sentiment_blocks_confirmed = sentiment_score < SENTIMENT_BLOCK_THRESHOLD
    if sentiment_blocks_confirmed:
        block_reasons.append("negative_sentiment")

    # Sector caution block on CONFIRMED (CHANGE 7)
    if sector_in_caution:
        block_reasons.append("sector_etf_caution")

    # Determine base tier from volume × score (CHANGE 2)
    high_volume = volume_ratio >= VOLUME_CONFIRMED_THRESHOLD

    if high_volume:
        if final_score >= TIER_CONFIRMED_MIN_SCORE:
            # Can be CONFIRMED unless blocked by sentiment or sector
            if block_reasons:
                # Downgraded to WATCHLIST
                return "watchlist", block_reasons
            return "confirmed", []
        elif final_score >= TIER_MEDIUM_MIN_SCORE:
            return "log_only", block_reasons
        else:
            return "suppressed", block_reasons
    else:
        # Low volume
        if final_score >= TIER_WATCHLIST_MIN_SCORE:
            return "watchlist", block_reasons + ["volume_unconfirmed"]
        elif final_score >= TIER_MEDIUM_MIN_SCORE:
            return "log_only", block_reasons + ["low_volume"]
        else:
            return "suppressed", block_reasons + ["low_volume"]


def get_watchlist_reason(block_reasons: list[str]) -> str:
    """Summarise why a WATCHLIST alert was sent (for notifier)."""
    if "volume_unconfirmed" in block_reasons and "sector_etf_caution" in block_reasons:
        return "both"
    if "volume_unconfirmed" in block_reasons:
        return "volume_unconfirmed"
    if "sector_etf_caution" in block_reasons:
        return "sector_caution"
    return "downgraded"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run() -> None:
    today = date.today().isoformat()
    logger.info(f"=== Swing Scanner v{VERSION} starting — {today} ===")

    # ------------------------------------------------------------------ #
    # STEP 1: Load veto list  (CHANGE 5)
    # ------------------------------------------------------------------ #
    vetoed = load_vetoed_tickers()
    active_tickers = [t for t in WATCHLIST if not is_ticker_vetoed(t, vetoed)]
    skipped_vetoed = [t for t in WATCHLIST if is_ticker_vetoed(t, vetoed)]

    if skipped_vetoed:
        logger.info(f"Vetoed tickers skipped: {skipped_vetoed}")
        # Structured skip log
        logger.info(json.dumps({"skipped": skipped_vetoed, "reason": "vetoed"}))

    # ------------------------------------------------------------------ #
    # STEP 2: SPY hard gate  (CHANGE 1)
    # ------------------------------------------------------------------ #
    spy_gate = check_spy_gate()
    spy_gate_str = "open" if spy_gate.gate_open else "closed"

    # ------------------------------------------------------------------ #
    # STEP 3: Sector ETF gates  (CHANGE 7)
    # ------------------------------------------------------------------ #
    sector_gates = check_sector_gates()

    # ------------------------------------------------------------------ #
    # STEP 4–6: Fetch data, score, tier
    # ------------------------------------------------------------------ #
    # Batch-fetch all active tickers + SPY (for relative strength)
    spy_df = fetch_spy_daily(lookback_days=60)
    all_ohlcv = fetch_ohlcv_batch(active_tickers, period="90d")

    log_records: list[dict] = []
    alerts_to_send: list[dict] = []  # queued until after logging

    for ticker in active_tickers:
        df = all_ohlcv.get(ticker)
        if df is None or len(df) < 30:
            logger.warning(f"{ticker}: insufficient data, skipping")
            continue

        # Fetch auxiliary signals
        sentiment = fetch_sentiment(ticker)
        geo_risk = fetch_geo_risk(ticker)

        # Score
        sb = score_ticker(
            ticker=ticker,
            df=df,
            spy_df=spy_df,
            sentiment=sentiment,
            geo_risk_detected=geo_risk,
        )

        # Sector status
        sector = get_ticker_sector(ticker)
        sector_in_caution, sector_etf = is_ticker_sector_in_caution(ticker, sector_gates)
        sector_etf_status = "below_10ema" if sector_in_caution else "above_10ema"

        # Alert tier
        tier, block_reasons = determine_alert_tier(
            ticker=ticker,
            final_score=sb.final_score,
            volume_ratio=sb.volume_ratio,
            sentiment_score=sb.sentiment_score,
            sector_in_caution=sector_in_caution,
        )

        # Build log record
        record = {
            "ticker": ticker,
            "score": sb.final_score,
            "raw_score": sb.raw_score,
            "volume_tier": tier,
            "volume_ratio": round(sb.volume_ratio, 3),
            "alert_sent": False,  # will be updated after dispatch
            "block_reasons": block_reasons,
            "spy_gate": spy_gate_str,
            "sector": sector,
            "sector_etf_status": sector_etf_status,
            "geo_risk_penalty": -sb.geo_risk_penalty if sb.geo_risk_penalty else 0,
            "final_score_after_penalty": sb.final_score,
            "sentiment": round(sb.sentiment_score, 4),
            "price": sb.price,
            "factors": sb.factors,
        }

        # If sentiment is blocking, log the block reason with score
        if sb.sentiment_score < SENTIMENT_BLOCK_THRESHOLD:
            record["blocked_reason"] = "negative_sentiment"

        log_records.append(record)

        # Queue for alert dispatch (actual send happens in STEP 7)
        if tier in ("confirmed", "watchlist"):
            alerts_to_send.append({
                "ticker": ticker,
                "tier": tier,
                "score": sb.final_score,
                "price": sb.price,
                "volume_ratio": sb.volume_ratio,
                "factor_breakdown": sb.factors,
                "geo_risk_penalty": sb.geo_risk_penalty,
                "sentiment_score": sb.sentiment_score,
                "sentiment_negative": sb.sentiment_score < SENTIMENT_BLOCK_THRESHOLD,
                "sector": sector,
                "sector_etf": sector_etf,
                "sector_in_caution": sector_in_caution,
                "block_reasons": block_reasons,
                "record_ref": record,  # for updating alert_sent flag
            })

    # ------------------------------------------------------------------ #
    # STEP 7: Dispatch
    # ------------------------------------------------------------------ #
    sent_signals = load_sent_signals()

    if not spy_gate.gate_open:
        # ---------------------------------------------------------------- #
        # SPY GATE CLOSED — send one summary, skip all per-ticker alerts
        # (CHANGE 1)
        # ---------------------------------------------------------------- #
        sorted_records = sorted(log_records, key=lambda r: r["score"], reverse=True)
        top_n = [
            (r["ticker"], r["score"])
            for r in sorted_records[:SPY_TOP_TICKERS_IN_GATE_MSG]
        ]
        send_spy_gate_message(top_n)

    else:
        # SPY gate is open — normal dispatch
        for alert in alerts_to_send:
            ticker = alert["ticker"]

            # Deduplication cooldown check (5-day, unchanged from v1.0)
            if is_in_cooldown(ticker, sent_signals):
                logger.info(f"{ticker}: in 5-day cooldown, skipping alert")
                alert["record_ref"]["block_reasons"].append("dedup_cooldown")
                continue

            success = False
            if alert["tier"] == "confirmed":
                success = send_confirmed_alert(
                    ticker=ticker,
                    price=alert["price"],
                    score=alert["score"],
                    volume_ratio=alert["volume_ratio"],
                    factor_breakdown=alert["factor_breakdown"],
                    geo_risk_penalty=alert["geo_risk_penalty"],
                    sector=alert["sector"],
                    sector_etf=alert["sector_etf"],
                    sector_in_caution=alert["sector_in_caution"],
                    spy_gate_open=spy_gate.gate_open,
                )
                if success:
                    mark_as_alerted(ticker, sent_signals, "confirmed")
            elif alert["tier"] == "watchlist":
                reason = get_watchlist_reason(alert["block_reasons"])
                success = send_watchlist_alert(
                    ticker=ticker,
                    price=alert["price"],
                    score=alert["score"],
                    volume_ratio=alert["volume_ratio"],
                    factor_breakdown=alert["factor_breakdown"],
                    geo_risk_penalty=alert["geo_risk_penalty"],
                    sentiment_score=alert["sentiment_score"],
                    sentiment_negative=alert["sentiment_negative"],
                    sector=alert["sector"],
                    sector_etf=alert["sector_etf"],
                    sector_in_caution=alert["sector_in_caution"],
                    spy_gate_open=spy_gate.gate_open,
                    watchlist_reason=reason,
                )
                if success:
                    mark_as_alerted(ticker, sent_signals, "watchlist")

            alert["record_ref"]["alert_sent"] = success

    # ------------------------------------------------------------------ #
    # STEP 8: Write daily log
    # ------------------------------------------------------------------ #
    write_daily_log(
        run_date=today,
        records=log_records,
        skipped=skipped_vetoed,
        spy_status=spy_gate_str,
    )

    # ------------------------------------------------------------------ #
    # STEP 9: Persist deduplication state
    # ------------------------------------------------------------------ #
    save_sent_signals(sent_signals)

    confirmed_count = sum(1 for r in log_records if r.get("alert_sent") and "confirmed" in r.get("volume_tier", ""))
    watchlist_count = sum(1 for r in log_records if r.get("alert_sent") and "watchlist" in r.get("volume_tier", ""))
    if confirmed_count == 0 and watchlist_count == 0 and spy_gate.gate_open:
        from notifier import _send_telegram
        top_3 = sorted(log_records, key=lambda x: x.get("score", 0), reverse=True)[:3]
        top_str = ", ".join(f"{r['ticker']} ({r.get('score',0)})" for r in top_3 if r.get("ticker"))
        _send_telegram(f"📭 *No recommendations today* — {today}\n\nNo signals met all entry criteria.\nTop setups (not actionable): {top_str}\n\n_SwingScanner v1.1 | Not financial advice_")
    watchlist_count = sum(1 for r in log_records if r.get("alert_sent") and "watchlist" in r.get("volume_tier", ""))
    logger.info(
        f"=== Run complete: {confirmed_count} confirmed alerts, "
        f"{watchlist_count} watchlist alerts, "
        f"SPY gate {'OPEN' if spy_gate.gate_open else 'CLOSED'} ==="
    )


if __name__ == "__main__":
    run()
