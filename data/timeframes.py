"""Timeframe utilities shared across data layer and engine."""
from __future__ import annotations


def tf_to_minutes(tf: str) -> int:
    """Normalize a Binance/CCXT TF string to minutes.

    Per spec §6.6: must handle '1m', '15m', '1h', '4h', '1d', '1w'. ValueError on unknown.
    """
    tf_map = {"m": 1, "h": 60, "d": 1440, "w": 10080}
    if not tf or tf[-1] not in tf_map:
        raise ValueError(f"Unsupported timeframe: {tf!r}")
    try:
        n = int(tf[:-1])
    except ValueError as e:
        raise ValueError(f"Bad timeframe number: {tf!r}") from e
    return n * tf_map[tf[-1]]
