"""Fetch closed 15m klines from the Binance USD-M public API into a CSV.

usage: python -I scripts/pine_lab_fetch_klines.py SYMBOL START_MS OUT.csv
  e.g. python -I scripts/pine_lab_fetch_klines.py BTCUSDT 1782864000000 data/lab/BTC_15m.csv

Reads from START_MS up to now, drops the still-forming bar, writes
`timestamp,open,high,low,close,volume` (public endpoint, no credentials).
"""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.request

INTERVAL_MS = 15 * 60 * 1000


def fetch(sym: str, start_ms: int) -> list[list]:
    rows: list[list] = []
    t = start_ms
    now = int(time.time() * 1000)
    while t < now:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=15m&startTime={t}&limit=1500"
        data = json.load(urllib.request.urlopen(url, timeout=30))
        if not data:
            break
        rows += data
        t = data[-1][0] + INTERVAL_MS
        time.sleep(0.2)
    return [r for r in rows if r[6] < now]  # drop the forming bar


def main(argv: list[str]) -> None:
    sym, start_ms, out = argv[0], int(argv[1]), argv[2]
    closed = fetch(sym, start_ms)
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for r in closed:
            w.writerow([r[0], r[1], r[2], r[3], r[4], r[5]])
    print(sym, len(closed), closed[0][0], closed[-1][0])


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(sys.argv[1:])
