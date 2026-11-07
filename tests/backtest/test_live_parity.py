"""Backtest live-parity (spec 2026-11-07 §3.2)."""
from __future__ import annotations

from pathlib import Path
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


def test_prefetch_timeframes_follow_the_live_config():
    from scripts.prefetch_data import parse_args
    a = parse_args(["--config", "configs/config.phase2_1k.yaml", "--symbols", "BTC/USDT,ETH/USDT", "--days", "45"])
    assert a.symbols == ["BTC/USDT", "ETH/USDT"] and a.days == 45
    assert sorted(a.timeframes) == sorted(["12h", "4h", "15m", "1d"])  # mid profile + daily


def test_prefetch_defaults_unchanged():
    from scripts.prefetch_data import SYMBOLS, TIMEFRAMES, parse_args
    a = parse_args([])
    assert a.symbols == SYMBOLS and a.timeframes == TIMEFRAMES and a.days == 365


def test_fetcher_supports_every_profile_timeframe():
    from data.fetcher import OHLCVFetcher
    from data.timeframes import PROFILES, tf_to_minutes
    needed = {tf for chain in PROFILES.values() for tf in chain} | {"1d"}
    assert needed <= set(OHLCVFetcher.tf_minutes)
    assert all(OHLCVFetcher.tf_minutes[tf] == tf_to_minutes(tf) for tf in needed)


def test_reconcile_matches_backtest_trades_on_simulated_time():
    from backtest.compare_live import reconcile
    live = [{"symbol": "BTC/USDT", "direction": "LONG", "opened_at": "2026-10-01T10:00:00+00:00", "pnl": 5.0}]
    bt = [{"symbol": "BTC/USDT", "direction": "LONG", "pnl": 4.0,
           "opened_at": "2026-11-07T12:00:00",            # wall clock of the backtest run
           "sim_opened_at": "2026-10-01T10:15:00+00:00"}]  # bar time
    out = reconcile(live, bt)
    assert out["matched_pairs"] == 1 and out["unmatched_live"] == []


def _cache_with(tmp_path, frames):
    from data.cache import OHLCVCache
    cache = OHLCVCache(tmp_path)
    for (sym, tf), df in frames.items():
        cache.put(sym, tf, df)
    return tmp_path


def _bars(tf_minutes, n):
    end = pd.Timestamp.now(tz="UTC").tz_localize(None).floor("h")  # cache index is tz-naive UTC
    idx = pd.date_range(end=end, periods=n, freq=f"{tf_minutes}min")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)


def test_every_timeframe_gets_the_live_kline_window_before_the_period(tmp_path):
    """Live feeds each TF `kline_limit` bars; the backtest must too, or the
    12h LuxAlgo swing trend never forms (root cause of 0 v2 trades, 2026-11-07)."""
    from backtest.cli import _load_data_for_period
    d = _cache_with(tmp_path, {("X/USDT", "12h"): _bars(720, 1000), ("X/USDT", "15m"): _bars(15, 5000)})
    plain = _load_data_for_period(["X/USDT"], ["12h", "15m"], period_days=10, cache_dir=d,
                                  verify_sha=False)
    data = _load_data_for_period(["X/USDT"], ["12h", "15m"], period_days=10, cache_dir=d,
                                 verify_sha=False, history_bars=500)
    for tf in ("12h", "15m"):  # exactly 500 extra bars of each TF, all before the period
        extra = data["X/USDT"][tf].index.difference(plain["X/USDT"][tf].index)
        assert len(extra) == 500 and extra.max() < plain["X/USDT"][tf].index.min()


def test_cli_runs_with_the_live_window(monkeypatch, tmp_path):
    import backtest.cli as cli
    seen = {}
    monkeypatch.setattr(cli, "_load_data_for_period",
                        lambda *a, **k: seen.update(load=k) or {"BTC/USDT": {}})
    monkeypatch.setattr(cli, "run_backtest", lambda **k: seen.update(run=k) or {"cycles": 1, "skipped_cycles": 0})
    monkeypatch.setattr(cli, "capture_provenance", lambda out: out.mkdir(parents=True, exist_ok=True))
    monkeypatch.chdir(tmp_path)
    import shutil
    (tmp_path / "configs").mkdir()
    shutil.copy(Path(__file__).resolve().parents[2] / "configs" / "config.phase2_1k.yaml", tmp_path / "configs")
    args = type("A", (), {"config": "configs/config.phase2_1k.yaml", "symbol": "BTC/USDT",
                          "period_days": 60, "balance": 2000.0})()
    cli.cmd_single(args)
    window = yaml.safe_load(open(tmp_path / "configs" / "config.phase2_1k.yaml", encoding="utf-8"))[
        "timeframes"].get("kline_limit", 500)
    assert seen["load"]["history_bars"] == window
    assert seen["run"]["warmup_bars"] == window and seen["run"]["smc_window_bars"] == window


def test_daily_frame_is_capped_like_live(monkeypatch, live_cfg):
    """Live passes 100 daily bars (backend/bot_runner.py fetch_ohlcv(sym, "1d", 100))."""
    seen = []

    class _Daily(_Scripted):
        def run_cycle(self, symbol, df_htf, df_mtf, df_entry, df_daily=None, balance=0.0, now=None):
            seen.append(len(df_daily) if df_daily is not None else None)

    monkeypatch.setattr(bt_engine, "SafeOrchestrator", _Daily)
    df = _flat(n=400)
    daily = _flat(n=300)
    daily.index = pd.date_range(end=df.index[-1], periods=300, freq="1D")
    tfs = {live_cfg["timeframes"][k]: df for k in ("htf", "mtf", "entry")}
    tfs["1d"] = daily
    run_backtest(symbols=["BTC/USDT"], data={"BTC/USDT": tfs}, config=live_cfg, initial_balance=2000.0)
    assert seen and max(seen) <= 100
