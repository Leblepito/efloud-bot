# Kronos — Claude Skill

The same kind of price prediction AI Wall Street pays millions for, packaged as a Claude skill you can invoke in plain English.

> **Not financial advice.** This is a research tool. Kronos outputs a probability distribution with a confidence interval, not a price target. Use it as one input into a research process. Stocks carry real risk.

## What it does

Run hedge-fund-grade technical analysis on any stock or crypto ticker from any Claude conversation.

```
You: run kronos on AAPL
Claude: [invokes the skill, returns prediction + confidence interval + interpretation]
```

Under the hood: the skill pulls recent OHLCV via yfinance, runs the Kronos foundation model (trained on 12B candlesticks from 45 exchanges) for a forward prediction, and returns formatted markdown Claude reads back to you in plain English.

## Install

One-time. First run takes 3-7 minutes to clone the Kronos repo, create a venv, and install torch + transformers + yfinance.

```bash
# The skill auto-installs on first invocation. You can also pre-install:
python3 .claude/skills/kronos/scripts/run_kronos.py AAPL
```

## Usage

From any Claude conversation:

- `run kronos on AAPL` — 6 months of daily candles, 24-day forecast (defaults)
- `kronos BTC-USD 3mo 4h 48` — 3 months of 4-hour candles, 48-period forecast
- `predict NVDA with kronos for the next 30 days` — claude infers args

Or invoke the script directly:

```bash
python3 .claude/skills/kronos/scripts/run_kronos.py <TICKER> [period] [interval] [pred_len]
```

## What the output looks like

```
# Kronos Prediction: AAPL

**Last close:** $XXX.XX (YYYY-MM-DD)
**Predicted close after 24 x 1d candles:** $XXX.XX
**Direction:** UP (+X.XX%)
**Confidence band:** NARROW (signal worth investigating)
**Forecast range:** $XXX.XX - $XXX.XX (±X.XX% of last close)

## Interpretation rules
- NARROW band (<5%): model is confident...
- MODERATE band (5-10%): mixed signal...
- WIDE band (>10%): treat as noise...
```

## Full walkthrough

Live walkthrough with copy-paste prompts, the two-layer stack (Kronos + Claude for filings), and the weekly research routine:

**https://ai-basic-series.vercel.app/run-kronos-walkthrough**

## Credits

- **Kronos foundation model:** [shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos) by Shiyu Chen (MIT licensed, trained on 12B candlesticks from 45 exchanges)
- **Market data:** [yfinance](https://github.com/ranaroussi/yfinance) (free, Yahoo Finance under the hood)
- **Skill packaging:** Cooper Simson / Actionable AI

## What this is NOT

- Not a trading bot
- Not a price target
- Not financial advice
- Not a license to skip risk management
