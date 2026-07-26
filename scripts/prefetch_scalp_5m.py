"""W2 validasyonu icin 5m cache doldurucu (2026-07-24, gecici arac).

scripts.prefetch_data 5m icermez (4h/1h/15m/1d) — scalp config'in (entry=5m)
backtest'i `No cache for <sym> 5m` ile duser. Bu arac 10 core scalp sembolunun
5m verisini ~120 gun cekip ayni cache'e yazar. Zaten cache'li semboller atlanir.

Kullanim (Windows, repo koku, venv aktif):
    python -m scripts.prefetch_scalp_5m
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from data.fetcher import OHLCVFetcher
from data.cache import OHLCVCache

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "TRX/USDT", "LINK/USDT", "AVAX/USDT", "ADA/USDT",
]
TF = "5m"
PERIOD_MS = 120 * 24 * 60 * 60 * 1000  # 120 gun (~34.5k bar/sembol)


def main() -> int:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - PERIOD_MS
    fetcher = OHLCVFetcher()
    cache = OHLCVCache(Path("cache/ohlcv"))
    failed = 0
    for i, symbol in enumerate(SYMBOLS, 1):
        existing = cache.get(symbol, TF)
        if existing is not None:
            print(f"[{i}/{len(SYMBOLS)}] [skip] {symbol} 5m ({len(existing)} bars cached)")
            continue
        print(f"[{i}/{len(SYMBOLS)}] [fetch] {symbol} 5m ...", end="", flush=True)
        try:
            result = fetcher.fetch_ohlcv_range(symbol, TF, start_ms, end_ms, max_gap_pct=5.0)
            cache.put(symbol, TF, result.df)
            print(f" {len(result.df)} bars, {len(result.gaps)} gaps")
        except Exception as e:
            failed += 1
            print(f" FAILED: {type(e).__name__}: {e}")
    print(f"\nDone. failed={failed}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
