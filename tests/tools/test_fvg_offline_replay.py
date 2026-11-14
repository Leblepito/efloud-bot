"""FVG offline replay (ADR-0011 offline gate for the target model): pure helpers + walk-forward."""
import json
import logging

import numpy as np
import pandas as pd
import pytest

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2 import luxalgo as lx
from tools import fvg_offline_replay as rp

H = 3_600_000


def T(net, variant="A", sym="BTC/USDT", ts=0, gross=None, cost=0.1):
    return {"variant": variant, "symbol": sym, "direction": "LONG", "reason": "TP1",
            "gross_r": net + cost if gross is None else gross, "net_r": net, "cost_r": cost,
            "exit_ts": ts}


# ---- exit-line parser -------------------------------------------------------

def test_parse_exit_line_with_variant():
    ln = ("[fvg shadow] exit ETH/USDT SHORT v=B reason=TP2 gross_r=+1.23 net_r=+1.10 "
          "cost_r=0.13 entry=2000.5")
    assert rp.parse_exit_line(ln, exit_ts=42) == {
        "variant": "B", "symbol": "ETH/USDT", "direction": "SHORT", "reason": "TP2",
        "gross_r": 1.23, "net_r": 1.10, "cost_r": 0.13, "exit_ts": 42}


def test_parse_exit_line_without_variant_defaults_to_a():
    ln = "[fvg shadow] exit BTC/USDT LONG reason=SL gross_r=-1.00 net_r=-1.20 cost_r=0.20 entry=1"
    t = rp.parse_exit_line(ln, exit_ts=1)
    assert t["variant"] == "A" and t["net_r"] == -1.20


def test_parse_exit_line_ignores_other_events():
    assert rp.parse_exit_line("[fvg shadow] filled BTC/USDT LONG v=A entry=1 bar_ts=2", 0) is None
    assert rp.parse_exit_line("random log", 0) is None


# ---- metrics ---------------------------------------------------------------

def test_metrics_basic():
    m = rp.compute_metrics([T(2.0, ts=1), T(-1.0, ts=2), T(-1.0, ts=3), T(1.0, ts=4)])
    assert m["n"] == 4
    assert m["win_rate"] == 0.5
    assert m["avg_net_r"] == pytest.approx(0.25)
    assert m["avg_gross_r"] == pytest.approx(0.35)
    assert m["pf_net"] == pytest.approx(3.0 / 2.0)
    assert m["avg_cost_r"] == pytest.approx(0.1)


def test_metrics_max_drawdown_uses_exit_time_order():
    # by exit time: cum 1, 3, 2, 1, 3 -> peak 3, trough 1 => dd 2 (input is out of order)
    trades = [T(-1.0, ts=4), T(1.0, ts=1), T(2.0, ts=2), T(-1.0, ts=3), T(2.0, ts=5)]
    assert rp.compute_metrics(trades)["max_dd_r"] == pytest.approx(2.0)


def test_metrics_empty_and_no_losses():
    e = rp.compute_metrics([])
    assert e["n"] == 0 and e["avg_net_r"] == 0.0 and e["pf_net"] == 0.0 and e["max_dd_r"] == 0.0
    assert rp.compute_metrics([T(1.0), T(2.0)])["pf_net"] == float("inf")


def test_split_is_oos_by_exit_time():
    trades = [T(1, ts=10), T(1, ts=66), T(1, ts=67), T(1, ts=100)]
    is_, oos = rp.split_is_oos(trades, start_ms=0, end_ms=100, is_frac=0.67)
    assert [t["exit_ts"] for t in is_] == [10, 66]
    assert [t["exit_ts"] for t in oos] == [67, 100]


def test_symbol_positive_share():
    trades = [T(1, sym="A"), T(-2, sym="A"), T(1, sym="B"), T(0.5, sym="C")]
    assert rp.symbol_positive_share(trades) == pytest.approx(2 / 3)
    assert rp.symbol_positive_share([]) == 0.0


# ---- verdict (each ADR-0011 criterion fails independently) ------------------

