"""Backtest analysis memo (item 12): exact-match reuse, isolation, and restore."""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from backtest.memo import FrameMemo, memoized_analysis


def _df(close=100.0, n=5):
    idx = pd.date_range("2026-10-01", periods=n, freq="12h")
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 1.0}, index=idx)


def _counting():
    calls = []

    def fn(df, *args, **kwargs):
        calls.append(1)
        return {"last": float(df["close"].iloc[-1]), "items": [1, 2], "args": args}
    return fn, calls


def test_identical_frame_is_computed_once():
    fn, calls = _counting()
    memo = FrameMemo(fn)
    a = memo(_df())
    b = memo(_df())                      # a new but identical frame object
    assert a == b and len(calls) == 1 and memo.hits == 1


def test_a_hit_is_isolated_from_caller_mutation():
    fn, _ = _counting()
    memo = FrameMemo(fn)
    first = memo(_df())
    first["items"].append(99)            # caller mutates its result
    second = memo(_df())
    second["items"].append(7)
    assert memo(_df())["items"] == [1, 2]


def test_same_index_different_prices_is_a_miss():
    """Portfolio: symbols share timestamps; equal keys must not share results."""
    fn, calls = _counting()
    memo = FrameMemo(fn)
    assert memo(_df(close=100.0))["last"] == 100.0
    assert memo(_df(close=200.0))["last"] == 200.0
    assert len(calls) == 2 and memo.hits == 0


def test_different_arguments_are_a_miss():
    fn, calls = _counting()
    memo = FrameMemo(fn)
    memo(_df(), "cfgA")
    memo(_df(), "cfgB")
    assert len(calls) == 2


def test_a_frame_edited_in_place_after_the_call_does_not_poison_the_cache():
    fn, calls = _counting()
    memo = FrameMemo(fn)
    df = _df()
    memo(df)
    df["close"] = 500.0                  # caller edits the frame it passed in
    assert memo(_df())["last"] == 100.0 and len(calls) == 1


def test_cache_is_bounded():
    fn, _ = _counting()
    memo = FrameMemo(fn, max_entries=2)
    for n in (3, 4, 5):
        memo(_df(n=n))
    assert len(memo._cache) == 2


def test_context_patches_and_restores_both_functions():
    import engine.smc_v2.luxalgo as lux

    class _Smc:
        def analyze(self, df):
            return "real"

    orch = SimpleNamespace(smc=_Smc())
    original_lux = lux.analyze
    with memoized_analysis(orch):
        assert isinstance(orch.smc.analyze, FrameMemo)
        assert isinstance(lux.analyze, FrameMemo)
    assert "analyze" not in vars(orch.smc) and orch.smc.analyze(None) == "real"
    assert lux.analyze is original_lux


def test_context_restores_on_error():
    import engine.smc_v2.luxalgo as lux

    original_lux = lux.analyze
    orch = SimpleNamespace(smc=SimpleNamespace(analyze=lambda df: "x"))
    with pytest.raises(RuntimeError):
        with memoized_analysis(orch):
            raise RuntimeError("boom")
    assert lux.analyze is original_lux and not isinstance(orch.smc.analyze, FrameMemo)


@pytest.mark.slow
def test_memo_on_and_off_give_byte_identical_backtests(monkeypatch):
    """The real engine with and without the memo must produce the same result."""
    import contextlib
    import json

    import numpy as np
    import yaml

    import backtest.engine as bt_engine
    import backtest.memo as memo_mod

    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    rng = np.random.default_rng(7)

    def frame(freq, periods, scale):
        idx = pd.date_range("2025-01-01", periods=periods, freq=freq, tz="UTC")
        trend = np.linspace(0, 15, periods) + 10 * np.sin(np.linspace(0, 12, periods))
        close = 100 + trend + np.cumsum(rng.normal(0, scale, periods))
        return pd.DataFrame({"open": close, "high": close + 0.6, "low": close - 0.6,
                             "close": close, "volume": 1000.0}, index=idx)

    n = 2600  # 27 days of 15m: enough closed 12h/4h bars for real cycles
    data = {"ETH/USDT": {"15m": frame("15min", n, 0.15), "4h": frame("4h", n // 16 + 1, 0.6),
                         "12h": frame("12h", n // 48 + 2, 1.0), "1d": frame("1D", n // 96 + 2, 1.5)}}

    hits = []
    real = memo_mod.FrameMemo.__call__

    def counting(self, df, *a, **k):
        before = self.hits
        out = real(self, df, *a, **k)
        hits.append(self.hits - before)
        return out

    def run():
        res = bt_engine.run_backtest(symbols=["ETH/USDT"], data=data, config=cfg,
                                     initial_balance=2000.0, warmup_bars=n - 200,
                                     smc_window_bars=750)
        wall = {"id", "opened_at", "closed_at"}
        res["trades"] = [{k: v for k, v in t.items() if k not in wall} for t in res["trades"]]
        return json.dumps(res, sort_keys=True, default=str)

    monkeypatch.setattr(memo_mod.FrameMemo, "__call__", counting)
    with_memo = run()
    monkeypatch.setattr(bt_engine, "memoized_analysis", lambda orch: contextlib.nullcontext())
    without_memo = run()

    assert json.loads(with_memo)["cycles"] > 0
    assert sum(hits) > 0, "the memo was never exercised"
    assert with_memo == without_memo
