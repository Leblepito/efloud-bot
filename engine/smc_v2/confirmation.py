"""LTF entry confirmation for SMC v2.

Per spec §4.1 confirmation.py:
  For SHORT: 15m bearish engulfing close inside zone → confirmed.
  For LONG:  15m bullish engulfing close inside zone → confirmed.

Bearish engulfing: prior bullish bar; current bearish; current body engulfs
prior body (current open >= prior close AND current close <= prior open).
Bullish engulfing: mirror.

Bars at or before `since_ts` are ignored — we only look for confirmations
AFTER the CHoCH trigger that birthed the setup.

Pure function. Returns (confirmed: bool, entry_price: float | None).
"""
from typing import Optional, Tuple

import pandas as pd

from engine.smc_v2.zones import ZoneSpec, is_price_in_zone


def confirm_entry(
    df_15m: pd.DataFrame,
    zone: ZoneSpec,
    direction: str,
    since_ts: int,
) -> Tuple[bool, Optional[float]]:
    """Detect LTF entry confirmation inside a zone.

    Args:
        df_15m: DataFrame with DatetimeIndex (UTC) and columns
            [open, high, low, close]. Other columns ignored.
        zone: ZoneSpec — the pullback target zone.
        direction: "SHORT" or "LONG"
        since_ts: int (ms epoch) — only consider bars with index timestamp
            strictly > since_ts.

    Returns:
        (True, entry_price) on first confirmation found;
        (False, None) otherwise.

    Entry price is the close of the confirming bar.
    """
    if len(df_15m) < 2:
        return False, None

    # Iterate bars in time order, checking each (prior, current) pair.
    opens = df_15m["open"].values
    closes = df_15m["close"].values
    # tz-aware DatetimeIndex.astype('int64') on Python 3.14 returns microseconds
    # for tz-aware indices (vs nanoseconds for tz-naive). Use per-element
    # .timestamp() * 1000 for reliable ms-epoch conversion across versions.
    timestamps_ms = [int(t.timestamp() * 1000) for t in df_15m.index]

    for i in range(1, len(df_15m)):
        cur_ts = timestamps_ms[i]
        if cur_ts <= since_ts:
            continue

        prior_open, prior_close = opens[i - 1], closes[i - 1]
        cur_open, cur_close = opens[i], closes[i]

        if direction == "SHORT":
            # Bearish engulfing: prior bullish; current bearish engulfs body
            prior_bullish = prior_close > prior_open
            cur_bearish = cur_close < cur_open
            engulfs = (cur_open >= prior_close) and (cur_close <= prior_open)
            if prior_bullish and cur_bearish and engulfs:
                if is_price_in_zone(cur_close, zone):
                    return True, float(cur_close)
        else:  # LONG
            # Bullish engulfing: prior bearish; current bullish engulfs body
            prior_bearish = prior_close < prior_open
            cur_bullish = cur_close > cur_open
            engulfs = (cur_open <= prior_close) and (cur_close >= prior_open)
            if prior_bearish and cur_bullish and engulfs:
                if is_price_in_zone(cur_close, zone):
                    return True, float(cur_close)

    return False, None
