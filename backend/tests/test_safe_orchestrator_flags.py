"""SafeOrchestrator freshness_check + persist + null notifications flags.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §6.1
"""
from unittest.mock import patch
import pytest
import yaml

from engine import SafeOrchestrator


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_freshness_check_can_be_disabled(base_config, tmp_path):
    """When freshness_check=False, validate_kline_freshness must NOT be called.

    NOTE: patch target follows the import in safe_orchestrator.py. Verify with:
        grep -n "validate_kline_freshness" engine/safe_orchestrator.py
    If imported as `from engine.safety import validate_kline_freshness`,
    patch `engine.safe_orchestrator.validate_kline_freshness` instead.
    """
    with patch("engine.safe_orchestrator.validate_kline_freshness") as mock_validate:
        orch = SafeOrchestrator(
            base_config,
            state_dir=str(tmp_path),
            freshness_check=False,
        )
        # Build minimal data
        import pandas as pd
        idx = pd.date_range("2026-01-01", periods=300, freq="15min")
        df = pd.DataFrame({"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1.0}, index=idx)
        orch.run_cycle("BTC/USDT", df, df, df, df, balance=1000)

    mock_validate.assert_not_called()


def test_persist_disabled_writes_no_state(base_config, tmp_path):
    """When persist=False, state_dir must remain empty after a cycle."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    orch = SafeOrchestrator(
        base_config,
        state_dir=str(state_dir),
        freshness_check=False,
        persist=False,
    )
    # Force a state save attempt
    orch.breaker.current_balance = 999.99
    orch._persist_state()

    files = list(state_dir.iterdir())
    assert files == [], f"Expected empty state_dir, found: {files}"


def test_null_notifications_swallow_calls(base_config, tmp_path):
    """NullNotificationManager swallows all calls used by SafeOrchestrator."""
    from engine.notifications import NullNotificationManager
    nm = NullNotificationManager()
    # Cover the actual NotificationManager call surface invoked by SafeOrchestrator
    assert nm.signal_readonly(
        symbol="BTC/USDT", direction="LONG",
        entry=100.0, sl=99.0, tp1=101.0, tp2=102.0,
        confluence=60, reasons=["test"],
    ) is None
    assert nm.position_opened(
        symbol="BTC/USDT", direction="LONG", entry=100.0,
        size=1.0, sl=99.0, tp1=101.0, confluence=60,
    ) is None
    assert nm.position_closed(
        symbol="BTC/USDT", direction="LONG", exit_price=101.0,
        pnl=1.0, reason="TP1",
    ) is None
    assert nm.alert("INFO", "test message") is None
    # Unknown method on real class — still no-op via __getattr__
    assert nm.future_method_not_yet_added(arbitrary="kwarg") is None

    # SafeOrchestrator accepts injected null manager
    orch = SafeOrchestrator(
        base_config,
        state_dir=str(tmp_path),
        notification_mgr=nm,
        freshness_check=False,
        persist=False,
    )
    assert orch.notification_mgr is nm


def test_freshness_check_default_calls_validate(base_config, tmp_path):
    """Default freshness_check=True must still invoke validate_kline_freshness."""
    with patch("engine.safe_orchestrator.validate_kline_freshness") as mock_validate:
        orch = SafeOrchestrator(base_config, state_dir=str(tmp_path))
        import pandas as pd
        idx = pd.date_range("2026-01-01", periods=300, freq="15min")
        df = pd.DataFrame(
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1.0},
            index=idx,
        )
        orch.run_cycle("BTC/USDT", df, df, df, df, balance=1000)

    assert mock_validate.called, "Default freshness_check=True should invoke validate"
