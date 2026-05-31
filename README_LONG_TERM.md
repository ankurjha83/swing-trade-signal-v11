# Long-Term Accumulation Scanner

This repo now runs a long-term accumulation scanner instead of the old swing-trading scanner.

## Scoring

```text
Quality      50
Valuation    30
Discount     15
Technical     5
----------------
Total       100
```

## Quality score

```text
Revenue Growth      15
Free Cash Flow      10
Gross Margin        10
ROE                  5
Market Leadership   10
```

## Valuation score

```text
PEG                15
Forward P/E        10
Price/Sales         5
```

## Run locally

```bash
pip install -r requirements.txt
python main.py
```

## GitHub Actions

The workflow runs weekly and can be triggered manually from the Actions tab.

## Telegram secrets

```text
V11_TELEGRAM_BOT_TOKEN
V11_TELEGRAM_CHAT_ID
```

## Logs

```text
logs/long_term/YYYY-MM-DD.json
```
