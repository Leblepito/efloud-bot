"""Backtest live-parity (spec 2026-11-07 §3.2)."""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

import backtest.engine as bt_engine
from backtest.engine import run_backtest
from backtest.intrabar import Bar, resolve_exit
from backtest.slippage import SlippageConfig, adverse_fill
from engine import SafeOrchestrator


def _pos(direction="LONG", sl=90.0, tp1=110.0, tp2=120.0, tp1_hit=False):
    return SimpleNamespace(direction=direction, sl=sl, tp1=tp1, tp2=tp2, tp1_hit=tp1_hit)


class TestResolveExit:
    def test_sl_wins_when_sl_and_tp1_touch_the_same_bar(self):
        assert resolve_exit(_pos(), Bar(100, 111, 89, 100)) == ("SL", 90.0)

    def test_tp1_before_hit(self):
        assert resolve_exit(_pos(), Bar(100, 111, 95, 108)) == ("TP1", 110.0)

    def test_tp2_not_filled_in_the_tp1_bar(self):
        assert resolve_exit(_pos(), Bar(100, 125, 95, 121)) == ("TP1", 110.0)

    def test_tp2_after_tp1_hit(self):
        assert resolve_exit(_pos(sl=100.0, tp1_hit=True), Bar(115, 121, 112, 120)) == ("TP2", 120.0)

    def test_break_even_stop_after_tp1(self):
        assert resolve_exit(_pos(sl=100.0, tp1_hit=True), Bar(105, 106, 99, 100)) == ("SL", 100.0)

    def test_gap_fills_at_open(self):
        assert resolve_exit(_pos(), Bar(85, 86, 80, 82)) == ("SL", 85.0)
        assert resolve_exit(_pos(direction="SHORT", sl=110.0, tp1=90.0, tp2=80.0),
                            Bar(88, 89, 85, 86)) == ("TP1", 88.0)

    def test_single_target_after_tp1_has_no_tp2(self):
        assert resolve_exit(_pos(tp2=None, tp1_hit=True, sl=100.0), Bar(115, 200, 112, 150)) == (None, None)


@pytest.fixture
def live_cfg():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["safety"]["max_holding_hours"] = 0  # max-hold is locked in tests/test_backtest_max_hold.py
    return cfg


def _flat(n=400, highs=None, lows=None, price=100.0):
    idx = pd.date_range("2026-01-01", periods=n, freq="15min")
    df = pd.DataFrame({"open": price, "high": price, "low": price, "close": price,
                       "volume": 1.0}, index=idx)
    for i, v in (highs or {}).items():
        df.iloc[i, df.columns.get_loc("high")] = v
    for i, v in (lows or {}).items():
        df.iloc[i, df.columns.get_loc("low")] = v
    return df


class _Scripted(SafeOrchestrator):
    SCRIPT: list = []
    SEEN: dict = {}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        type(self).SEEN["config"] = self.config
        self._steps = [{"at": at, "fn": fn, "done": False} for at, fn in type(self).SCRIPT]

    def run_cycle(self, symbol, df_htf, df_mtf, df_entry, df_daily=None, balance=0.0, now=None):
        for s in self._steps:
            if not s["done"] and pd.Timestamp(now) >= s["at"]:
                s["fn"](self)
                s["done"] = True


def _run(monkeypatch, cfg, df, script, **kw):
    monkeypatch.setattr(_Scripted, "SCRIPT", script)
    monkeypatch.setattr(bt_engine, "SafeOrchestrator", _Scripted)
    tfs = {cfg["timeframes"][k]: df for k in ("htf", "mtf", "entry")}
    tfs["1d"] = df
    return run_backtest(symbols=["BTC/USDT"], data={"BTC/USDT": tfs}, config=cfg,
                        initial_balance=2000.0, commission_pct=0.0, funding_pct_per_8h=0.0, **kw)


def _open(tp2):
    def fn(orch):
        orch.lifecycle.open_position(symbol="BTC/USDT", direction="LONG", entry_price=100.0,
                                     sl=90.0, tp1=110.0, tp2=tp2, size=1.0)
    return fn


