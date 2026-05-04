"""One-time helper: pre-populate the OHLCV cache with 1y of Binance data.

Usage:
    python -m scripts.prefetch_data

Fetches 10 symbols × 4 timeframes from Binance public REST (no auth needed),
writes parquet files under cache/ohlcv/{symbol}/{tf}.parquet.

Tolerates up to 5% gaps for legitimate Binance maintenance windows. The cache
is sha256-verified on read by OHLCVCache; if a parquet file is corrupted or
mismatched, it'll be silently re-fetched on next run.

Wall time: ~10-15 min. Total cache size: ~150-200 MB.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from data.fetcher import OHLCVFetcher
from data.cache import OHLCVCache

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "XRP/USDT", "DOGE/USDT", "SOL/USDT",
    "BNB/USDT", "TRX/USDT", "LINK/USDT", "BCH/USDT", "ADA/USDT",
]
TIMEFRAMES = ["4h", "1h", "15m", "1d"]
PERIOD_MS = 365 * 24 * 60 * 60 * 1000  # 1 year


def main() -> int:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - PERIOD_MS
    fetcher = OHLCVFetcher()
    cache = OHLCVCache(Path("cache/ohlcv"))

    total_jobs = len(SYMBOLS) * len(TIMEFRAMES)
    done = 0
    skipped = 0
    failed = 0

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            done += 1
            existing = cache.get(symbol, tf)
            if existing is not None:
                skipped += 1
                print(f"[{done}/{total_jobs}] [skip] {symbol} {tf} ({len(existing)} bars cached)")
                continue
            print(f"[{done}/{total_jobs}] [fetch] {symbol} {tf} ...", end="", flush=True)
            try:
                # Tolerate up to 5% gaps for legitimate Binance maintenance/late-listings
                result = fetcher.fetch_ohlcv_range(symbol, tf, start_ms, end_ms, max_gap_pct=5.0)
                cache.put(symbol, tf, result.df)
                print(f" {len(result.df)} bars, {len(result.gaps)} gaps")
            except Exception as e:
                failed += 1
                print(f" FAILED: {type(e).__name__}: {e}")

    print(f"\nDone. {done - skipped - failed} fetched, {skipped} skipped, {failed} failed.")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
