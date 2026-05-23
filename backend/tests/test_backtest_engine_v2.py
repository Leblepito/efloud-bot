"""Backtest engine — SMC v2 path (PR #S4).

Tests:
- v1 default behavior remains byte-identical (inert invariant).
- v2 path constructs SetupStateStore and threads it to the orchestrator.
- v2 path runs without exceptions on noise data.
- Result dict carries `smc_version` marker.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import yaml

from backtest.engine import run_backtest


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def synthetic_data():
    """Trending synthetic OHLCV (deterministic via seed)."""
    rng = np.random.default_rng(42)
    n_15m = 400
    idx_15m = pd.date_range("2025-01-01", periods=n_15m, freq="15min", tz="UTC")
    idx_1h = pd.date_range("2025-01-01", periods=n_15m // 4 + 1, freq="1h", tz="UTC")
    idx_4h = pd.date_range("2025-01-01", periods=n_15m // 16 + 1, freq="4h", tz="UTC")
    idx_1d = pd.date_range("2025-01-01", periods=max(n_15m // 96 + 2, 5), freq="1D", tz="UTC")

    def make_df(idx, scale=0.5):
        closes = 100 + np.cumsum(rng.normal(0, scale, len(idx)))
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


def test_v1_default_byte_identical(base_config, synthetic_data):
    """Omitting smc_version must equal explicit smc_version='v1'."""
    r1 = run_backtest(
        symbols=["ETH/USDT"],
        data=synthetic_data,
        config=base_config,
        initial_balance=2000.0,
    )
    r2 = run_backtest(
        symbols=["ETH/USDT"],
        data=synthetic_data,
        config=base_config,
        initial_balance=2000.0,
        smc_version="v1",
    )
    assert r1["total_trades"] == r2["total_trades"]
    assert r1["final_balance"] == r2["final_balance"]
    assert r1["trades"] == r2["trades"]


def test_v2_records_marker(base_config, synthetic_data):
    r = run_backtest(
        symbols=["ETH/USDT"],
        data=synthetic_data,
        config=base_config,
        smc_version="v2",
    )
    assert r["smc_version"] == "v2"


def test_v1_records_marker(base_config, synthetic_data):
    r = run_backtest(symbols=["ETH/USDT"], data=synthetic_data, config=base_config)
    assert r["smc_version"] == "v1"


def test_v2_runs_to_completion_no_exception(base_config, synthetic_data):
    """v2 should complete on noise data even if zero trades are produced."""
    r = run_backtest(
        symbols=["ETH/USDT"],
        data=synthetic_data,
        config=base_config,
        smc_version="v2",
    )
    assert r["total_trades"] >= 0
    assert r["skipped_cycles"] >= 0


def test_v2_orchestrator_receives_setup_state_store(base_config, synthetic_data, monkeypatch):
    """Verify the v2 path constructs a SetupStateStore and threads it to orch."""
    from backtest import engine as bt_engine
    captured = {}
    original_orch_cls = bt_engine.SafeOrchestrator

    class SpyOrch(original_orch_cls):
        def __init__(self, *args, **kwargs):
            captured["setup_state_store"] = kwargs.get("setup_state_store")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(bt_engine, "SafeOrchestrator", SpyOrch)
    run_backtest(
        symbols=["ETH/USDT"],
        data=synthetic_data,
        config=base_config,
        smc_version="v2",
    )
    store = captured.get("setup_state_store")
    assert store is not None
    assert store.max_pending_per_symbol == 3


def test_v1_orchestrator_setup_state_store_is_none(base_config, synthetic_data, monkeypatch):
    """v1 path must NOT construct a store."""
    from backtest import engine as bt_engine
    captured = {}
    original_orch_cls = bt_engine.SafeOrchestrator

    class SpyOrch(original_orch_cls):
        def __init__(self, *args, **kwargs):
            captured["setup_state_store"] = kwargs.get("setup_state_store")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(bt_engine, "SafeOrchestrator", SpyOrch)
    run_backtest(symbols=["ETH/USDT"], data=synthetic_data, config=base_config)
    assert captured["setup_state_store"] is None
