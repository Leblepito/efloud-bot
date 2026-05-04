"""Backtest engine — single-symbol walk-forward.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §5, §6.1
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
        cfg = yaml.safe_load(f)
    return cfg


@pytest.fixture
def synthetic_data():
    """1000 bars, slight trend, no real signals — used to validate plumbing."""
    idx = pd.date_range("2026-01-01", periods=1000, freq="15min")
    closes = 100 + (idx.hour - 12).astype(float) * 0.05
    df = pd.DataFrame({
        "open": closes, "high": closes + 0.5, "low": closes - 0.5,
        "close": closes, "volume": 1.0,
    }, index=idx)
    return df


def test_engine_runs_to_completion(base_config, synthetic_data):
    data = {"BTC/USDT": {"4h": synthetic_data, "1h": synthetic_data,
                         "15m": synthetic_data, "1d": synthetic_data}}
    result = run_backtest(
        symbols=["BTC/USDT"],
        data=data,
        config=base_config,
        initial_balance=2000.0,
    )
    assert result is not None
    assert result["initial_balance"] == 2000.0
    assert "final_balance" in result
    assert "trades" in result
    assert isinstance(result["trades"], list)


def test_engine_deterministic(base_config, synthetic_data):
    """Same data + config → byte-identical result.json."""
    data = {"BTC/USDT": {"4h": synthetic_data, "1h": synthetic_data,
                         "15m": synthetic_data, "1d": synthetic_data}}
    r1 = run_backtest(symbols=["BTC/USDT"], data=data, config=base_config, initial_balance=2000.0)
    r2 = run_backtest(symbols=["BTC/USDT"], data=data, config=base_config, initial_balance=2000.0)
    # Drop wall-clock fields if any
    for r in (r1, r2):
        r.pop("_wall_seconds", None)
    assert _strict_dumps(r1) == _strict_dumps(r2)


def test_mtm_dd_isolated_unit(base_config, tmp_path):
    """Inject a position manually; verify MTM drawdown picks up unrealized loss."""
    import tempfile
    from engine import SafeOrchestrator
    from engine.notifications import NullNotificationManager
    from backtest.engine import compute_mtm_drawdown

    with tempfile.TemporaryDirectory() as state_dir:
        orch = SafeOrchestrator(
            base_config, state_dir=state_dir,
            notification_mgr=NullNotificationManager(),
            freshness_check=False, persist=False,
        )
        # Manually open a LONG @ 100 size 10
        orch.lifecycle.open_position(
            symbol="BTC/USDT", direction="LONG", entry_price=100.0,
            sl=95.0, tp1=105.0, tp2=110.0, size=10.0
        )
        # Simulate price going to 90 (unrealized loss = -100)
        balance = 1000.0
        peak = 1000.0
        new_dd, new_peak = compute_mtm_drawdown(
            orch.lifecycle.positions, balance, {"BTC/USDT": 90.0}, peak
        )
        # Equity = 1000 + (90 - 100) * 10 * +1 = 900
        # DD vs peak 1000 = 10%
        assert new_dd == pytest.approx(10.0)
        assert new_peak == 1000.0


def test_mtm_drawdown_field_present(base_config, synthetic_data):
    """run_backtest result must include max_drawdown_pct (>= 0)."""
    data = {"BTC/USDT": {"4h": synthetic_data, "1h": synthetic_data,
                         "15m": synthetic_data, "1d": synthetic_data}}
    result = run_backtest(
        symbols=["BTC/USDT"],
        data=data,
        config=base_config,
        initial_balance=2000.0,
    )
    assert "max_drawdown_pct" in result
    assert result["max_drawdown_pct"] >= 0
