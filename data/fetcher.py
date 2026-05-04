"""Binance public OHLCV fetcher via CCXT — range fetch + gap detection."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple
import logging

import pandas as pd

from exchange import BinanceClient

log = logging.getLogger("efloud.data.fetcher")


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


@dataclass
class FetchResult:
    df: pd.DataFrame
    gaps: List[Tuple[int, int]] = field(default_factory=list)  # (start_ms, end_ms) of missing windows


class OHLCVFetcher:
    """Public Binance OHLCV via CCXT (no auth)."""

    tf_minutes = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}

    def __init__(self):
        # Public klines need no auth. CCXT only validates creds on private endpoints.
        self.client = BinanceClient(api_key="", api_secret="", testnet=False, market_type="futures")

    def fetch_ohlcv_range(self, symbol: str, tf: str, start_ms: int, end_ms: int,
                            limit: int = 1500, max_gap_pct: float = 1.0) -> FetchResult:
        """Fetch OHLCV in range; return df + gap list. Raises ValueError if total gap exceeds max_gap_pct."""
        if tf not in self.tf_minutes:
            raise ValueError(f"Unsupported tf: {tf!r}")
        tf_ms = self.tf_minutes[tf] * 60 * 1000
        all_bars: list = []
        cursor = start_ms
        while cursor < end_ms:
            batch = self.client.exchange.fetch_ohlcv(symbol, tf, since=cursor, limit=limit)
            if not batch:
                break
            all_bars.extend(batch)
            last_ts = batch[-1][0]
            if last_ts <= cursor:
                break  # safety: no progress
            cursor = last_ts + tf_ms

        # Dedupe + sort
        seen: dict = {}
        for bar in all_bars:
            seen[bar[0]] = bar
        sorted_bars = sorted(seen.values(), key=lambda b: b[0])

        # Build df
        df = pd.DataFrame(sorted_bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)

        # Gap detection
        expected = pd.date_range(
            start=pd.to_datetime(start_ms, unit="ms"),
            end=pd.to_datetime(end_ms - tf_ms, unit="ms"),
            freq=f"{self.tf_minutes[tf]}min",
        )
        gaps: list = []
        if len(df) < len(expected):
            present = set(df.index)
            in_gap = False
            gap_start = None
            for ts in expected:
                if ts not in present:
                    if not in_gap:
                        gap_start = int(ts.timestamp() * 1000)
                        in_gap = True
                else:
                    if in_gap:
                        gap_end = int(ts.timestamp() * 1000)
                        gaps.append((gap_start, gap_end))
                        in_gap = False
            if in_gap:
                gaps.append((gap_start, end_ms))

        # max_gap_pct refusal (per spec §6.6)
        total_gap_ms = sum(end - start for start, end in gaps)
        period_ms = end_ms - start_ms
        gap_pct = (total_gap_ms / period_ms * 100) if period_ms else 0
        if gap_pct > max_gap_pct:
            raise ValueError(
                f"Fetch incomplete: {gap_pct:.2f}% gap exceeds max {max_gap_pct}% "
                f"({len(gaps)} gap windows)"
            )

        return FetchResult(df=df, gaps=gaps)

    def fetch_funding_rates(self, symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        """Fetch funding rate history (8h cadence)."""
        all_rows: list = []
        cursor = start_ms
        while cursor < end_ms:
            batch = self.client.exchange.fetch_funding_rate_history(symbol, since=cursor, limit=1000)
            if not batch:
                break
            all_rows.extend(batch)
            last_ts = batch[-1].get("timestamp", cursor)
            if last_ts <= cursor:
                break
            cursor = last_ts + 1
        rows = [{"ts": r["timestamp"], "funding_rate": r["fundingRate"]} for r in all_rows]
        df = pd.DataFrame(rows)
        if not df.empty:
            df["ts"] = pd.to_datetime(df["ts"], unit="ms")
            df.set_index("ts", inplace=True)
            df = df[~df.index.duplicated()].sort_index()
        return df
