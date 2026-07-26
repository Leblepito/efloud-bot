"""Wilder ATR(14) on the entry timeframe.

WHY THIS FILE EXISTS
--------------------
`engine/smc_v2/sl_calc.py::calc_sl` documents its `atr_15m` argument as
"current 15m ATR(14)" and uses it for three separate jobs: the structural
buffer (`sl_atr_buffer * atr`), the minimum stop clamp (`min_sl_atr * atr`)
and the maximum stop clamp (`max_sl_atr * atr`). Until now
`safe_orchestrator` never computed an ATR at all -- it passed the proxy
`max(entry_price * 1%, zone_width)` (BT-21). Measured against the real
Wilder ATR(14) on 15m over the last 90 days the proxy is 2.7x too large on
the portfolio median and 9.2x too large on TRX/USDT, which silently turns
`max_sl_atr: 5.0` from "at most 5 ATRs" into "at most 5% of price" -- a
ceiling so high it never binds. This module supplies the real number so the
operator's existing safety config means what it says.

Wilder's smoothing, not a simple mean: seed with the SMA of the first
`period` true ranges, then ATR_i = (ATR_{i-1} * (period - 1) + TR_i) / period.
`engine/intent.py::_atr` uses a plain mean of the last `period` TRs; that is
a different estimator and is deliberately left alone here -- intent scoring
is a relative-ranking consumer, whereas the SL clamps are absolute-distance
consumers and need the standard definition every ATR-based config number in
this repo was tuned against.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd


def wilder_atr(df: Optional[pd.DataFrame], period: int = 14) -> Optional[float]:
    """Return the latest Wilder ATR(`period`) of `df`, or None if not computable.

    Returns None -- never 0.0 and never a guess -- when the input cannot
    support an honest answer: missing frame, missing OHLC columns, fewer than
    `period + 1` bars, or a non-finite result. None is the caller's signal to
    fall back to its previous behaviour; a 0.0 would be silently accepted by
    `calc_sl` as "no volatility" and collapse every clamp to zero, and a
    guessed value would be worse than the proxy it replaces.
    """
    if df is None or period < 1:
        return None
    try:
        n = len(df)
    except TypeError:
        return None
    # period + 1 bars: the first true range needs a previous close, so a
    # frame of exactly `period` bars yields only `period - 1` TRs and cannot
    # seed the average.
    if n < period + 1:
        return None
    if not {"high", "low", "close"}.issubset(df.columns):
        return None

    high = pd.to_numeric(df["high"], errors="coerce").to_numpy(dtype=float)
    low = pd.to_numeric(df["low"], errors="coerce").to_numpy(dtype=float)
    close = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)

    prev_close = close[:-1]
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - prev_close), np.abs(low[1:] - prev_close)),
    )
    # A single NaN anywhere in the OHLC window poisons every subsequent
    # recursive step, so drop non-finite true ranges rather than propagating.
    tr = tr[np.isfinite(tr)]
    if len(tr) < period:
        return None

    atr = float(tr[:period].mean())
    for x in tr[period:]:
        atr = (atr * (period - 1) + float(x)) / period

    if not math.isfinite(atr) or atr <= 0.0:
        return None
    return atr
