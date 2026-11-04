"""T-20261104-11: kline WS akışı — ağ yok, sahte combined-stream mesajlarıyla."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from exchange.ws_klines import KlineStream, build_url, to_stream_symbol

T0 = 1_793_823_300_000  # 15m sınırı
TF_MS = 900_000


def _msg(sym="BTCUSDT", tf="15m", t=T0, o=100, h=105, l=99, c=104, x=False, e=None):
    return json.dumps({"stream": f"{sym.lower()}@kline_{tf}", "data": {
        "e": "kline", "E": e or t + 1000, "s": sym,
        "k": {"t": t, "T": t + TF_MS - 1, "s": sym, "i": tf, "o": str(o), "c": str(c),
              "h": str(h), "l": str(l), "v": "10", "x": x}}})


def test_symbol_and_url():
    assert to_stream_symbol("BTC/USDT") == "btcusdt"
    assert to_stream_symbol("BTC/USDT:USDT") == "btcusdt"
    url = build_url(["BTC/USDT", "ETH/USDT"], ["15m", "4h"])
    assert url.startswith("wss://fstream.binance.com/stream?streams=")
    assert url.count("@kline_") == 4 and "ethusdt@kline_4h" in url
    assert build_url(["BTC/USDT"], ["15m"], testnet=True).startswith("wss://stream.binancefuture.com")
    with pytest.raises(ValueError):
        build_url([], ["15m"])


def test_forming_bar_updates_price_but_is_not_closed():
    closed = []
    s = KlineStream(["BTC/USDT"], ["15m"], on_close=lambda *a: closed.append(a))
    assert s.handle_message(_msg(c=104, x=False), recv_ms=1)
    assert s.last_price("BTC/USDT") == 104.0
    assert s.last_closed("BTC/USDT", "15m") is None  # C1: oluşan bar kapanmış sayılmaz
    assert closed == []


def test_close_stored_once_and_callback_fires_once():
    closed = []
    s = KlineStream(["BTC/USDT"], ["15m"], on_close=lambda sym, tf, bar, ms: closed.append((sym, tf, bar["t"], ms)))
    s.handle_message(_msg(x=True), recv_ms=5)
    s.handle_message(_msg(x=True), recv_ms=6)  # yinelenen kapanış
    assert closed == [("BTC/USDT", "15m", T0, 5)]
    assert s.closed_bar("BTC/USDT", "15m", T0)["c"] == 104.0
    assert s.closed_bar("BTC/USDT", "15m", T0 + TF_MS) is None


def test_ignores_garbage_unknown_symbol_and_callback_errors():
    def boom(*a):
        raise RuntimeError("x")
    s = KlineStream(["BTC/USDT"], ["15m"], on_close=boom)
    assert not s.handle_message("not json")
    assert not s.handle_message(json.dumps({"data": {"e": "aggTrade"}}))
    assert not s.handle_message(_msg(sym="DOGEUSDT"))
    assert s.handle_message(_msg(x=True))  # geri çağrı hatası akışı düşürmez


def test_age_and_stats():
    s = KlineStream(["BTC/USDT"], ["15m"])
    assert s.age_ms() is None
    s.handle_message(_msg(), recv_ms=1000)
    assert s.age_ms(now_ms=1500) == 500
    assert s.stats()["streams"] == 1 and s.stats()["messages"] == 1


def _runner(ws, counts=None):
    from backend.bot_runner import BotRunner
    r = BotRunner.__new__(BotRunner)
    r.ws_stream = ws
    r._ws_counts = counts or {"ok": 0, "mismatch": 0, "missing": 0}
    return r


def _df(o=100, h=105, l=99, c=104):
    idx = pd.to_datetime([T0], unit="ms")
    return pd.DataFrame({"open": [o], "high": [h], "low": [l], "close": [c], "volume": [1.0]}, index=idx)


def test_shadow_parity_ok_mismatch_missing():
    s = KlineStream(["BTC/USDT"], ["15m"])
    r = _runner(s)
    r._ws_shadow_check("BTC/USDT", "15m", _df())
    assert r._ws_counts["missing"] == 1
    s.handle_message(_msg(x=True))
    r._ws_shadow_check("BTC/USDT", "15m", _df())
    assert r._ws_counts["ok"] == 1
    r._ws_shadow_check("BTC/USDT", "15m", _df(c=999))
    assert r._ws_counts["mismatch"] == 1


def test_shadow_check_is_noop_without_stream():
    r = _runner(None)
    r._ws_shadow_check("BTC/USDT", "15m", _df())
    assert r._ws_counts == {"ok": 0, "mismatch": 0, "missing": 0}


def test_ws_disabled_by_default():
    from backend.bot_runner import BotRunner
    r = BotRunner.__new__(BotRunner)
    r.ws_stream = None
    r.cfg = {"timeframes": {"entry": "15m", "mtf": "1h", "htf": "4h"}, "exchange": {}}
    r.universe = SimpleNamespace(resolve=lambda: ["BTC/USDT"])
    r._ws_start()
    assert r.ws_stream is None
