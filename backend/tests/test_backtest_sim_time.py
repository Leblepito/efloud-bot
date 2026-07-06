"""Backtest trade records carry SIMULATED entry/exit timestamps.

The live engine stamps opened_at/closed_at with wall-clock datetime.utcnow()
(lifecycle.open_position). In a backtest that makes every trade look like it
happened "now", so any time-based analysis (walk-forward IS/OOS split, regime
separation) silently collapses every trade into one bucket. The run loop already
tracks the simulated bar timestamps (sim_open_ts/sim_close_ts) for S2b funding;
stamp_sim_times surfaces them onto the trade records as sim_opened_at /
sim_closed_at.
"""
import pandas as pd
import pytest
import yaml

from backtest.engine import run_backtest, stamp_sim_times


def test_stamp_sim_times_maps_by_id():
    """Maps sim open/close onto each trade by id; missing id -> None; stringified."""
    trades = [{"id": "a", "pnl": 1.0}, {"id": "b", "pnl": -1.0}, {"id": "c", "pnl": 0.5}]
    sim_open = {
        "a": pd.Timestamp("2025-06-01 12:00:00"),
        "b": pd.Timestamp("2025-12-20 03:15:00"),
        "c": pd.Timestamp("2026-02-10 09:45:00"),
    }
    sim_close = {"a": pd.Timestamp("2025-06-01 18:00:00")}

    stamp_sim_times(trades, sim_open, sim_close)

    # IS-side trade (June) vs OOS-side trade (December) get distinct sim times —
    # this is exactly what a walk-forward partition relies on.
    assert trades[0]["sim_opened_at"] == "2025-06-01 12:00:00"
    assert trades[0]["sim_closed_at"] == "2025-06-01 18:00:00"
    assert trades[1]["sim_opened_at"] == "2025-12-20 03:15:00"
    assert trades[1]["sim_closed_at"] is None      # id not in sim_close -> None
    assert trades[2]["sim_opened_at"] == "2026-02-10 09:45:00"


def test_stamp_sim_times_handles_missing_open():
    """An id absent from sim_open_ts — or present with a None value — yields None."""
    trades = [{"id": "ghost", "pnl": 0.0}, {"id": "nullval", "pnl": 0.0}]
    # ghost: id absent from both maps. nullval: id present but value is None.
    stamp_sim_times(trades, {"nullval": None}, {"nullval": None})
    assert trades[0]["sim_opened_at"] is None
    assert trades[0]["sim_closed_at"] is None
    assert trades[1]["sim_opened_at"] is None
    assert trades[1]["sim_closed_at"] is None


def test_run_backtest_trades_carry_sim_time_keys():
    """Contract: every trade record from run_backtest exposes the sim-time keys
    (so partitioning code can rely on them). Synthetic noise data may yield zero
    trades — the assertion guards the wiring whenever trades do appear."""
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    idx = pd.date_range("2026-01-01", periods=1000, freq="15min")
    closes = 100 + (idx.hour - 12).astype(float) * 0.05
    df = pd.DataFrame(
        {"open": closes, "high": closes + 0.5, "low": closes - 0.5,
         "close": closes, "volume": 1.0},
        index=idx,
    )
    data = {"BTC/USDT": {"4h": df, "12h": df, "15m": df, "1d": df}}

    res = run_backtest(symbols=["BTC/USDT"], data=data, config=cfg, initial_balance=2000.0)

    for t in res["trades"]:
        assert "sim_opened_at" in t, "trade record missing sim_opened_at"
        assert "sim_closed_at" in t, "trade record missing sim_closed_at"
