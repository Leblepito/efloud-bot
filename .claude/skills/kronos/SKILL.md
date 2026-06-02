---
name: kronos
description: Run hedge-fund-grade technical analysis on any stock or crypto ticker using the Kronos open source foundation model (trained on 12B candlesticks from 45 exchanges). Pass a ticker, get back a price prediction with confidence interval in plain English. Triggers on "/kronos", "run kronos on X", "kronos analysis", "predict X with kronos", "technical analysis on X", "what does kronos say about X".
argument-hint: "<TICKER> [period] [interval] [pred_len]"
---

# Kronos Technical Analysis Skill

The same kind of price prediction AI Wall Street pays millions for, packaged so you can run it from any Claude conversation with one command.

**This is a research tool, not financial advice.** It outputs a forward probability distribution with a confidence interval. Wide interval = noise. Narrow interval across multiple timeframes = signal worth investigating.

---

## How to invoke

When the user asks for technical analysis on a ticker, calls the skill explicitly, or asks Kronos for a prediction, run the script and present the output verbatim. Do not editorialize the prediction. Add a "Not financial advice" reminder if the user is making decisions based on the output.

```bash
python3 .claude/skills/kronos/scripts/run_kronos.py <TICKER> [period] [interval] [pred_len]
```

**Arguments:**
- `TICKER` (required) — Stock symbol (AAPL, NVDA, TSLA) or crypto pair (BTC-USD, ETH-USD)
- `period` (default `6mo`) — How much history to use. yfinance values: `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `max`
- `interval` (default `1d`) — Candle size. yfinance values: `1d`, `1h`, `4h`, `1wk`, `1mo` (intraday limited to last 60 days)
- `pred_len` (default `24`) — How many future candles to forecast

**Examples:**
- `python3 .claude/skills/kronos/scripts/run_kronos.py AAPL` — 6 months of daily candles, 24-day forecast
- `python3 .claude/skills/kronos/scripts/run_kronos.py BTC-USD 3mo 4h 48` — 3 months of 4-hour candles, 48-period forecast
- `python3 .claude/skills/kronos/scripts/run_kronos.py NVDA 1y 1d 30` — 1 year of daily, 30-day forecast

---

## First run

First time the skill runs, it auto-installs everything. This takes 3-7 minutes and prints status to stderr. You will see:

```
First run: cloning Kronos from GitHub...
First run: creating Python venv...
First run: installing dependencies (torch, transformers, yfinance, pandas)...
First run: downloading Kronos model weights from HuggingFace (~500MB)...
```

Subsequent runs are fast (~5-15 seconds depending on ticker and `pred_len`).

If first run fails, see [Troubleshooting](#troubleshooting) below.

---

## What the output looks like

The script returns markdown with:
1. Last close price + date
2. Predicted close after `pred_len` periods
3. Direction (UP / DOWN / FLAT) with percentage change
4. Confidence band (narrow = signal, wide = noise)
5. Interpretation rules
6. Full forecast trajectory as a table

Present this to the user as-is. Do not invent a prediction or modify the numbers.

---

## When to recommend a wider stack

If the user is making a real investment decision based on the output, recommend they pair this with:
1. Their own ticker-specific Claude Project containing the company's filings (5y annuals, recent 10-Qs, earnings call transcripts)
2. A bull case and bear case memo written by Claude using only the documents in the Project
3. A weekly run of `/kronos` across their watchlist
4. A quarterly refresh of the memos when earnings drop

This is the full two-layer stack: Kronos for the chart side, Claude for the fundamentals side.

Link to the full walkthrough: `https://ai-basic-series.vercel.app/run-kronos-walkthrough`

---

## What this is NOT

- Not a trading bot. Does not place orders.
- Not a price target. Outputs a probability distribution.
- Not financial advice. Research tool only.
- Not a license to skip risk management.

When the user asks "should I buy this," redirect to the two-layer stack and remind them this is research, not a recommendation.

---

## Troubleshooting

**"git: command not found"** — Install Xcode command line tools: `xcode-select --install`

**"No data for TICKER"** — yfinance does not have data for that symbol. Check the symbol on Yahoo Finance directly. Crypto must use `-USD` suffix (BTC-USD, not BTC).

**"ModuleNotFoundError: model"** — The venv install failed. Delete `.claude/skills/kronos/.venv` and `.claude/skills/kronos/_kronos` and run again.

**Out of memory on a big ticker** — Reduce `period` (use `3mo` instead of `2y`) or reduce `pred_len`.

**Slow first prediction (>10 min)** — Model weights are downloading from HuggingFace. This only happens once.
