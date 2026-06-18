# backend/tests/test_resolve_signals.py
from engine.signal_ledger import SignalRecord
from scripts.routines.resolve_signals import resolve_signal

def _rec(direction="LONG", entry=100.0, sl=98.0, tp1=104.0, tp2=None,
         exit_model="single_target", rr1=2.0, rr2=None, ts=0):
    return SignalRecord(signal_id="x", ts_emitted=ts, brk_ts=ts, symbol="T/USDT",
        direction=direction, emitted_entry=entry, sl=sl, tp1=tp1, tp2=tp2,
        confluence=70, rr1=rr1, rr2=rr2, timeframe="15m", htf_bias="LONG",
        regime="trend", reasons=[], was_tradeable=True, entry_is_retrace=False,
        exit_model=exit_model)

def _bar(ts, o, h, l, c):
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c}

def test_long_tp1_first():
    rec = _rec()
    bars = [_bar(0,100,100,100,100), _bar(60000,100,101,99,100), _bar(120000,100,104,100,104)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert out["outcome"] == "tp1" and out["hypo_r_gross"] > 0

def test_long_sl_first():
    rec = _rec()
    bars = [_bar(0,100,100,100,100), _bar(60000,100,100,97,98)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert out["outcome"] == "sl" and out["hypo_r_gross"] == -1.0

def test_long_same_bar_both_is_conservative_sl():
    rec = _rec()
    bars = [_bar(0,100,100,100,100), _bar(60000,100,104,97,100)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert out["outcome"] == "sl"

def test_short_same_bar_both_is_conservative_sl():
    rec = _rec(direction="SHORT", entry=100.0, sl=102.0, tp1=96.0)
    bars = [_bar(0,100,100,100,100), _bar(60000,100,102,96,100)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert out["outcome"] == "sl"

def test_tp1_and_tp2_no_sl_credits_tp1_first():
    rec = _rec(tp2=106.0, exit_model="partial_ladder", rr2=3.0)
    bars = [_bar(0,100,100,100,100), _bar(60000,100,106,100,105)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert out["outcome"] in ("tp1", "tp2")
    assert out["hypo_r_gross"] > 0

def test_unfilled_when_confirmation_never_occurs_v2():
    rec = _rec()
    bars = [_bar(i*60000,100,100.1,99.9,100) for i in range(20)]
    out = resolve_signal(rec, bars, smc_version="v2", max_horizon_hours=48)
    assert out["status"] == "unfilled"

def test_v2_positive_fill_then_tp():
    # ADDED (plan-review correction #8): v2 happy-path — flat, then an engulfing
    # confirmation bar within fill_window, then later TP. prod runs v2.
    rec = _rec(ts=0)
    bars = [
        _bar(0,100,100,100,100),           # emission bar (ignored)
        _bar(60000,100,100.2,99.8,100),    # prev bar for engulf reference
        _bar(120000,100,102.5,100,102.2),  # engulfing confirmation (close > prev high, body>0)
        _bar(180000,102.2,104,102,104),    # later TP1 (104)
    ]
    out = resolve_signal(rec, bars, smc_version="v2", max_horizon_hours=48)
    assert out["status"] == "resolved"
    assert out["fill_price"] == 102.2           # confirmation bar CLOSE
    assert out["bars_to_fill"] == 2             # post-emission 1-based: bar at ts=60000 is i=0, bar at ts=120000 is i=1 -> i+1=2
    assert out["outcome"] == "tp1"

def test_v2_race_starts_strictly_after_fill_bar():
    # ADDED: a TP/SL touch ON the confirmation bar itself must NOT resolve;
    # the race begins on the bar AFTER fill.
    rec = _rec(ts=0)
    bars = [
        _bar(0,100,100,100,100),
        _bar(60000,100,100.2,99.8,100),
        _bar(120000,100,104,100,102.2),    # confirmation bar ALSO spikes to tp1 high — must be ignored for the race
        _bar(180000,102.2,102.5,102,102.3) # after-fill: neither tp nor sl -> not resolved on this alone
    ]
    out = resolve_signal(rec, bars, smc_version="v2", max_horizon_hours=48)
    # fill happened at bar idx 3 (close 102.2); race over remaining bars hits neither -> timeout
    assert out["status"] == "timeout"
    assert out["fill_price"] == 102.2

def test_timeout_when_neither_hit():
    rec = _rec()
    bars = [_bar(i*60000,100,101,99,100) for i in range(5)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=0.001)
    assert out["status"] == "timeout" and out["outcome"] == "timeout"

def test_lookahead_ignores_pre_fill_bars():
    rec = _rec(ts=120000)
    bars = [_bar(0,100,104,100,104), _bar(60000,100,104,100,104),
            _bar(120000,100,100,100,100), _bar(180000,100,100,97,98)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert out["outcome"] == "sl"

def test_partial_ladder_blended_r_tp1_then_breakeven():
    rec = _rec(tp2=106.0, exit_model="partial_ladder", rr1=2.0, rr2=3.0)
    bars = [_bar(0,100,100,100,100), _bar(60000,100,104,100,104), _bar(120000,104,104,100,100)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert 0.4 < out["hypo_r_gross"] < 1.1
