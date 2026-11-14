"""T-20261114-01: orchestrator hook for the FVG entry shadow (never touches the live path)."""
import pytest
import numpy as np
import pandas as pd

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2 import fvg_entry as fe


def _df(n=60, start="2026-11-01"):
    idx = pd.date_range(start, periods=n, freq="15min", tz="UTC")
    c = 100 + np.cumsum(np.sin(np.arange(n) / 3.0))
    return pd.DataFrame({"open": c, "high": c + 0.5, "low": c - 0.5, "close": c,
                         "volume": 1.0}, index=idx)


def _orch(mode):
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"smc_v2": {"fvg_entry": mode, "luxalgo": {"enabled": True}},
                   "safety": {"min_sl_atr": 2.0, "max_sl_atr": 5.0},
                   "risk": {"min_rr": 1.8, "sl_atr_buffer": 0.5}}
    return orch


def test_mode_parsing():
    assert _orch("shadow").fvg_entry_mode() == "shadow"
    for raw in ("off", "live", "", None, "SHADOWX"):
        assert _orch(raw).fvg_entry_mode() == "off"
    orch = _orch("off")
    orch.config["smc_v2"].pop("fvg_entry")
    assert orch.fvg_entry_mode() == "off"


def test_off_does_not_build_plans(monkeypatch):
    called = []
    monkeypatch.setattr(fe, "build_plans", lambda *a, **k: called.append(1) or [])
    _orch("off")._fvg_shadow_step("BTC/USDT", _df(), _df(), None, {})
    assert called == []


def test_shadow_builds_plans_and_steps_book(monkeypatch):
    seen = {}

    def fake_build(symbol, lux, bias, bar_ts, atr, safety, min_rr, wick_buffer_r=0.0):
        seen.update(symbol=symbol, n=len(bar_ts), min_rr=min_rr, min_sl=safety.min_sl_atr,
                    buf=safety.sl_atr_buffer)
        return []

    monkeypatch.setattr(fe, "build_plans", fake_build)
    orch = _orch("shadow")
    from engine.smc_v2 import luxalgo as lx
    lux = lx.analyze(_df())
    orch._fvg_shadow_step("BTC/USDT", _df(), _df(40), lux, {})
    assert seen == {"symbol": "BTC/USDT", "n": 60, "min_rr": 1.8, "min_sl": 2.0, "buf": 0.5}
    assert isinstance(orch._fvg_shadow_book, fe.FvgShadowBook)


def test_errors_never_propagate(monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(fe, "build_plans", boom)
    with caplog.at_level("WARNING", logger="efloud.safe_orch"):
        _orch("shadow")._fvg_shadow_step("BTC/USDT", _df(), _df(), None, {})
    assert any("[fvg shadow] error" in r.message for r in caplog.records)


def _capture_builds(monkeypatch):
    calls = []

    def fake_build(symbol, lux, bias, bar_ts, atr, safety, min_rr, wick_buffer_r=0.0, **kw):
        calls.append(kw.get("sl_mode", "atr"))
        return []

    monkeypatch.setattr(fe, "build_plans", fake_build)
    return calls


def _step(orch):
    from engine.smc_v2 import luxalgo as lx
    orch._fvg_shadow_step("BTC/USDT", _df(), _df(40), lx.analyze(_df()), {})


def test_absent_variants_means_only_a(monkeypatch):
    calls = _capture_builds(monkeypatch)
    _step(_orch("shadow"))
    assert calls == ["atr"]


def test_variants_list_builds_both(monkeypatch):
    calls = _capture_builds(monkeypatch)
    orch = _orch("shadow")
    orch.config["smc_v2"]["fvg_entry_sl_variants"] = ["atr", "ob_pct"]
    _step(orch)
    assert calls == ["atr", "ob_pct"]


def test_unknown_variant_ignored_with_warning(monkeypatch, caplog):
    calls = _capture_builds(monkeypatch)
    orch = _orch("shadow")
    orch.config["smc_v2"]["fvg_entry_sl_variants"] = ["atr", "bogus"]
    with caplog.at_level("WARNING", logger="efloud.safe_orch"):
        _step(orch)
    assert calls == ["atr"]
    assert any("bogus" in r.message for r in caplog.records)


def test_book_gets_backtest_cost_config(monkeypatch):
    _capture_builds(monkeypatch)
    orch = _orch("shadow")
    orch.config["backtest"] = {"commission_pct": 0.05, "funding_pct_per_8h": 0.02}
    _step(orch)
    assert orch._fvg_shadow_book.commission_pct == 0.05
    assert orch._fvg_shadow_book.funding_pct_per_8h == 0.02


def test_book_cost_defaults_without_backtest_block(monkeypatch):
    _capture_builds(monkeypatch)
    orch = _orch("shadow")
    _step(orch)
    book = orch._fvg_shadow_book
    assert (book.commission_pct, book.funding_pct_per_8h) == (0.04, 0.01)


@pytest.mark.parametrize("raw,expected", [("atr", ["atr"]), ("ob_pct", ["ob_pct"]), (" ob_pct ", ["ob_pct"])])
def test_scalar_string_variant_is_one_variant(monkeypatch, raw, expected):
    calls = _capture_builds(monkeypatch)
    orch = _orch("shadow")
    orch.config["smc_v2"]["fvg_entry_sl_variants"] = raw
    _step(orch)
    assert calls == expected
