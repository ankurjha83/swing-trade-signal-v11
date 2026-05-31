"""
main_long_term.py

Standalone long-term accumulation scanner.

Run:
    python main_long_term.py
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from config.settings import WATCHLIST

from long_term_fetcher import fetch_long_term_data
from long_term_scorer import score_long_term_candidate
from long_term_notifier import send_long_term_alert, send_long_term_summary
from sentiment_analyzer import analyze_news_sentiment


LOG_DIR = Path("logs/long_term")
MIN_ALERT_SCORE = 70
SEND_INDIVIDUAL_ALERTS = True
SEND_SUMMARY_ALERT = True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("main_long_term")


def write_log(results: list, skipped: list[dict]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    run_date = date.today().isoformat()
    log_path = LOG_DIR / f"{run_date}.json"

    payload = {
        "scanner": "long_term_accumulation",
        "run_date": run_date,
        "run_ts": datetime.now(timezone.utc).isoformat(),
        "min_alert_score": MIN_ALERT_SCORE,
        "results": [asdict(r) for r in results],
        "skipped": skipped,
    }

    with open(log_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    logger.info(f"Wrote long-term log to {log_path}")


def run() -> None:
    logger.info("=== Long-term accumulation scanner starting ===")
    logger.info(f"Loaded {len(WATCHLIST)} tickers from WATCHLIST")

    results = []
    skipped = []

    for ticker in WATCHLIST:
        logger.info(f"Scanning {ticker}")

        long_term_data = fetch_long_term_data(ticker)

        if long_term_data.get("error"):
            skipped.append({"ticker": ticker, "reason": long_term_data["error"]})
            logger.warning(f"{ticker}: skipped — {long_term_data['error']}")
            continue

        sentiment = analyze_news_sentiment(long_term_data.get("news", []))
        result = score_long_term_candidate(ticker, long_term_data, sentiment)

        if result is None:
            skipped.append({"ticker": ticker, "reason": "scoring_failed"})
            logger.warning(f"{ticker}: scoring failed")
            continue

        results.append(result)

    results = sorted(results, key=lambda r: r.total_score, reverse=True)
    write_log(results, skipped)

    alert_candidates = [
        r for r in results
        if r.total_score >= MIN_ALERT_SCORE and r.rating not in {"Avoid", "Blocked"}
    ]

    if SEND_INDIVIDUAL_ALERTS:
        for result in alert_candidates:
            send_long_term_alert(result)

    if SEND_SUMMARY_ALERT:
        send_long_term_summary(results)

    logger.info(
        f"=== Long-term scan complete: {len(alert_candidates)} alert candidates, "
        f"{len(results)} scored, {len(skipped)} skipped ==="
    )


if __name__ == "__main__":
    run()
