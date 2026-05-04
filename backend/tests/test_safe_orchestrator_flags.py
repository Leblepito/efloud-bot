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
