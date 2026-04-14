# Swing Trade Signal Scanner

## What's New in v1.1

v1.1 introduces 7 targeted improvements based on a 3.5-week signal audit (Mar 21 – Apr 14, 2026):

| Change | Impact |
|---|---|
| SPY hard gate | Blocks all alerts in bear market conditions |
| Volume tiers | Separates confirmed entries from watchlist setups |
| Sentiment block | Prevents entries against negative news flow |
| Geo risk penalty | Reduces score when geopolitical risk detected |
| Ticker veto | Manual override for repeatedly failing setups |
| RSI ceiling 65→70 | Captures strong momentum stocks correctly |
| Sector ETF gate | Blocks sector-specific signals during sector downturns |

v1.1 is designed to run in parallel with v1.0 for 3 weeks for A/B evaluation before v1.0 is retired.

---

## Overview

Swing Trade Signal Scanner is an automated technical analysis system that screens a curated watchlist of 22 tickers daily and fires structured Telegram alerts for high-probability swing trade setups.

It runs on GitHub Actions on a weekday schedule (09:00 UTC and 20:00 UTC), fetches OHLCV data via yfinance, scores each ticker across 10 technical factors, and dispatches two types of alerts — **CONFIRMED** (🚀) and **WATCHLIST** (👁) — each with full market context.

---

## Architecture

```
main.py            Orchestrator: gates, scoring, tier dispatch, logging
├── fetcher.py     yfinance data layer (batching, retry)
├── screener.py    SPY hard gate + sector ETF overlay gates
├── scorer.py      10-factor composite score (0–100)
├── notifier.py    Telegram alert formatting and dispatch
└── config/
    ├── settings.py         All constants, watchlist, sector map
    └── vetoed_tickers.json Manual veto list
```

---

## Alert Types

### 🚀 CONFIRMED Signal
Sent when ALL of the following are met:
- SPY is above its 20-day EMA (gate open)
- Volume ratio ≥ 1.3x and score ≥ 75
- Sentiment score ≥ 0 (not negative)
- Sector ETF is above its 10-day EMA
- Ticker is not in the deduplication cooldown (5 days)
- Ticker is not vetoed

### 👁 WATCHLIST Alert
Sent when setup is technically strong but one condition is unconfirmed:
- Volume < 1.3x AND score ≥ 80 (volume unconfirmed), OR
- Sector ETF below 10 EMA (sector headwind), OR
- Negative sentiment detected (flagged but not hard-blocked for watchlist)

WATCHLIST alerts use the 👁 emoji instead of 🚀 for instant visual
differentiation in the Telegram channel.

### 🚫 SPY Gate Message
Sent exactly once per run when SPY is below its 20-day EMA:
- NO per-ticker alerts are fired
- Top 3 tickers by score are listed for manual review
- All scores are still computed and logged

---

## Scoring Model

10 factors, max 100 points raw:

| Factor | Max pts | Notes |
|---|---|---|
| RSI | 15 | Momentum zone 50–70; oversold bounce 30–45 |
| EMA alignment | 20 | Price > 20EMA > 50EMA > 200EMA |
| Volume | 12 | Ratio vs 20-day avg (scoring only; tier is separate) |
| Breakout | 15 | Close above 20-day consolidation box |
| MACD | 10 | Line above signal, histogram expanding |
| Relative strength | 8 | 10-day return vs SPY |
| ATR/volatility | 5 | Healthy range 1.5%–5% |
| Sentiment | 8 | News sentiment score |
| Key levels | 5 | Above prior swing high |
| Geo risk (raw) | 2 | 0 if geo risk detected |

**v1.1 post-scoring adjustment:** If geopolitical risk is detected,
8 points are subtracted from the final score (floor 0). Max score with
geo risk = 92.

---

## Volume Tier System (v1.1)

| Volume | Score | Tier |
|---|---|---|
| ≥ 1.3x | ≥ 75 | CONFIRMED → Telegram alert |
| ≥ 1.3x | 60–74 | MEDIUM → log only, no alert |
| < 1.3x | ≥ 80 | WATCHLIST → Telegram alert (unconfirmed) |
| < 1.3x | 60–79 | LOW → log only |
| < 0.5x | any | DEAD → suppress entirely |

---

## Gating Hierarchy

Applied in order (highest priority first):

