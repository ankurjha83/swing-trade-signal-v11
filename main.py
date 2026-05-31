"""
main.py

Long-term accumulation scanner.

This replaces the old swing scanner entry point.

Run:
    python main.py
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from config.settings import (
    LOG_DIR,
    MIN_ALERT_SCORE,
    MIN_DISCOUNT_SCORE,
    SEND_INDIVIDUAL_ALERTS,
    SEND_SUMMARY_ALERT,
    VERSION,
    WATCHLIST,
)
from long_term_fetcher import fetch_long_term_data
from long_term_notifier import send_long_term_alert, send_long_term_summary
from long_term_scorer import score_long_term_candidate
from sentiment_analyzer import analyze_news_sentiment


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("main")


def write_log(results: list, skipped: list[dict]) -> None:
    log_dir = Path(LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    run_date = date.today().isoformat()
    log_path = log_dir / f"{run_date}.json"

    payload = {
        "scanner": "long_term_accumulation",
        "version": VERSION,
        "run_date": run_date,
        "run_ts": datetime.now(timezone.utc).isoformat(),
        "min_alert_score": MIN_ALERT_SCORE,
        "results": [asdict(r) for r in results],
        "skipped": skipped,
    }

    with open(log_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    logger.info("Wrote long-term log to %s", log_path)


def run() -> None:
    logger.info("=== Long-term accumulation scanner starting ===")
    logger.info("Loaded %s tickers", len(WATCHLIST))

    results = []
    skipped = []

    for ticker in WATCHLIST:
        logger.info("Scanning %s", ticker)

        long_term_data = fetch_long_term_data(ticker)

        if long_term_data.get("error"):
            skipped.append({"ticker": ticker, "reason": long_term_data["error"]})
            logger.warning("%s skipped: %s", ticker, long_term_data["error"])
            continue

        sentiment = analyze_news_sentiment(long_term_data.get("news", []))
        result = score_long_term_candidate(ticker, long_term_data, sentiment)

        if result is None:
            skipped.append({"ticker": ticker, "reason": "scoring_failed"})
            logger.warning("%s scoring failed", ticker)
            continue

        results.append(result)

    results = sorted(results, key=lambda r: r.total_score, reverse=True)
    write_log(results, skipped)

    alert_candidates = [
        r for r in results
        if (
            r.total_score >= MIN_ALERT_SCORE
            and r.discount_score >= MIN_DISCOUNT_SCORE
            and r.rating not in {"Avoid", "Blocked"}
     )
    ]

    if SEND_INDIVIDUAL_ALERTS:
        for result in alert_candidates:
            send_long_term_alert(result)

    if SEND_SUMMARY_ALERT:
        send_long_term_summary(results)

    logger.info(
        "=== Long-term scan complete: %s alert candidates, %s scored, %s skipped ===",
        len(alert_candidates),
        len(results),
        len(skipped),
    )


if __name__ == "__main__":
    run()