def _good_trades():
    # 120 trades, evenly over [0, 100]; 2 symbols, all positive, OOS PF high
    out = []
    for i in range(120):
        net = 1.0 if i % 3 else -0.5
        out.append(T(net, sym="A" if i % 2 else "B", ts=i * 100 // 120))
    return out


DAY = 86_400_000
LIVE = ["A", "B"]
PASS_V = "PASS (absolute criteria; baseline comparison not run)"


def _ev(trades, symbols=None, live=None, end=None):
    """evaluate() over a 200-day window by default (trade ts are scaled to it)."""
    end = 200 * DAY if end is None else end
    sc = end // 100
    trades = [dict(t, exit_ts=t["exit_ts"] * sc) for t in trades]
    return rp.evaluate(trades, 0, end, 0.67, symbols=LIVE if symbols is None else symbols,
                       live_symbols=LIVE if live is None else live)


def test_verdict_pass():
    r = _ev(_good_trades())
    assert r["verdict"] == PASS_V and r["reasons"] == []


def test_verdict_never_bare_pass():
    assert _ev(_good_trades())["verdict"] != "PASS"


def test_verdict_fails_on_short_window():
    r = _ev(_good_trades(), end=100 * DAY)
    assert r["verdict"] == "FAIL" and "window<180d" in r["reasons"]


def test_verdict_fails_on_symbol_set_mismatch():
    r = _ev(_good_trades(), symbols=["A"])
    assert r["verdict"] == "FAIL" and "symbols != live set" in r["reasons"]
    r = _ev(_good_trades(), live=["A", "B", "C"])
    assert "symbols != live set" in r["reasons"]


def test_verdict_unknown_live_set_fails_closed():
    r = rp.evaluate(_good_trades(), 0, 200 * DAY, 0.67, symbols=LIVE, live_symbols=None)
    assert "symbols != live set" in r["reasons"]


def test_zero_trade_symbol_counts_as_not_positive():
    assert rp.symbol_positive_share([T(1, sym="A")], symbols=["A", "B"]) == 0.5
    assert rp.symbol_positive_share([], symbols=["A"]) == 0.0
    r = _ev(_good_trades(), symbols=LIVE + ["Z1", "Z2"], live=LIVE + ["Z1", "Z2"])
    assert any("symbols NET-positive" in x for x in r["reasons"])


def test_verdict_fails_on_n():
    r = _ev(_good_trades()[:60])
    assert r["verdict"] == "FAIL" and any("n=" in x for x in r["reasons"])


def test_verdict_fails_on_is_negative():
    tr = [dict(t, net_r=-0.2 if t["exit_ts"] < 60 else t["net_r"]) for t in _good_trades()]
    r = _ev(tr)
    assert r["verdict"] == "FAIL" and any(x.startswith("IS avg") for x in r["reasons"])


def test_verdict_fails_on_oos_negative_and_pf():
    tr = [dict(t, net_r=-0.2 if t["exit_ts"] >= 67 else t["net_r"]) for t in _good_trades()]
    r = _ev(tr)
    assert any(x.startswith("OOS avg") for x in r["reasons"])
    assert any(x.startswith("OOS PF") for x in r["reasons"])


def test_verdict_fails_on_oos_pf_only():
    # alternating +1.0 / -0.9: avg > 0 everywhere but PF ~1.11 < 1.30; both symbols positive
    tr = [T(1.0 if i % 2 else -0.9, sym="A" if i % 4 < 2 else "B", ts=i * 100 // 120)
          for i in range(120)]
    r = _ev(tr)
    assert any(x.startswith("OOS PF") for x in r["reasons"])
    assert not any(x.startswith("OOS avg") or x.startswith("IS avg") for x in r["reasons"])


def test_verdict_fails_on_symbol_share():
    tr = [dict(t, symbol=f"S{i % 5}") for i, t in enumerate(_good_trades())]
    for t in tr:
        if t["symbol"] in ("S0", "S1", "S2"):
            t["net_r"] = -abs(t["net_r"]) - 0.01   # 3/5 symbols negative; share 0.4
    # keep pooled avg positive enough to isolate the share criterion
    for t in tr:
        if t["symbol"] in ("S3", "S4"):
            t["net_r"] = 20.0
    r = _ev(tr)
    assert r["verdict"] == "FAIL" and any("symbols" in x for x in r["reasons"])
    assert not any(x.startswith("OOS avg") or x.startswith("IS avg") for x in r["reasons"])


def test_evaluate_all_groups_variants():
    tr = [T(1, variant="A", ts=1), T(1, variant="B", ts=2)]
    res = rp.evaluate_all(tr, 0, 100, 0.67, symbols=LIVE, live_symbols=LIVE)
    assert set(res) == {"A", "B"} and res["A"]["all"]["n"] == 1


# ---- look-ahead guard + history -------------------------------------------

def test_mtf_window_never_uses_unclosed_bar():
    opens = np.array([0, 4 * H, 8 * H, 12 * H], dtype="int64")
    # entry bar closes exactly at 8h: the 4h bar opened at 4h closes at 8h -> usable; the 8h one not
    assert rp.usable_mtf_count(opens, 4 * H, entry_close_ms=8 * H) == 2
    assert rp.usable_mtf_count(opens, 4 * H, entry_close_ms=8 * H - 1) == 1
    assert rp.usable_mtf_count(opens, 4 * H, entry_close_ms=12 * H + 4 * H) == 4
    assert rp.usable_mtf_count(opens, 4 * H, entry_close_ms=0) == 0


def _frame(start, n, tf_min, price=100.0):
    idx = pd.date_range(start, periods=n, freq=f"{tf_min}min", tz="UTC")
    c = price + np.cumsum(np.sin(np.arange(n) / 5.0))
    return pd.DataFrame({"open": c, "high": c + 0.5, "low": c - 0.5, "close": c, "volume": 1.0},
                        index=idx)


CFG = {"timeframes": {"profile": "custom", "entry": "15m", "mtf": "1h", "htf": "4h",
                      "kline_limit": 60},
       "smc_v2": {"fvg_entry": "shadow", "fvg_entry_sl_variants": ["atr", "ob_pct"],
                  "luxalgo": {"enabled": True, "pullback_timeout_bars": 12,
                              "tp_wick_buffer_r": 0.15, "swing_length": 10, "internal_length": 3}},
       "safety": {"min_sl_atr": 0.1, "max_sl_atr": 5.0},
       "risk": {"min_rr": 0.8, "sl_atr_buffer": 0.5}}


def test_missing_mtf_history_raises_named_error():
    ent = _frame("2026-11-01", 400, 15)
    mtf = _frame("2026-11-03", 100, 60)        # starts after the window start -> < 60 bars before
    start = int(ent.index[200].timestamp() * 1000)
    with pytest.raises(rp.HistoryError, match=r"BTC/USDT.*1h"):
        rp.replay_symbol("BTC/USDT", ent, mtf, CFG, start, int(ent.index[-1].timestamp() * 1000) + 900_000)


def test_missing_entry_history_raises_named_error():
    ent = _frame("2026-11-01", 400, 15)
    mtf = _frame("2026-10-01", 1000, 60)
    start = int(ent.index[10].timestamp() * 1000)
    with pytest.raises(rp.HistoryError, match=r"BTC/USDT.*15m"):
        rp.replay_symbol("BTC/USDT", ent, mtf, CFG, start, int(ent.index[-1].timestamp() * 1000) + 900_000)


def test_short_cache_end_raises_instead_of_silent_short_run():
    ent, mtf = _walk_frames()
    s, e = _window(ent)
    with pytest.raises(rp.HistoryError, match=r"BTC/USDT.*15m.*window end"):
        rp.replay_symbol("BTC/USDT", ent, mtf, CFG, s, e + 15 * 60_000)


def test_lagging_mtf_raises():
    ent, mtf = _walk_frames()
    s, e = _window(ent)
    with pytest.raises(rp.HistoryError, match=r"BTC/USDT.*1h.*lag"):
        rp.replay_symbol("BTC/USDT", ent, mtf.iloc[:-5], CFG, s, e)


def test_run_requires_end():
    with pytest.raises(SystemExit):
        rp.main(["run", "--out", "x"])


# ---- synthetic end-to-end ---------------------------------------------------

def _walk_frames(seed=2, n=1000):  # seed picked so the fixture yields setups and closed trades
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-10-01", periods=n, freq="15min", tz="UTC")
    c = 100 + np.cumsum(rng.normal(0, 0.6, n)) + 8 * np.sin(np.arange(n) / 40.0)
    o = np.r_[c[0], c[:-1]]
    hi = np.maximum(o, c) + np.abs(rng.normal(0, 0.3, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, 0.3, n))
    ent = pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": 1.0}, index=idx)
    mtf = ent.resample("1h").agg({"open": "first", "high": "max", "low": "min",
                                  "close": "last", "volume": "sum"})
    return ent, mtf


def _window(ent):
    return int(ent.index[300].timestamp() * 1000), int(ent.index[-1].timestamp() * 1000) + 900_000


def test_replay_is_deterministic_and_produces_trades():
    ent, mtf = _walk_frames()
    s, e = _window(ent)
    a = rp.replay_symbol("BTC/USDT", ent, mtf, CFG, s, e)
    b = rp.replay_symbol("BTC/USDT", ent, mtf, CFG, s, e)
    assert a.lines == b.lines and a.trades == b.trades
    assert any(" setup+ " in ln for _, ln in a.lines)
    assert a.trades, "synthetic fixture must close at least one shadow trade"
    assert {t["variant"] for t in a.trades} <= {"A", "B"}


def test_replay_matches_orchestrator_shadow_step_line_for_line():
    """Parity: the replay and SafeOrchestrator._fvg_shadow_step emit identical `[fvg shadow]` lines."""
    ent, mtf = _walk_frames()
    s, e = _window(ent)
    res = rp.replay_symbol("BTC/USDT", ent, mtf, CFG, s, e)

    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = json.loads(json.dumps(CFG))
    lux_cfg = orch.config["smc_v2"]["luxalgo"]
    got = []

    class _Capture(logging.Handler):
        def emit(self, record):
            got.append(record.getMessage())

    h = _Capture()
    lg = logging.getLogger("efloud.safe_orch")
    lg.addHandler(h)
    old = lg.level
    lg.setLevel(logging.INFO)
    try:
        k = CFG["timeframes"]["kline_limit"] - 1   # live drops the forming bar
        for i in range(len(ent)):
            t_open = int(ent.index[i].timestamp() * 1000)
            if t_open < s or t_open + 900_000 > e:
                continue
            close_ms = t_open + 900_000
            de = ent.iloc[max(0, i + 1 - k): i + 1]
            n_m = int((mtf.index.as_unit("ms").asi8 + 3_600_000 <= close_ms).sum())
            dm = mtf.iloc[max(0, n_m - k): n_m]
            lux = lx.analyze(de, lx.LuxConfig.from_dict(lux_cfg))
            orch._fvg_shadow_step("BTC/USDT", de, dm, lux, lux_cfg)
    finally:
        lg.removeHandler(h)
        lg.setLevel(old)
    assert got, "no shadow lines produced"
    assert got == [ln for _, ln in res.lines]


def test_merge_recomputes_from_trades(tmp_path):
    a = {"meta": {"git_sha": "x", "start_ms": 0, "end_ms": 100, "symbols": ["A"], "is_frac": 0.67,
                  "variants_tried": 2}, "trades": [T(1, sym="A", ts=10)]}
    b = {"meta": {"git_sha": "x", "start_ms": 0, "end_ms": 100, "symbols": ["B"], "is_frac": 0.67,
                  "variants_tried": 2}, "trades": [T(-1, sym="B", ts=20)]}
    pa, pb = tmp_path / "a.json", tmp_path / "b.json"
    pa.write_text(json.dumps(a))
    pb.write_text(json.dumps(b))
    rep = rp.merge_reports([pa, pb])
    assert rep["meta"]["symbols"] == ["A", "B"]
    assert rep["results"]["A"]["all"]["n"] == 2
    assert "n=2" in " ".join(rep["results"]["A"]["reasons"])


def _rep(sym, **over):
    meta = {"git_sha": "x", "start_ms": 0, "end_ms": 100, "symbols": [sym], "is_frac": 0.67,
            "variants_tried": 2, "cost": "c", "config": "cfg", "profile": "p"}
    meta.update(over)
    return {"meta": meta, "trades": [T(1, sym=sym, ts=10)]}


def _write(tmp_path, *reps):
    paths = []
    for i, r in enumerate(reps):
        p = tmp_path / f"r{i}.json"
        p.write_text(json.dumps(r))
        paths.append(p)
    return paths


@pytest.mark.parametrize("field,val", [("start_ms", 1), ("end_ms", 99), ("is_frac", 0.5),
                                       ("cost", "d"), ("config", "other"), ("profile", "q"),
                                       ("variants_tried", 3)])
def test_merge_rejects_inconsistent_inputs(tmp_path, field, val):
    paths = _write(tmp_path, _rep("A"), _rep("B", **{field: val}))
    with pytest.raises(rp.MergeError, match=field):
        rp.merge_reports(paths)


def test_merge_rejects_duplicate_symbol(tmp_path):
    paths = _write(tmp_path, _rep("A"), _rep("A"))
    with pytest.raises(rp.MergeError, match="A"):
        rp.merge_reports(paths)


def test_merge_cli_exits_nonzero_with_message(tmp_path, capsys):
    paths = _write(tmp_path, _rep("A"), _rep("A"))
    rc = rp.main(["merge", "--inputs", *map(str, paths), "--out", str(tmp_path / "o")])
    assert rc != 0 and "A" in capsys.readouterr().err
