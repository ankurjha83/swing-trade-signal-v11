# Long-Term Accumulation Scanner

This patch adds a separate long-term accumulation scanner to `swing-trade-signal-v11`.

It does not replace the current swing scanner.

## New files

```text
long_term_fetcher.py
long_term_scorer.py
sentiment_analyzer.py
long_term_notifier.py
main_long_term.py
.github/workflows/long-term-accumulation.yml
README_LONG_TERM.md
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

## Run locally

```bash
python main_long_term.py
```

## Telegram secrets

Uses the same secrets as v11:

```text
V11_TELEGRAM_BOT_TOKEN
V11_TELEGRAM_CHAT_ID
```

## Output

Logs are written to:

```text
logs/long_term/YYYY-MM-DD.json
```