1. **Vetoed ticker** — skip entirely (no analysis, no log)
2. **SPY below 20 EMA** — block all alerts; send SPY gate summary
3. **Volume < 0.5x** — suppress regardless of score
4. **Negative sentiment** — blocked from CONFIRMED; can appear in WATCHLIST
5. **Sector ETF below 10 EMA** — downgrade from CONFIRMED to WATCHLIST
6. **Dedup cooldown (5 days)** — skip alert (still score and log)
7. **Volume/score tier** — final CONFIRMED vs WATCHLIST vs log-only

---

## Sector ETF Map

| Sector | ETF | EMA | Tickers |
|---|---|---|---|
| Cybersecurity | CIBR | 10 | CRWD, PLTR, NET, PANW, ZS, OKTA |
| Semiconductors | SOXX | 10 | NVDA, AMD, MU, QCOM, TSM, COHR |
| Cloud | WCLD | 10 | SHOP, NET, CRWD, SNOW, DDOG |
| Space | UFO | 10 | RKLB, ASTS, MNTS |

Tickers not in any sector map are not subject to sector gating.
Sector gate is SOFTER than SPY gate: sector caution only downgrades
affected tickers from CONFIRMED to WATCHLIST; it does not block everything.

---

## Ticker Veto System

If a ticker keeps generating false signals, add it to `config/vetoed_tickers.json`:

```json
{
  "PLTR": {
    "vetoed_until": "2026-04-20",
    "reason": "3x miss — price failed to move +5% within 7 days on 3 consecutive signals"
  }
}
```

The system will **completely ignore** the vetoed ticker (no analysis, no
scoring, no log entry in top picks) until the `vetoed_until` date passes.
After that date, the ticker is automatically reinstated on the next run.

This is intentionally a **manual** mechanism to keep human judgment in
the loop. Do not automate the veto decision. A miss is defined as the
signal price failing to achieve +5% within 7 days.

---

## Log Format (v1.1)

Logs are written to `logs/v1.1/YYYY-MM-DD.json` (separate from v1.0's `logs/`).

Each ticker entry:

```json
{
  "ticker": "NET",
  "score": 74,
  "raw_score": 82,
  "volume_tier": "unconfirmed",
  "volume_ratio": 1.15,
  "alert_sent": false,
  "block_reasons": ["negative_sentiment", "sector_etf_caution"],
  "spy_gate": "open",
  "sector": "cybersecurity",
  "sector_etf_status": "below_10ema",
  "geo_risk_penalty": -8,
  "final_score_after_penalty": 66,
  "sentiment": -0.038,
  "price": 108.42
}
```

---

## Setup

### 1. Clone repo

```bash
git clone https://github.com/YOUR_USERNAME/swing-trade-signal-v11.git
cd swing-trade-signal-v11
pip install -r requirements.txt
```

### 2. Add Telegram secrets

In your GitHub repo → Settings → Secrets → Actions, add:

| Secret | Description |
|---|---|
| `V11_TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `V11_TELEGRAM_CHAT_ID` | Target channel/chat ID |

These are separate from the v1.0 secrets (`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`)
so both versions can run in parallel to different channels.

### 3. Run locally

```bash
export V11_TELEGRAM_BOT_TOKEN="your_token"
export V11_TELEGRAM_CHAT_ID="your_chat_id"
python main.py
```

### 4. Run tests

```bash
pytest tests/test_scorer.py -v
```

---

## A/B Evaluation (v1.0 vs v1.1)

v1.1 runs in parallel with v1.0 for a minimum of 3 weeks before v1.0 is retired.

Evaluation criteria:
- **Signal accuracy**: % of CONFIRMED alerts that achieve +5% within 7 days
- **False positive rate**: alerts fired that reverse within 2 days
- **Alert volume**: total alerts per week (v1.1 should fire fewer, higher-quality alerts)
- **SPY gate effectiveness**: did it correctly block alerts during corrections?
- **Sector gate value**: did it prevent sector-specific false signals?

Logs are structured JSON in `logs/v1.1/` specifically to support automated
A/B analysis against v1.0's `logs/` directory.

---

## What's NOT Changed from v1.0

The following are **identical** to v1.0 to ensure fair A/B comparison:

- Watchlist (same 22 tickers)
- Data fetching logic (yfinance, batching, retry)
- All 10 scoring factors and their weights
- Indicator calculations (RSI, EMA, MACD, ATR, etc.)
- Alert message body format (only header and footer blocks are new)
- GitHub Actions schedule (09:00 UTC and 20:00 UTC on weekdays)
- requirements.txt
- sent_signals.json 5-day deduplication cooldown (veto is additive)

---

## Version

`v1.1` — April 2026

_SwingScanner v1.1 | Not financial advice_
