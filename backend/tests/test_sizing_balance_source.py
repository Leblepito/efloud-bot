"""Unit tests for sizing_balance_source flag dispatch.

The flag controls which balance metric is fed into calc_position_size():
- 'total' (default): bot.client.get_balance() — totalMarginBalance
- 'available':       bot.client.get_available_margin() — availableBalance

Risk breakers, guards, and drawdown calc continue using totalMarginBalance
regardless of the flag — these tests only validate the sizing-side choice.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from engine.safe_orchestrator import _sizing_balance


class TestSizingBalanceSource:
    """Direct unit test of the dispatch helper.

    We don't construct a full SafeOrchestrator here — too heavy and not
    the unit under test. The helper is the entire seam; testing it
    isolates the behavior change from PR-A.
    """

    def test_total_mode_uses_live_balance(self):
        client = MagicMock()
        client.get_balance.return_value = 2156.32
        client.get_available_margin.return_value = 1820.00
        result = _sizing_balance(client, source="total", live_balance=2156.32)
        assert result == pytest.approx(2156.32)
        client.get_available_margin.assert_not_called()

    def test_available_mode_calls_get_available_margin(self):
        client = MagicMock()
        client.get_balance.return_value = 2156.32
        client.get_available_margin.return_value = 1820.00
        result = _sizing_balance(client, source="available", live_balance=2156.32)
        assert result == pytest.approx(1820.00)
        client.get_available_margin.assert_called_once()

    def test_unknown_source_falls_back_to_total_with_warning(self, caplog):
        """Defensive: typo in config (e.g. 'availble') must not crash bot."""
        client = MagicMock()
        client.get_balance.return_value = 2156.32
        with caplog.at_level(logging.WARNING, logger="efloud.safe_orch"):
            result = _sizing_balance(client, source="availble", live_balance=2156.32)
        assert result == pytest.approx(2156.32)
        assert any(
            "sizing_balance_source" in r.message for r in caplog.records
        ), f"Expected warning about sizing_balance_source, got: {[r.message for r in caplog.records]}"

    def test_default_when_source_is_none(self):
        """Missing config key → behave as 'total'."""
        client = MagicMock()
        client.get_balance.return_value = 2156.32
        result = _sizing_balance(client, source=None, live_balance=2156.32)
        assert result == pytest.approx(2156.32)
        client.get_available_margin.assert_not_called()

    def test_dry_run_no_client_call(self):
        """In dry_run, live_balance is the synthetic 10000.0 float and we must
        not call the client at all — it may be None or unconfigured."""
        result = _sizing_balance(client=None, source="available", live_balance=10000.0)
        assert result == pytest.approx(10000.0)

    def test_available_returns_zero_no_negative(self):
        """If exchange returns 0 (margin fully deployed), sizing must accept
        0.0 cleanly — calc_position_size will then return 0 contracts and
        the guard rejects the trade. No exception."""
        client = MagicMock()
        client.get_available_margin.return_value = 0.0
        result = _sizing_balance(client, source="available", live_balance=2156.32)
        assert result == 0.0

    def test_case_insensitive(self):
        """Config typo with caps ('AVAILABLE' or 'Total') should still work."""
        client = MagicMock()
        client.get_available_margin.return_value = 1500.0
        assert _sizing_balance(client, "AVAILABLE", 2000.0) == pytest.approx(1500.0)
        assert _sizing_balance(client, "Total", 2000.0) == pytest.approx(2000.0)

    def test_non_string_source_falls_back(self):
        """Defensive: if YAML somehow yields an int/None, no crash."""
        client = MagicMock()
        client.get_balance.return_value = 2000.0
        # Bool, int, etc. — all should fall back to 'total'
        assert _sizing_balance(client, source=True, live_balance=2000.0) == 2000.0
        assert _sizing_balance(client, source=42, live_balance=2000.0) == 2000.0
