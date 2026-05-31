# Long-Term Accumulation Scanner

This repository runs a long-term accumulation scanner. The old swing-trading
entry point has been retired; `main.py` is now the production scanner.

## Architecture

```text
main.py                  Orchestrates watchlist loading, scoring, logging, alerts
main_long_term.py        Compatibility wrapper around main.run()
long_term_fetcher.py     yfinance price, fundamentals, and news fetches
long_term_scorer.py      Quality, valuation, discount, and technical scoring
sentiment_analyzer.py    Conservative keyword sentiment scoring
long_term_notifier.py    Telegram alert and summary formatting
config/settings.py       Long-term scanner settings and watchlist fallback
```

## Scoring

```text
Quality      50
Valuation    30
Discount     15
Technical     5
----------------
Total       100
```

Ratings are assigned from the final score, current news sentiment, and severe
drawdown checks:

```text
A       85+
B       75-84
C       65-74
Watch   55-64
Avoid   below 55
Blocked severe negative sentiment or severe drawdown
```

## Run Locally

```bash
python -m pip install -r requirements.txt
python main.py
```

If Telegram secrets are not present, alert messages are printed instead of sent.

## GitHub Actions

The workflow in `.github/workflows/run_signal_v11.yml` installs
dependencies, runs a syntax check, executes the scanner, and commits
long-term scan logs back to the repository.

```bash
python main.py
```

It runs on a weekly schedule and manual dispatch.

## Telegram Secrets

```text
V11_TELEGRAM_BOT_TOKEN
V11_TELEGRAM_CHAT_ID
```

## Logs

Each run writes a JSON log to:

```text
logs/long_term/YYYY-MM-DD.json
```