class TestEngineExits:
    def test_dual_target_takes_half_at_tp1_then_rest_at_tp2(self, monkeypatch, live_cfg):
        # after TP1 (bar 300) price holds at 112: above the break-even stop, below TP2
        df = _flat(highs={300: 111.0})
        df.iloc[301:, :4] = 112.0
        df.iloc[330, df.columns.get_loc("high")] = 121.0
        res = _run(monkeypatch, live_cfg, df, [(df.index[210], _open(120.0))])
        t = res["trades"][0]
        assert t["exit_reason"] == "TP2" and t["sl_moved_to_be"] is True
        entry = t["entry"]  # slipped entry
        cfg = SlippageConfig()
        tp1 = adverse_fill(110.0, "LONG", "TP", cfg)
        tp2 = adverse_fill(120.0, "LONG", "TP", cfg)
        assert t["pnl"] == pytest.approx(0.5 * (tp1 - entry) + 0.5 * (tp2 - entry), rel=1e-6)

    def test_dual_target_stops_at_break_even_after_tp1(self, monkeypatch, live_cfg):
        df = _flat(highs={300: 111.0})
        df.iloc[301:, :4] = 105.0  # above the break-even stop until bar 330
        df.iloc[330, df.columns.get_loc("low")] = 95.0
        res = _run(monkeypatch, live_cfg, df, [(df.index[210], _open(120.0))])
        t = res["trades"][0]
        assert t["exit_reason"] == "SL" and t["sl_moved_to_be"] is True
        assert t["pnl"] > 0  # half banked at TP1, rest out near entry

    def test_single_target_closes_everything_at_tp1(self, monkeypatch, live_cfg):
        df = _flat(highs={300: 111.0})
        res = _run(monkeypatch, live_cfg, df, [(df.index[210], _open(None))])
        assert res["trades"][0]["exit_reason"] == "TP1"


class TestLiveConfigAndOffline:
    def test_smc_version_comes_from_the_config(self, monkeypatch, live_cfg):
        assert live_cfg["engine"]["smc_version"] == "v2"
        res = _run(monkeypatch, live_cfg, _flat(), [])
        assert res["smc_version"] == "v2"

    def test_explicit_smc_version_still_overrides(self, monkeypatch, live_cfg):
        assert _run(monkeypatch, live_cfg, _flat(), [], smc_version="v1")["smc_version"] == "v1"

    def test_run_config_disables_agent_team_and_kronos(self, monkeypatch, live_cfg):
        live_cfg.setdefault("agent_team", {})["enabled"] = True
        _run(monkeypatch, live_cfg, _flat(), [])
        seen = _Scripted.SEEN["config"]
        assert seen["agent_team"]["enabled"] is False
        assert seen.get("kronos", {}).get("enabled") is False
        assert live_cfg["agent_team"]["enabled"] is True  # caller's dict untouched

    def test_llm_factory_is_null_during_the_run(self, monkeypatch, live_cfg):
        seen = []

        def probe(orch):
            import engine.agents.llm as llm
            client = llm.make_llm_client({"provider": "openrouter"})
            seen.append((type(client).__name__, client.complete_json("x")))

        import engine.agents.llm as llm
        original = llm.make_llm_client
        df = _flat()
        _run(monkeypatch, live_cfg, df, [(df.index[210], probe)])
        assert seen == [("_NullLLM", {})]
        assert llm.make_llm_client is original  # restored after the run

    def test_live_config_backtest_block_makes_runs_net(self, live_cfg):
        assert live_cfg["backtest"]["commission_pct"] == 0.04
        assert live_cfg["backtest"]["funding_pct_per_8h"] == 0.01


def test_cli_flags_runs_with_too_many_skipped_cycles():
    from backtest.cli import skipped_ratio_exceeded
    assert skipped_ratio_exceeded({"skipped_cycles": 2, "cycles": 100}) is True
    assert skipped_ratio_exceeded({"skipped_cycles": 1, "cycles": 100}) is False
    assert skipped_ratio_exceeded({"skipped_cycles": 0}) is False


def test_engine_reports_cycle_count(monkeypatch, live_cfg):
    res = _run(monkeypatch, live_cfg, _flat(), [])
    assert res["cycles"] > 0


def _grid_one(cfg):
    return {"config_hash": cfg["h"], "value": cfg["h"] * 2}


def test_grid_with_one_worker_runs_in_process(tmp_path, monkeypatch):
    import backtest.grid as grid

    class _Boom:
        def __init__(self, *a, **k):
            raise AssertionError("ProcessPoolExecutor must not be used for workers=1")

    monkeypatch.setattr(grid, "ProcessPoolExecutor", _Boom)
    runner = grid.GridRunner(tmp_path)
    out = runner.run([{"h": 1}, {"h": 2}], run_one_fn=_grid_one, workers=1)
    assert sorted(r["value"] for r in out) == [2, 4]
