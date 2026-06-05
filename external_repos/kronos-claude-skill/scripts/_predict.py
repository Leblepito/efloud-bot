#!/usr/bin/env python3
"""Inner predict runner. Runs inside the skill's venv.

Assumes torch + transformers + yfinance are installed and the Kronos repo
is on disk at $KRONOS_REPO. Outputs markdown to stdout for Claude to display.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

KRONOS_REPO = Path(os.environ.get("KRONOS_REPO", Path(__file__).resolve().parent.parent / "_kronos"))
sys.path.insert(0, str(KRONOS_REPO))

import yfinance as yf

try:
    from model import Kronos, KronosTokenizer, KronosPredictor
except Exception as e:
    print(f"ERROR loading Kronos model module: {e}", file=sys.stderr)
    print(f"Expected Kronos repo at: {KRONOS_REPO}", file=sys.stderr)
    print("If this is the first run after a Kronos upstream change, try:", file=sys.stderr)
    print("  rm -rf ~/.claude/skills/kronos/_kronos && retry", file=sys.stderr)
    sys.exit(2)


TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base"
MODEL_ID = "NeoQuasar/Kronos-small"


def fetch_ohlcv(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Pull OHLCV from yfinance and normalize column names."""
    print(f"[kronos] fetching {ticker} ({period} of {interval} candles) from yfinance...", file=sys.stderr)
    data = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    if data.empty:
        raise SystemExit(
            f"No data for {ticker} period={period} interval={interval}. "
            f"Check the symbol on Yahoo Finance. Crypto must use -USD suffix (e.g. BTC-USD)."
        )
    history = data[["Open", "High", "Low", "Close", "Volume"]].copy()
    history.columns = ["open", "high", "low", "close", "volume"]
    history.index.name = "timestamps"
    return history


def build_future_timestamps(last_ts: pd.Timestamp, interval: str, pred_len: int) -> pd.DatetimeIndex:
    """Build a future-timestamp index matching the interval cadence."""
    if interval in ("1d", "1day"):
        delta = pd.Timedelta(days=1)
    elif interval in ("1wk", "1week"):
        delta = pd.Timedelta(weeks=1)
    elif interval in ("1mo", "1month"):
        delta = pd.DateOffset(months=1)
    elif interval.endswith("h"):
        hours = int(interval.rstrip("h"))
        delta = pd.Timedelta(hours=hours)
    elif interval.endswith("m"):
        mins = int(interval.rstrip("m"))
        delta = pd.Timedelta(minutes=mins)
    else:
        delta = pd.Timedelta(days=1)
    return pd.DatetimeIndex([last_ts + delta * (i + 1) for i in range(pred_len)])


def load_predictor() -> KronosPredictor:
    print(f"[kronos] loading model {MODEL_ID} (may download from HF on first run)...", file=sys.stderr)
    tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_ID)
    model = Kronos.from_pretrained(MODEL_ID)
    predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=512)
    return predictor


def format_output(
    ticker: str,
    history: pd.DataFrame,
    forecast: pd.DataFrame,
    pred_len: int,
    interval: str,
) -> str:
    last_close = float(history["close"].iloc[-1])
    pred_close = float(forecast["close"].iloc[-1])
    pct_change = ((pred_close - last_close) / last_close) * 100.0

    pred_high = float(forecast["close"].max())
    pred_low = float(forecast["close"].min())
    band_width_pct = ((pred_high - pred_low) / last_close) * 100.0

    if pct_change > 0.25:
        direction = "UP"
    elif pct_change < -0.25:
        direction = "DOWN"
    else:
        direction = "FLAT"

    if band_width_pct < 5:
        confidence = "NARROW (signal worth investigating)"
    elif band_width_pct < 10:
        confidence = "MODERATE (mixed signal, check other timeframes)"
    else:
        confidence = "WIDE (treat as noise, model is hedging)"

    last_ts = history.index[-1].strftime("%Y-%m-%d %H:%M")

    output = []
    output.append(f"# Kronos Prediction: {ticker}")
    output.append("")
    output.append(f"**Last close:** ${last_close:,.2f} ({last_ts})")
    output.append(f"**Predicted close after {pred_len} x {interval} candles:** ${pred_close:,.2f}")
    output.append(f"**Direction:** {direction} ({pct_change:+.2f}%)")
    output.append(f"**Confidence band:** {confidence}")
    output.append(f"**Forecast range:** ${pred_low:,.2f} - ${pred_high:,.2f} (±{band_width_pct:.2f}% of last close)")
    output.append("")
    output.append("## Interpretation rules")
    output.append("")
    output.append("- **NARROW band (<5%):** model is confident across its forward distribution. Treat as a signal worth investigating. Look for confirmation on a second timeframe before acting.")
    output.append("- **MODERATE band (5-10%):** mixed signal. Useful for context, not for decisions on its own.")
    output.append("- **WIDE band (>10%):** model is hedging. Treat the prediction as noise. Do not act on it.")
    output.append("")
    output.append("## What this is NOT")
    output.append("")
    output.append("This is a probability distribution over likely price paths, not a price target.")
    output.append("Not financial advice. Stocks carry real risk. Run on multiple timeframes")
    output.append("(daily AND weekly, for example) and pair with the fundamental side before")
    output.append("giving any signal weight.")
    output.append("")
    output.append("## Full forecast trajectory")
    output.append("")
    output.append("```")
    output.append(forecast.round(2).to_string())
    output.append("```")
    output.append("")
    output.append("---")
    output.append("")
    output.append("*Model: Kronos-small (NeoQuasar/Kronos-small) trained on 12B candlesticks from 45 exchanges. Skill: ~/.claude/skills/kronos/*")
    return "\n".join(output)


def load_history(ticker: str, period: str, interval: str, df_path: str | None = None) -> pd.DataFrame:
    """Load OHLCV data. If df_path is provided, reads the parquet file,
    ensures proper columns, index name, and skips yfinance fetching.
    """
    if df_path:
        print(f"[kronos] reading injected dataframe from {df_path}...", file=sys.stderr)
        history = pd.read_parquet(df_path)
        # Ensure exact columns and order required
        history = history[["open", "high", "low", "close", "volume"]].copy()
        history.index.name = "timestamps"
        return history
    return fetch_ohlcv(ticker, period, interval)


def main() -> int:
    if len(sys.argv) < 5:
        print("Usage: _predict.py <TICKER> <period> <interval> <pred_len> [--df-path <path>]", file=sys.stderr)
        return 1

    ticker = sys.argv[1]
    period = sys.argv[2]
    interval = sys.argv[3]
    pred_len = int(sys.argv[4])

    df_path = None
    if "--df-path" in sys.argv:
        try:
            idx = sys.argv.index("--df-path")
            if idx + 1 < len(sys.argv):
                df_path = sys.argv[idx + 1]
        except ValueError:
            pass

    history = load_history(ticker, period, interval, df_path)
    predictor = load_predictor()

    last_ts = history.index[-1]
    x_timestamp = pd.Series(history.index)
    y_timestamp = pd.Series(build_future_timestamps(last_ts, interval, pred_len))

    print(f"[kronos] predicting {pred_len} forward candles for {ticker}...", file=sys.stderr)
    forecast = predictor.predict(
        df=history,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=pred_len,
        T=1.0,
        top_p=0.9,
        sample_count=1,
    )

    print(format_output(ticker, history, forecast, pred_len, interval))
    return 0


if __name__ == "__main__":
    sys.exit(main())
