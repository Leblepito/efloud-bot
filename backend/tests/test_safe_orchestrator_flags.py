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
    """NullNotificationManager.notify() must not raise and must return None."""
    from engine.notifications import NullNotificationManager
    nm = NullNotificationManager()
    assert nm.notify("test_event", {"key": "value"}) is None
    assert nm.notify_position_opened(None) is None  # Tolerates any signature

    # SafeOrchestrator accepts injected null manager
    orch = SafeOrchestrator(
        base_config,
        state_dir=str(tmp_path),
        notification_mgr=nm,
        freshness_check=False,
        persist=False,
    )
    assert orch.notification_mgr is nm
