"""v1 vs v2 backtest comparison harness (PR #S4, spec §8.2).

Tests:
- harness produces both v1 and v2 result dicts + deltas + gates
- gate evaluation: pass / warn / hard_reject per metric
- delta computation: per-metric abs + rel_pct
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import yaml

from backtest.comparison import (
    DEFAULT_GATES,
    _avg_realized_rr,
    compute_deltas,
    evaluate_gates,
    run_v1_v2_comparison,
)


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def synthetic_data():
    rng = np.random.default_rng(7)
    n_15m = 400
    idx_15m = pd.date_range("2025-01-01", periods=n_15m, freq="15min", tz="UTC")
    idx_1h = pd.date_range("2025-01-01", periods=n_15m // 4 + 1, freq="1h", tz="UTC")
    idx_4h = pd.date_range("2025-01-01", periods=n_15m // 16 + 1, freq="4h", tz="UTC")
    idx_1d = pd.date_range("2025-01-01", periods=max(n_15m // 96 + 2, 5), freq="1D", tz="UTC")

    def make_df(idx):
        closes = 100 + np.cumsum(rng.normal(0, 0.5, len(idx)))
        return pd.DataFrame({
            "open": closes,
            "high": closes + 0.3,
            "low": closes - 0.3,
            "close": closes,
            "volume": 1000.0,
        }, index=idx)

    return {
        "ETH/USDT": {
            "4h": make_df(idx_4h),
            "1h": make_df(idx_1h),
            "15m": make_df(idx_15m),
            "1d": make_df(idx_1d),
        }
    }


def test_comparison_runs_both_paths(base_config, synthetic_data):
    report = run_v1_v2_comparison(
        symbols=["ETH/USDT"], data=synthetic_data, config=base_config
    )
    assert "v1" in report and "v2" in report
    assert "deltas" in report and "gates" in report
    assert report["v1"]["smc_version"] == "v1"
    assert report["v2"]["smc_version"] == "v2"
    # stop_hunt_rate computed and injected
    assert "stop_hunt_rate" in report["v1"]
    assert "stop_hunt_rate" in report["v2"]
    # avg_realized_rr computed and injected
    assert "avg_realized_rr" in report["v1"]
    assert "avg_realized_rr" in report["v2"]


def test_evaluate_gates_pass_case():
    v1 = {
        "win_rate": 50.0,
        "max_drawdown_pct": 10.0,
        "sharpe_like": 1.0,
        "stop_hunt_rate": 0.3,
    }
    v2 = {
        "win_rate": 60.0,           # higher than v1 → pass
        "max_drawdown_pct": 8.0,    # lower than v1 → pass
        "sharpe_like": 1.2,         # higher than v1 → pass
        "stop_hunt_rate": 0.1,      # < 50% of v1 → pass
        "avg_realized_rr": 2.0,     # >= 1.5 absolute → pass
    }
    gates = evaluate_gates(v1, v2, DEFAULT_GATES)
    assert gates["win_rate"] == "pass"
    assert gates["max_drawdown_pct"] == "pass"
    assert gates["sharpe_like"] == "pass"
    assert gates["stop_hunt_rate"] == "pass"
    assert gates["avg_realized_rr"] == "pass"


def test_evaluate_gates_hard_reject_case():
    v1 = {
        "win_rate": 50.0,
        "max_drawdown_pct": 10.0,
        "sharpe_like": 1.0,
        "stop_hunt_rate": 0.3,
    }
    v2 = {
        "win_rate": 50.0,
        "max_drawdown_pct": 10.0,
        "sharpe_like": 0.5,         # 0.5/1.0 = 0.5 < 0.9 → hard_reject
        "stop_hunt_rate": 0.5,      # 0.5/0.3 = 1.67 > 1.0 → hard_reject
        "avg_realized_rr": 1.0,     # < 1.2 absolute → hard_reject
    }
    gates = evaluate_gates(v1, v2, DEFAULT_GATES)
    assert gates["sharpe_like"] == "hard_reject"
    assert gates["stop_hunt_rate"] == "hard_reject"
    assert gates["avg_realized_rr"] == "hard_reject"


def test_evaluate_gates_warn_case():
    v1 = {
        "win_rate": 50.0,
        "max_drawdown_pct": 10.0,
        "sharpe_like": 1.0,
        "stop_hunt_rate": 0.3,
    }
    v2 = {
        "win_rate": 48.0,           # 0.96/1.0 = 0.96, in (0.95, 1.0) → warn
        "max_drawdown_pct": 10.5,   # 10.5/10 = 1.05, in (1.0, 1.1) → warn
        "sharpe_like": 0.95,        # in (0.9, 1.0) → warn
        "stop_hunt_rate": 0.2,      # 0.2/0.3 = 0.67, in (0.5, 1.0) → warn
        "avg_realized_rr": 1.3,     # in (1.2, 1.5) → warn
    }
    gates = evaluate_gates(v1, v2, DEFAULT_GATES)
    assert gates["win_rate"] == "warn"
    assert gates["max_drawdown_pct"] == "warn"
    assert gates["sharpe_like"] == "warn"
    assert gates["stop_hunt_rate"] == "warn"
    assert gates["avg_realized_rr"] == "warn"


def test_deltas_computed_per_metric():
    v1 = {"win_rate": 50.0, "max_drawdown_pct": 10.0, "sharpe_like": 1.0, "total_trades": 20}
    v2 = {"win_rate": 60.0, "max_drawdown_pct": 8.0, "sharpe_like": 1.2, "total_trades": 12}
    d = compute_deltas(v1, v2)
    assert d["win_rate"]["abs"] == pytest.approx(10.0)
    assert d["win_rate"]["rel_pct"] == pytest.approx(20.0)
    assert d["sharpe_like"]["abs"] == pytest.approx(0.2)
    assert d["sharpe_like"]["rel_pct"] == pytest.approx(20.0)
    assert d["total_trades"]["abs"] == -8


def test_deltas_handles_zero_v1():
    """rel_pct must be None (not raise) when v1=0."""
    v1 = {"x": 0.0}
    v2 = {"x": 5.0}
    d = compute_deltas(v1, v2)
    assert d["x"]["abs"] == 5.0
    assert d["x"]["rel_pct"] is None


def test_deltas_skips_non_numeric():
    """Non-numeric fields (lists, strings) are skipped."""
    v1 = {"trades": [{"a": 1}], "name": "v1"}
    v2 = {"trades": [{"a": 2}], "name": "v2"}
    d = compute_deltas(v1, v2)
    assert "trades" not in d
    assert "name" not in d


def test_avg_realized_rr_basic():
    """Direct unit: LONG win + SHORT loss + degenerate trade (skipped)."""
    trades = [
        # LONG win: entry=100, sl=95 (risk=5), exit=110 (gain=10) → RR=+2.0
        {"entry": 100.0, "sl": 95.0, "exit": 110.0, "pnl": 10.0},
        # SHORT loss: entry=100, sl=105 (risk=5), exit=105 (loss=5) → RR=-1.0
        {"entry": 100.0, "sl": 105.0, "exit": 105.0, "pnl": -5.0},
        # Degenerate: entry == sl → skipped (zero risk)
        {"entry": 100.0, "sl": 100.0, "exit": 110.0, "pnl": 10.0},
    ]
    rr = _avg_realized_rr(trades)
    # Average of (+2.0, -1.0) = +0.5
    assert rr == pytest.approx(0.5)


def test_avg_realized_rr_empty_returns_zero():
    assert _avg_realized_rr([]) == 0.0


def test_evaluate_gates_zero_v1_branch():
    """When v1 metric is 0, ratio division is avoided. v2>=0 passes,
    v2<0 hard_rejects (for higher-is-better)."""
    v1 = {"sharpe_like": 0.0}
    gates = evaluate_gates(v1, {"sharpe_like": 0.0}, {"sharpe_like": DEFAULT_GATES["sharpe_like"]})
    assert gates["sharpe_like"] == "pass"
    gates = evaluate_gates(v1, {"sharpe_like": -0.5}, {"sharpe_like": DEFAULT_GATES["sharpe_like"]})
    assert gates["sharpe_like"] == "hard_reject"
