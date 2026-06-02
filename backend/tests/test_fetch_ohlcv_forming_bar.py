"""C1 regression: fetch_ohlcv must drop the still-forming (unclosed) last bar.

CCXT's fetch_ohlcv returns the current, in-progress candle as the final row.
The whole SMC engine (CHoCH/BOS via close crossings, entry price, SL local-low,
ATR) read `.iloc[-1]` on that forming bar, so a signal could appear and vanish
intra-bar (repaint) — and this was invisible in backtest, which feeds only
closed bars. Fix: drop the last row when its close time (open + tf) is still in
the future, at the single exchange choke point so live + CLI inherit it.

Interaction note: after the drop the freshest last-CLOSED bar's open time is in
[tf, 2·tf) old; the orchestrator validates freshness with tolerance_factor=2.5,
so delta < 2·tf < 2.5·tf — freshness still passes (asserted below).
"""
from __future__ import annotations

import time

import pytest

from engine.safety.guard import validate_kline_freshness
from exchange import BinanceClient

_TF = "15m"
_TF_MS = 15 * 60 * 1000


def _client_with_raw(monkeypatch, raw):
    client = BinanceClient(testnet=True, market_type="futures")
    monkeypatch.setattr(client.exchange, "fetch_ohlcv", lambda *a, **k: [list(r) for r in raw])
    return client


def _bars(opens):
    # [open_ms, o, h, l, c, v] — flat OHLC is fine for these structural tests.
    return [[o, 100.0, 101.0, 99.0, 100.0, 1.0] for o in opens]


def test_drops_forming_last_bar(monkeypatch):
    now_ms = int(time.time() * 1000)
    forming_open = now_ms - _TF_MS // 3          # open+tf in the future → forming
    opens = [forming_open - k * _TF_MS for k in range(4, 0, -1)] + [forming_open]
    client = _client_with_raw(monkeypatch, _bars(opens))

    df = client.fetch_ohlcv("BTC/USDT", _TF, limit=500)

    assert len(df) == len(opens) - 1, "the forming last bar must be dropped"
    last_open_ms = int(df.index[-1].value // 1_000_000)
    assert last_open_ms == opens[-2], "last row must be the most recent CLOSED bar"
    assert last_open_ms + _TF_MS <= now_ms, "remaining last bar must be closed"


def test_keeps_already_closed_last_bar(monkeypatch):
    now_ms = int(time.time() * 1000)
    # Exchange already returns only closed bars (last open+tf < now) → keep all.
    last_open = now_ms - 2 * _TF_MS
    opens = [last_open - k * _TF_MS for k in range(4, 0, -1)] + [last_open]
    client = _client_with_raw(monkeypatch, _bars(opens))

    df = client.fetch_ohlcv("BTC/USDT", _TF, limit=500)

    assert len(df) == len(opens), "an already-closed last bar must be kept"


def test_freshness_passes_after_dropping_forming_bar(monkeypatch):
    now_ms = int(time.time() * 1000)
    forming_open = now_ms - _TF_MS // 3
    opens = [forming_open - k * _TF_MS for k in range(4, 0, -1)] + [forming_open]
    client = _client_with_raw(monkeypatch, _bars(opens))

    df = client.fetch_ohlcv("BTC/USDT", _TF, limit=500)

    # Must NOT raise StaleDataError with the orchestrator's tolerance_factor=2.5.
    assert validate_kline_freshness(df, _TF, tolerance_factor=2.5) is True
