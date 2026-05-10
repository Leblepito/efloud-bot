"""Regression: SafeOrchestrator must always have `self.client` attribute set.

Background: PR #24 introduced `self.client` references in _calc_size paths
(initial entry sizing + DCA sizing) without setting the attribute in __init__.
The bug surfaced ~10 hours after the audit deploy when ETH/BTC/SUI/RENDER
cycles reached the sizing path:

    'SafeOrchestrator' object has no attribute 'client'

Fix: __init__ now binds self.client = order_manager.client when an
order_manager is provided, falling back to None otherwise (paper-trade /
unit tests).

This regression test is the contract: SafeOrchestrator MUST always expose
the `client` attribute, regardless of how it's instantiated.
"""
from unittest.mock import MagicMock
import pytest
import yaml

from engine import SafeOrchestrator


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_client_attribute_present_when_order_manager_none(base_config, tmp_path):
    """No order_manager → self.client must be None, not missing."""
    orch = SafeOrchestrator(
        base_config,
        state_dir=str(tmp_path),
        order_manager=None,
        freshness_check=False,
    )
    # The attribute must EXIST. AttributeError here = regression.
    assert hasattr(orch, "client"), "SafeOrchestrator must expose `client` attribute"
    assert orch.client is None


def test_client_attribute_present_when_order_manager_has_client(base_config, tmp_path):
    """order_manager.client → self.client mirrors it."""
    fake_client = MagicMock(name="BinanceClient")
    fake_order_mgr = MagicMock(name="OrderManager")
    fake_order_mgr.client = fake_client

    orch = SafeOrchestrator(
        base_config,
        state_dir=str(tmp_path),
        order_manager=fake_order_mgr,
        freshness_check=False,
    )
    assert hasattr(orch, "client")
    assert orch.client is fake_client


def test_client_attribute_present_with_default_kwargs(base_config, tmp_path):
    """Smoke: default-constructed SafeOrchestrator has client attr."""
    orch = SafeOrchestrator(base_config, state_dir=str(tmp_path))
    assert hasattr(orch, "client"), \
        "SafeOrchestrator(default) must always expose `client` attribute"
    # When order_manager is not passed, client falls back to None
    assert orch.client is None


def test_sizing_balance_helper_can_use_self_client(base_config, tmp_path):
    """Smoke: _sizing_balance call site can read self.client without AttributeError.

    This mirrors the production code path that broke. We don't run a full
    cycle (too much setup), but we directly verify that a paper-trade
    orchestrator can pass self.client into _sizing_balance without crash.
    """
    from engine.safe_orchestrator import _sizing_balance

    orch = SafeOrchestrator(
        base_config,
        state_dir=str(tmp_path),
        order_manager=None,
        freshness_check=False,
    )
    # Direct call mimicking the production path (lines 547, 645)
    # When client is None, _sizing_balance falls back to live_balance
    result = _sizing_balance(orch.client, "total", 1000.0)
    assert result == 1000.0  # 'total' source returns live_balance unchanged
