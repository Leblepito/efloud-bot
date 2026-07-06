"""Portfolio mode — 2+ symbols share balance + breaker.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §5
"""
import json
import pandas as pd
import pytest
import yaml

from backtest.engine import run_backtest


def _strict_dumps(obj):
    """JSON-dump with no fallback — raises on non-serializable types."""
    return json.dumps(obj, sort_keys=True)


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def synthetic_data():
    idx = pd.date_range("2026-01-01", periods=600, freq="15min")
    df = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0},
        index=idx,
    )
    syms = ["BTC/USDT", "ETH/USDT"]
    return {s: {"4h": df, "12h": df, "15m": df, "1d": df} for s in syms}


def test_portfolio_two_symbols_runs(base_config, synthetic_data):
    result = run_backtest(
        symbols=["BTC/USDT", "ETH/USDT"],
        data=synthetic_data,
        config=base_config,
        initial_balance=2000.0,
    )
    assert sorted(result["symbols"]) == ["BTC/USDT", "ETH/USDT"]


def test_portfolio_byte_identical_across_runs(base_config, synthetic_data):
    """Determinism: alphabetical processing → identical results regardless of input order."""
    r1 = run_backtest(symbols=["ETH/USDT", "BTC/USDT"], data=synthetic_data,
                      config=base_config, initial_balance=2000.0)
    r2 = run_backtest(symbols=["BTC/USDT", "ETH/USDT"], data=synthetic_data,
                      config=base_config, initial_balance=2000.0)
    for r in (r1, r2):
        r.pop("_wall_seconds", None)
    assert _strict_dumps(r1) == _strict_dumps(r2)
