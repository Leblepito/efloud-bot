"""Tests for scripts/desk/plan_replay.py — Monte Carlo plan replay for 24/7 crypto.

Port of day-trader-skill's trader-timemachine (MIT) to Binance USDT-M bars:
UTC time-of-day slots instead of NYSE sessions, a fixed horizon instead of the
close, and fees folded into R (efloud's NET-cost rule).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scripts.desk import plan_replay as pr


def bars(days=30, tf=15, step=0.0, wick=0.001, start=100.0, seed=None):
    """Synthetic closed bars: each close = prev close * (1+step); symmetric wicks."""
    n = days * (1440 // tf)
    idx = pd.date_range("2026-09-01", periods=n, freq=f"{tf}min", tz="UTC")
    rng = np.random.default_rng(seed) if seed is not None else None
    closes, opens = [], []
    p = start
    for _ in range(n):
        o = p
        s = step if rng is None else rng.normal(0, 0.003)
        p = p * (1 + s)
        opens.append(o)
        closes.append(p)
    o = np.array(opens)
    c = np.array(closes)
    return pd.DataFrame({
        "open": o, "close": c,
        "high": np.maximum(o, c) * (1 + wick), "low": np.minimum(o, c) * (1 - wick),
        "volume": 1.0,
    }, index=idx)


def test_build_pool_has_one_slot_per_bar_of_day_and_skips_gaps():
    df = bars(days=25)
    pool = pr.build_pool(df, tf_minutes=15)
    assert len(pool) == 96
    # every slot gets one ratio per day except the very first bar overall
    assert sum(len(s) for s in pool) == len(df) - 1
    gapped = df.drop(df.index[500])
    pool2 = pr.build_pool(gapped, tf_minutes=15)
    # removing one bar breaks two consecutive pairs (before and after the gap) into one gap pair
    assert sum(len(s) for s in pool2) == len(gapped) - 2


def test_simulate_is_deterministic_for_a_seed():
    pool = pr.build_pool(bars(days=25, seed=1), 15)
    plan = pr.Plan(side="long", entry=100.0, stop=99.0, target=102.0)
    a = pr.simulate(pool, plan, start_slot=10, horizon=48, replays=500, seed=7)
    b = pr.simulate(pool, plan, start_slot=10, horizon=48, replays=500, seed=7)
    assert a == b
    assert abs(a["p_target"] + a["p_stop"] + a["p_neither"] - 1.0) < 1e-9


def test_uptrend_favours_long_target_and_short_stop():
    pool = pr.build_pool(bars(days=25, step=0.002, wick=0.0005), 15)
    long_mc = pr.simulate(pool, pr.Plan("long", 100.0, 99.0, 102.0), 0, 96, replays=300)
    short_mc = pr.simulate(pool, pr.Plan("short", 100.0, 101.0, 98.0), 0, 96, replays=300)
    assert long_mc["p_target"] > 0.9
    assert short_mc["p_stop"] > 0.9


def test_bar_touching_both_counts_as_stop():
    # a single ratio whose low is below the stop AND high above the target
    pool = [[(1.0, 1.05, 0.95, 1.0)] for _ in range(96)]
    mc = pr.simulate(pool, pr.Plan("long", 100.0, 98.0, 103.0), 0, 5, replays=50)
    assert mc["p_stop"] == 1.0 and mc["p_target"] == 0.0


def test_fees_lower_avg_r_by_round_trip_cost():
    pool = pr.build_pool(bars(days=25, seed=3), 15)
    plan = pr.Plan("long", 100.0, 99.0, 102.0)
    gross = pr.simulate(pool, plan, 5, 48, replays=400, seed=11, fee_pct=0.0)
    net = pr.simulate(pool, plan, 5, 48, replays=400, seed=11, fee_pct=0.04)
    # round trip 2 x 0.04% of 100 = 0.08 on a risk of 1.0 -> 0.08 R
    assert net["cost_r"] == pytest.approx(0.08)
    assert net["avg_r"] == pytest.approx(gross["avg_r"] - 0.08, abs=1e-6)


def test_slot_wraps_past_midnight():
    pool = [[(1.0, 1.0, 1.0, 1.0)] for _ in range(96)]
    pool[3] = [(1.0, 1.10, 1.0, 1.10)]  # only slot 3 can reach the target
    mc = pr.simulate(pool, pr.Plan("long", 100.0, 95.0, 105.0), start_slot=94, horizon=8,
                     replays=20, window=0)
    assert mc["p_target"] == 1.0


@pytest.mark.parametrize("plan, msg", [
    (pr.Plan("long", 100.0, 101.0, 105.0), "stop"),
    (pr.Plan("long", 100.0, 99.0, 98.0), "target"),
    (pr.Plan("short", 100.0, 99.0, 98.0), "stop"),
    (pr.Plan("long", 100.0, 99.99, 105.0), "too tight"),
    (pr.Plan("hold", 100.0, 99.0, 105.0), "side"),
])
def test_invalid_plans_are_refused(plan, msg):
    with pytest.raises(pr.PlanError, match=msg):
        pr.validate(plan)


@pytest.mark.parametrize("p_target, p_stop, r, cost, head", [
    (0.45, 0.45, 1.0, 0.0, "coin flip"),
    (0.24, 0.50, 2.0, 0.0, "break-even"),   # needs 33 %, got 32 %
    (0.40, 0.40, 2.0, 0.0, "Strongly toward the target"),
    (0.20, 0.70, 1.0, 0.0, "Strongly toward the stop"),
    (0.0, 0.0, 1.0, 0.0, "No replay"),
])
def test_verdict_thresholds(p_target, p_stop, r, cost, head):
    mc = {"p_target": p_target, "p_stop": p_stop, "r_at_target": r, "cost_r": cost, "horizon": 96}
    assert head.lower() in pr.verdict(mc).lower()


def test_fees_raise_the_break_even_share():
    # 1R plan, 50/50 split: a coin flip gross, but leans to the stop once fees cost 0.25R
    mc = {"p_target": 0.5, "p_stop": 0.5, "r_at_target": 1.0, "horizon": 96}
    assert "coin flip" in pr.verdict({**mc, "cost_r": 0.0}).lower()
    assert "toward the stop" in pr.verdict({**mc, "cost_r": 0.25}).lower()


def test_history_replays_the_rule_on_real_bars():
    df = bars(days=25, step=0.002, wick=0.0005)
    plan = pr.Plan("long", float(df["close"].iloc[-1]), float(df["close"].iloc[-1]) * 0.99,
                   float(df["close"].iloc[-1]) * 1.02)
    h = pr.history(df, plan, tf_minutes=15, horizon=96)
    assert h["n"] >= 20
    assert h["p_target"] > 0.9


def test_run_refuses_too_little_data():
    with pytest.raises(pr.PlanError, match="days"):
        pr.run(bars(days=5), pr.Plan("long", 100.0, 99.0, 102.0), tf_minutes=15, horizon=48)


def test_cli_offline_json(tmp_path, capsys):
    df = bars(days=25, seed=5)
    rows = [[int(ts.timestamp() * 1000), r.open, r.high, r.low, r.close, r.volume]
            for ts, r in df.iterrows()]
    f = tmp_path / "klines.json"
    f.write_text(json.dumps(rows))
    last = float(df["close"].iloc[-1])
    code = pr.main(["--symbol", "BTC/USDT", "--tf", "15m", "--side", "long",
                    "--entry", str(last), "--stop", str(last * 0.99), "--target", str(last * 1.02),
                    "--horizon", "48", "--replays", "300", "--offline", str(f), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["plan"]["symbol"] == "BTC/USDT"
    assert {"mc", "history", "verdict"} <= set(out)
    assert out["mc"]["seed"] == 19
