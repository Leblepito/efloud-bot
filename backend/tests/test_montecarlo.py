"""S6: Monte Carlo bootstrap + in-sample/out-of-sample split for the backtest.

A single contiguous backtest gives one point estimate. S6 adds:
  * bootstrap_pnl_distribution — resample the trade-pnl sequence with replacement
    to get a distribution of return / max-drawdown (luck / overfit sensitivity);
  * walk_forward_split — index ranges for an IS/OOS split so edge can be checked
    out-of-sample;
  * montecarlo_gate — a robustness gate (5th-percentile return must stay > 0).
"""
import pytest

from backtest.montecarlo import (
    bootstrap_pnl_distribution,
    montecarlo_gate,
    walk_forward_split,
)


def test_bootstrap_all_positive_pnls_positive_distribution():
    pnls = [10.0] * 50
    d = bootstrap_pnl_distribution(pnls, initial_balance=1000.0, n_runs=500, seed=1)
    assert d["n_trades"] == 50
    assert d["return_pct_p05"] == pytest.approx(50.0)  # 50×10 = +500 / 1000 = +50% (no variance)
    assert d["return_pct_p95"] == pytest.approx(50.0)
    assert d["max_drawdown_pct_p95"] == pytest.approx(0.0)  # monotonic up → no DD


def test_bootstrap_is_deterministic_with_seed():
    pnls = [12.0, -8.0, 5.0, -3.0, 20.0, -15.0] * 10
    a = bootstrap_pnl_distribution(pnls, 1000.0, n_runs=300, seed=42)
    b = bootstrap_pnl_distribution(pnls, 1000.0, n_runs=300, seed=42)
    assert a == b
    # Mixed pnls → spread between p05 and p95.
    assert a["return_pct_p05"] < a["return_pct_p95"]


def test_bootstrap_empty_is_safe():
    d = bootstrap_pnl_distribution([], 1000.0)
    assert d["n_trades"] == 0
    assert d["return_pct_p50"] == 0.0


def test_walk_forward_split_ranges():
    is_rng, oos_rng = walk_forward_split(n_bars=1000, warmup_bars=200, is_frac=0.7)
    # usable = 800; IS len = 560 → IS [200, 760), OOS [760, 1000)
    assert is_rng == (200, 760)
    assert oos_rng == (760, 1000)
    # No overlap, contiguous, both non-empty.
    assert is_rng[1] == oos_rng[0]
    assert oos_rng[1] - oos_rng[0] > 0


def test_montecarlo_gate_passes_when_p05_positive():
    assert montecarlo_gate({"return_pct_p05": 5.0}) is True
    assert montecarlo_gate({"return_pct_p05": -1.0}) is False
