"""Engine purity test — SafeOrchestrator must run with NO real disk writes
or network calls when freshness_check=False, persist=False, NullNotifications.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §6.1
"""
from unittest.mock import patch
import socket
import pandas as pd
import pytest
import yaml

from engine import SafeOrchestrator
from engine.notifications import NullNotificationManager


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_orchestrator_runs_with_no_real_disk_or_network(base_config, fs):
    """fs fixture from pyfakefs — any real disk write would fail or be invisible
    to the os module after the fixture is torn down. Network is blocked."""
    fs.create_dir("/fake_state")
    fs.add_real_file("configs/config.phase2_1k.yaml")

    # Block sockets at the syscall level
    with patch("socket.socket", side_effect=RuntimeError("Network use forbidden in pure mode")):
        orch = SafeOrchestrator(
            base_config,
            state_dir="/fake_state",
            notification_mgr=NullNotificationManager(),
            freshness_check=False,
            persist=False,
        )
        idx = pd.date_range("2026-01-01", periods=300, freq="15min")
        df = pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0},
            index=idx,
        )
        # One full cycle
        orch.run_cycle("BTC/USDT", df, df, df, df, balance=1000.0)

    # Asserting the cycle completed without raising is the test.
    # Bonus: state_dir must be untouched (persist=False)
    import os
    assert os.listdir("/fake_state") == []
