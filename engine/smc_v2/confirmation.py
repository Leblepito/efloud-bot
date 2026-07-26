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
    last_bar_only: bool = False,
) -> Tuple[bool, Optional[float]]:
    """Detect LTF entry confirmation inside a zone.

    Args:
        df_15m: DataFrame with DatetimeIndex (UTC) and columns
            [open, high, low, close]. Other columns ignored.
        zone: ZoneSpec — the pullback target zone.
        direction: "SHORT" or "LONG"
        since_ts: int (ms epoch) — only consider bars with index timestamp
            strictly > since_ts.
        last_bar_only: W2/C2 (2026-07-18, default False). True iken YALNIZ
            son kapanmış (prior, current) çifti değerlendirilir — onay "şu an
            tazedir" semantiği. Eski davranış since_ts'ten beri TÜM barları
            tarayıp İLK engulfing'de onaylıyordu; onay barı çok eski (stale)
            olabiliyor, canlı emir ise ŞİMDİKİ fiyattan açıldığından onay
            fiyatı ile giriş fiyatı arasında keyfi sapma doğuyordu. False →
            birebir eski davranış; NET-cost gate Windows'ta koşulup operatör
            config'te (`smc_v2.confirm_last_bar_only: true`) açana kadar
            canlı değişmez.

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
    # ms-epoch conversion: per-element Timestamp.timestamp() works reliably
    # across Python versions and tz-aware/naive variants. The vectorized
    # .view('int64') / .astype('int64') idioms are NOT portable on Python
    # 3.14 + tz-aware DatetimeIndex (returns microseconds, not nanoseconds).
    # Loop is O(n) but n is bounded by the LTF DataFrame size (typically
    # < 500 bars per setup), so the Python-loop overhead is negligible.
    timestamps_ms = [int(t.timestamp() * 1000) for t in df_15m.index]

    # W2/C2: last_bar_only → yalnız son kapanmış çift (stale onay biter);
    # default False → tarama aralığı birebir eski (tüm çiftler).
    start_i = len(df_15m) - 1 if last_bar_only else 1
    for i in range(start_i, len(df_15m)):
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
