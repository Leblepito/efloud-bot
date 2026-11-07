"""Binance Futures funding fees — 8h cadence application."""
from __future__ import annotations
import pandas as pd


def compute_funding_delta(*, notional: float, direction: str, funding_rate: float) -> float:
    """Return the balance delta (signed) for one funding event.

    Convention: balance_delta = -side_sign × notional × rate
                where side_sign = +1 for LONG, -1 for SHORT.
    """
    side_sign = +1 if direction == "LONG" else -1
    return -side_sign * notional * funding_rate


def funding_events_in_range(funding_df: pd.DataFrame, start_ts, end_ts) -> pd.DataFrame:
    """Return funding events between start_ts (exclusive) and end_ts (inclusive).

    funding_df: index = timestamp, column = funding_rate
    """
    if funding_df.empty:
        return funding_df
    return funding_df[(funding_df.index > start_ts) & (funding_df.index <= end_ts)]
