"""Pine lab parity harness tests (spec §7.2) — synthetic data only, no network."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import pine_lab_parity as plp  # noqa: E402


def _df_from_closes(closes, wick=0.2, start="2026-01-01"):
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]]
    highs = np.maximum(opens, closes) + wick
    lows = np.minimum(opens, closes) - wick
    idx = pd.date_range(start, periods=len(closes), freq="15min")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": 1.0}, index=idx)


def _zigzag(points, steps=6):
    out = []
    for a, b in zip(points[:-1], points[1:]):
        out += list(np.linspace(a, b, steps, endpoint=False))
    out.append(points[-1])
    return out


def _trend_df(n_cycles=20):
    pts = [100, 110, 104, 108, 98, 103, 92, 97, 88, 99, 94, 112, 105, 120, 113, 128]
    closes = []
    base = 0.0
    for _ in range(n_cycles):
        closes += [p + base for p in _zigzag(pts)]
        base += 5.0
    return _df_from_closes(closes)


def _lab_config():
    cfg = plp.load_config(ROOT / "configs" / "config.phase2_1k.yaml")
    lux = cfg["smc_v2"]["luxalgo"]
    lux.update({"swing_length": 4, "internal_length": 2, "eq_length": 2, "atr_length": 10,
                "require_premium_discount": False, "min_confluence": 0, "pullback_timeout_bars": 60})
    cfg["risk"]["recency_bars"] = 120
    cfg["smc_v2"]["po3_gate"] = False
    cfg["smc_v2"]["max_entry_dist_atr"] = 0.0
    cfg["smc_v2"]["max_zone_overshoot_atr"] = 999.0
    cfg["safety"]["min_sl_atr"] = 0.5
    return cfg


def test_load_ohlcv_csv_tradingview_and_binance_layouts(tmp_path):
    tv = tmp_path / "tv.csv"
    tv.write_text("time,open,high,low,close,Volume\n1700000000,1,2,0.5,1.5,10\n1700000900,1.5,2.5,1,2,11\n")
    df = plp.load_ohlcv_csv(tv)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.tz is None and df.index[0] == pd.Timestamp("2023-11-14 22:13:20")
    bn = tmp_path / "bn.csv"
    bn.write_text("timestamp,open,high,low,close,volume\n1700000000000,1,2,0.5,1.5,10\n")
    assert plp.load_ohlcv_csv(bn).index[0] == df.index[0]


def test_resample_htf_drops_incomplete_last_bin_and_checks_alignment():
    df = _df_from_closes(list(range(100, 100 + 8 * 48 + 7)))        # 8 full 12h bins + 7 bars
    htf = plp.resample_htf(df, "12h")
    assert len(htf) == 8                                            # the 9th (partial) 12h bin is dropped
    assert htf.index[0] == pd.Timestamp("2026-01-01 00:00")
    assert htf["high"].iloc[0] == df["high"].iloc[:48].max()
    bad = df.copy()
    bad.index = bad.index + pd.Timedelta(minutes=7)
    with pytest.raises(ValueError):
        plp.resample_htf(bad, "12h")


def test_replay_emits_and_confirms_on_trending_zigzag():
    df = _trend_df()
    rows, stats = plp.replay(df, _lab_config(), window=200, htf_bias_override="BULL")
    assert stats["bars"] == len(df) - 199
    assert stats["emitted"] >= 1
    assert all(r["direction"] == "LONG" for r in rows)
    assert all(set(r) == set(plp.ROW_FIELDS) for r in rows)
    confirmed = [r for r in rows if r["drop_reason"] == ""]
    assert confirmed, "expected at least one confirmed setup with SL/TP"
    for r in confirmed:
        assert r["sl"] < r["entry"] < r["tp1"]
        assert r["atr_source"] == "WILDER14"
        assert r["tp1_source"] != ""
        assert r["confirmed_ts"] >= r["trigger_bar_ts"]
        assert isinstance(r["fill"], float)


def test_replay_reads_recency_from_risk_block_like_live_orchestrator():
    cfg = plp.load_config(ROOT / "configs" / "config.phase2_1k.yaml")
    assert cfg["risk"]["recency_bars"] == 168 and "recency_bars" not in cfg.get("smc_v2", {})
    assert plp.recency_bars(cfg) == 168
    assert plp.recency_bars({"smc_v2": {"recency_bars": 99}}) == 40


def test_guard_rejected_flag_marks_floor_widened_stops(tmp_path):
    cfg = _lab_config()
    cfg["safety"]["min_sl_atr"] = 2.0
    df = _trend_df(4)
    orch = plp.LabOrchestrator(cfg, plp.new_store(cfg, tmp_path), tmp_path)
    from engine.smc_v2.setup_state import SetupCandidate
    from engine.smc_v2.zones import ZoneSpec
    flags = set()
    rng = np.random.default_rng(1)
    for _ in range(300):
        entry = float(rng.uniform(0.05, 120000))
        d = df * (entry / 100.0)
        atr = plp.wilder_atr(d, period=14)
        zone = ZoneSpec(low=entry - 0.2 * atr, high=entry, source="OB")
        cand = SetupCandidate(symbol="LAB/USDT", direction="LONG", trigger_bar_ts=1, trigger_price=entry,
                              htf_bias="BULL", target_zone=zone, htf_swing_anchor=zone.low, bars_waited=0,
                              state="CONFIRMED", confluence_score=1,
                              reasons=["LUX swing BOS BULL", "", "confluence=SWING_OB"])
        orch._place_v2_entry_order(cand, current_price=entry, entry_price=entry, df_entry=d)
        rec = orch.records[-1]
        if rec["drop_reason"] == "":
            assert rec["atr_source"] == "WILDER14"
            flags.add(rec["python_guard_rejected"])
    assert flags == {True, False}, "the B2 float flag must fire for some floor-widened stops and not others"


def test_write_rows_roundtrip(tmp_path):
    rows = [{k: "" for k in plp.ROW_FIELDS}]
    rows[0].update(symbol="LAB/USDT", direction="LONG", trigger_bar_ts=5, entry=1.0, sl=0.9, tp1=1.2)
    out = tmp_path / "py.csv"
    plp.write_rows(rows, out)
    back = plp.read_rows(out)
    assert back[0]["trigger_bar_ts"] == 5 and back[0]["entry"] == 1.0 and back[0]["drop_reason"] == ""


def _tv_csv(tmp_path, rows):
    p = tmp_path / "trades.csv"
    hdr = "Trade #,Type,Date and time,Signal,Price USDT,Position size (qty),Net P&L USDT\n"
    p.write_text(hdr + "".join(rows))
    return p


def test_load_tv_trades_and_parse_signal(tmp_path):
    p = _tv_csv(tmp_path, [
        "1,Entry long,2026-03-01 10:00,B|trig=1772359200000|sl=99|tp1=103|tp2=na,100,5,\n",
        "1,Exit long,2026-03-01 12:00,TP1/SL,103,5,15\n",
    ])
    t = plp.load_tv_trades(p)
    assert list(t.columns) == ["trade", "type", "time", "signal", "price", "qty", "pnl"]
    e = plp.tv_entries(t)
    assert e == [{"direction": "LONG", "trig": 1772359200000, "entry": 100.0, "entry_ref": None, "sl": 99.0,
                  "tp1": 103.0, "tp2": None, "time": pd.Timestamp("2026-03-01 10:00"), "variant": "B"}]
    p2 = _tv_csv(tmp_path, ["1,Entry long,2026-03-01 10:00,B|trig=1|entry=99.5|sl=99|tp1=103|tp2=na,100,5,\n"])
    assert plp.tv_entries(plp.load_tv_trades(p2))[0]["entry_ref"] == 99.5


def test_compare_matches_python_only_pine_only_and_tolerances():
    py = [
        {"direction": "LONG", "trigger_bar_ts": 1, "entry": 100.0, "fill": 100.0, "sl": 98.0, "tp1": 104.0, "tp2": "", "drop_reason": "", "python_guard_rejected": False, "confirmed_ts": 1},
        {"direction": "LONG", "trigger_bar_ts": 2, "entry": 100.0, "fill": 100.0, "sl": 98.0, "tp1": 104.0, "tp2": "", "drop_reason": "", "python_guard_rejected": True, "confirmed_ts": 2},
        {"direction": "SHORT", "trigger_bar_ts": 3, "entry": 100.0, "fill": 100.0, "sl": 102.0, "tp1": 96.0, "tp2": "", "drop_reason": "SL_TOO_FAR", "python_guard_rejected": False, "confirmed_ts": 3},
    ]
    entries = [
        {"direction": "LONG", "trig": 1, "entry": 100.04, "entry_ref": 100.0, "sl": 98.0, "tp1": 104.0, "tp2": None, "time": pd.Timestamp("2026-01-01")},
        {"direction": "LONG", "trig": 2, "entry": 100.0, "entry_ref": 100.0, "sl": 98.5, "tp1": 104.0, "tp2": None, "time": pd.Timestamp("2026-01-01")},
        {"direction": "SHORT", "trig": 9, "entry": 50.0, "entry_ref": 50.0, "sl": 51.0, "tp1": 48.0, "tp2": None, "time": pd.Timestamp("2026-01-01")},
    ]
    res = plp.compare(py, entries)
    assert res["python_entries"] == 2 and res["matched"] == 2
    assert res["python_only"] == [] and [e["trig"] for e in res["pine_only"]] == [9]
    assert [m["trig"] for m in res["level_mismatch"]] == [2]           # sl 98.5 vs 98.0 > 0.1 %
    assert res["guard_rejected"] == 1
    assert res["match_rate"] == 1.0 and res["passed"] is False         # level mismatch fails the gate
    entries[0]["entry"] = 100.2                                       # > 0.05 % → unmatched
    res2 = plp.compare(py, entries)
    assert res2["matched"] == 2 and res2["python_only"] == []
    assert [m["trig"] for m in res2["level_mismatch"]] == [1, 2]
    assert "entry" in res2["level_mismatch"][0]["levels"]
    assert "match" in plp.format_compare(res2)


def _py_row(trig, entry=100.0, confirmed=None, drop="", fill=None):
    return {"direction": "LONG", "trigger_bar_ts": trig, "entry": entry, "fill": entry if fill is None else fill, "sl": 98.0, "tp1": 104.0, "tp2": "",
            "drop_reason": drop, "python_guard_rejected": False, "confirmed_ts": trig if confirmed is None else confirmed}


def _tv_entry(trig, entry=100.0, time="2026-01-01", entry_ref=None):
    return {"direction": "LONG", "trig": trig, "entry": entry, "entry_ref": entry if entry_ref is None else entry_ref, "sl": 98.0, "tp1": 104.0, "tp2": None,
            "time": pd.Timestamp(time)}


def test_compare_pass_path_and_gate_boundary():
    py = [_py_row(i) for i in range(1, 21)]
    tv = [_tv_entry(i) for i in range(1, 21)]
    res = plp.compare(py, tv)
    assert res["passed"] is True and res["match_rate"] == 1.0
    res = plp.compare(py, tv[:19])
    assert res["match_rate"] == 0.95 and res["passed"] is True
    assert plp.compare(py, tv[:18])["passed"] is False
    assert plp.compare(py, tv[:19], gate=0.96)["passed"] is False


def test_compare_duplicate_keys_pair_in_time_order():
    py = [_py_row(7, 100.0, confirmed=10), _py_row(7, 110.0, confirmed=20)]
    t1, t2, t3 = "2026-01-01 00:00", "2026-01-01 01:00", "2026-01-01 02:00"
    tv = [_tv_entry(7, 110.0, t2), _tv_entry(7, 100.0, t1)]
    res = plp.compare(py, tv)
    assert res["matched"] == 2 and res["level_mismatch"] == []
    res = plp.compare(py, [_tv_entry(7, 100.0, t1)])
    assert res["matched"] == 1 and [r["confirmed_ts"] for r in res["python_only"]] == [20]
    res = plp.compare(py, tv + [_tv_entry(7, 120.0, t3)])
    assert res["matched"] == 2 and [e["entry"] for e in res["pine_only"]] == [120.0]


def test_compare_excludes_python_rows_inside_an_open_tv_trade():
    py = [_py_row(10), _py_row(20), _py_row(30)]
    res = plp.compare(py, [_tv_entry(10)], intervals=[(10, 25, False)])
    assert [r["confirmed_ts"] for r in res["blocked_by_position"]] == [20]
    assert [r["confirmed_ts"] for r in res["python_only"]] == [30]
    assert res["python_entries"] == 2 and res["matched"] == 1
    assert "blocked" in plp.format_compare(res)


def test_compare_uses_fill_price_not_engulfing_close():
    py = [_py_row(1, entry=100.0, fill=101.0)]
    res = plp.compare(py, [_tv_entry(1, entry=101.0, entry_ref=100.0)])
    assert res["matched"] == 1 and res["level_mismatch"] == []
    res = plp.compare(py, [_tv_entry(1, entry=100.0, entry_ref=100.0)])
    assert res["matched"] == 1 and "entry" in res["level_mismatch"][0]["levels"]
    res = plp.compare(py, [_tv_entry(1, entry=101.0, entry_ref=101.0)])
    assert res["level_mismatch"][0]["levels"] == ["entry_ref"]


def test_compare_without_python_entries_fails_gate():
    py = [_py_row(1, drop="SL_TOO_FAR"), _py_row(2, drop="RR")]
    tv = [_tv_entry(1), _tv_entry(2)]
    res = plp.compare(py, tv)
    assert res["python_entries"] == 0 and res["match_rate"] == 0.0 and res["passed"] is False
    assert res["pine_only"] == tv


def test_cli_compare_reports_missing_signal_column(tmp_path, capsys):
    p = tmp_path / "py.csv"
    row = {k: "" for k in plp.ROW_FIELDS}
    row.update(symbol="LAB/USDT", direction="LONG", trigger_bar_ts=5, entry=1.0, sl=0.9, tp1=1.2, confirmed_ts=5)
    plp.write_rows([row], p)
    tv = tmp_path / "trades.csv"
    tv.write_text("Trade #,Type,Date and time,Price USDT,Position size (qty),Net P&L USDT\n"
                  "1,Entry long,2026-03-01 10:00,100,5,\n")
    assert plp.main(["compare", "--python", str(p), "--tv", str(tv)]) == 2
    assert "Signal" in capsys.readouterr().err


def test_score_trades_r_math_with_partial_tp1(tmp_path):
    p = _tv_csv(tmp_path, [
        "1,Entry long,2026-03-01 10:00,B|trig=1|sl=98|tp1=104|tp2=108,100,10,\n",
        "1,Exit long,2026-03-01 12:00,TP1|sl=98,104,5,20\n",
        "1,Exit long,2026-03-01 14:00,TP2|sl=98,108,5,40\n",      # +60 on risk 2×10=20 → +3.0 R
        "2,Entry short,2026-03-02 10:00,B|trig=2|sl=102|tp1=96|tp2=na,100,10,\n",
        "2,Exit short,2026-03-02 12:00,SL|sl=102,102,10,-20\n",   # −1.0 R
        "3,Entry long,2026-03-03 10:00,B|trig=3|sl=99|tp1=103|tp2=na,100,10,\n",
        "3,Exit long,2026-03-03 12:00,MAX_HOLD,99.5,10,-5\n",  # −0.5 R
        "4,Entry long,2026-03-04 10:00,B|T3|trig=4|ote=1,100,10,\n",
        "4,Exit long,2026-03-04 12:00,TP1|sl=98,104,10,40\n",   # +2.0 R, SL recovered from the exit comment
    ])
    s = plp.score_trades(plp.load_tv_trades(p))
    assert s["n"] == 4
    assert s["total_r"] == pytest.approx(3.5)
    assert s["avg_r"] == pytest.approx(0.875)
    assert s["pf"] == pytest.approx(5.0 / 1.5)
    assert s["max_dd_r"] == pytest.approx(1.5)                 # peak +3.0 → trough +1.5
    assert s["win_rate"] == pytest.approx(0.5)


def test_score_merges_split_partial_trades(tmp_path):
    p = _tv_csv(tmp_path, [
        "1,Entry long,2026-03-01 10:00,B|trig=5|sl=98|tp1=104|tp2=108,100,5,\n",
        "1,Exit long,2026-03-01 12:00,TP1|sl=98,104,5,20\n",
        "2,Entry long,2026-03-01 10:00,B|trig=5|sl=98|tp1=104|tp2=108,100,5,\n",
        "2,Exit long,2026-03-01 14:00,TP2|sl=98,108,5,40\n",
    ])
    t = plp.load_tv_trades(p)
    s = plp.score_trades(t)
    assert s["n"] == 1 and s["total_r"] == pytest.approx(3.0)        # 60 / (2 x 10)
    ms = lambda x: int(pd.Timestamp(x).value // 1_000_000)
    assert plp.tv_intervals(t) == [(ms("2026-03-01 10:00"), ms("2026-03-01 14:00"), False)]


def test_blocked_by_position_boundaries(tmp_path):
    ms = lambda x: int(pd.Timestamp(x).value // 1_000_000)
    e, x = ms("2026-03-01 10:00"), ms("2026-03-01 14:00")
    sl = plp.tv_intervals(plp.load_tv_trades(_tv_csv(tmp_path, [
        "1,Entry long,2026-03-01 10:00,B|trig=1|sl=98|tp1=104|tp2=na,100,10,\n",
        "1,Exit long,2026-03-01 14:00,SL|sl=98,98,10,-20\n"])))
    assert sl == [(e, x, False)]
    mh = plp.tv_intervals(plp.load_tv_trades(_tv_csv(tmp_path, [
        "1,Entry long,2026-03-01 10:00,B|trig=1|sl=98|tp1=104|tp2=na,100,10,\n",
        "1,Exit long,2026-03-01 14:00,MAX_HOLD,99,10,-10\n"])))
    assert mh == [(e, x, True)]

    def blocked(iv, cts):
        res = plp.compare([_py_row(cts, confirmed=cts)], [], intervals=iv)
        return len(res["blocked_by_position"]) == 1

    mid = (e + x) // 2
    assert not blocked(sl, e) and not blocked(mh, e)     # entry bound is exclusive
    assert not blocked(sl, x)                            # SL exit fills intrabar: next entry possible
    assert blocked(mh, x)                                # MAX_HOLD closes at the close: still held
    assert blocked(sl, mid) and blocked(mh, mid)


def test_decide_applies_all_four_criteria():
    base = {"n": 60, "total_r": 10.0, "avg_r": 0.17, "pf": 1.3, "max_dd_r": 5.0}
    win = {"n": 55, "total_r": 14.0, "avg_r": 0.25, "pf": 1.5, "max_dd_r": 5.5}
    assert plp.decide(base, win) == (True, [])
    ok, why = plp.decide(base, {**win, "n": 49})
    assert ok is False and any("n=" in w for w in why)
    ok, why = plp.decide(base, {**win, "max_dd_r": 6.1})
    assert ok is False and any("drawdown" in w for w in why)
    ok, why = plp.decide(base, {**win, "total_r": 10.0})
    assert ok is False
    ok, why = plp.decide(base, {"n": 1, "total_r": 0.0, "avg_r": 0.0, "pf": 0.0, "max_dd_r": 99.0})
    assert len(why) == 4 and all(w.isascii() for w in why)
