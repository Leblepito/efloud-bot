"""Tests for SMC v2 SetupStateStore wiring in SafeOrchestrator.

PR #S2b ships ONLY the inert opt-in scaffold:
- `setup_state_store` parameter (default None → no behavior change)
- `_advance_setup_state_tick` method (no-op when store is None)
- `confirm_entry` placeholder (always False)

Trigger phase and real confirmation land in PR #S3.
"""
from unittest.mock import MagicMock, patch
import pytest

from engine.safe_orchestrator import SafeOrchestrator


@pytest.fixture
def minimal_config():
    """Smallest config dict that lets SafeOrchestrator construct.

    Mirrors the shape used by existing safe_orchestrator tests in this repo.
    """
    return {
        "structure": {
            "swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
            "eq_threshold_pct": 0.1, "range_lookback": 50,
        },
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {"max_open_positions": 7, "min_rr": 1.8, "min_confluence": 55,
                 "risk_per_trade_pct": 0.75, "recency_bars": 40},
        "safety": {
            "daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
            "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
            "starting_balance": 10000, "max_position_notional_pct": 20,
            "max_total_exposure": 5.0, "max_holding_hours": 48,
            "max_pyramid_adds": 2, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
            "adx_trend_threshold": 25, "adx_range_threshold": 20,
            "volatile_atr_mult": 2.5, "reverse_min_profit_pct": 0.2,
        },
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "operation": {"check_interval_sec": 30, "log_level": "INFO"},
    }


class TestSetupStateStoreParameter:
    """The new `setup_state_store` parameter is optional and defaults to None.
    When None (default), no behavior changes vs v1."""

    def test_default_none_when_not_passed(self, minimal_config, tmp_path):
        orc = SafeOrchestrator(minimal_config, state_dir=str(tmp_path), persist=False)
        assert orc.setup_state_store is None

    def test_store_attribute_set_when_passed(self, minimal_config, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "setup_candidates.json")
        orc = SafeOrchestrator(
            minimal_config,
            state_dir=str(tmp_path),
            persist=False,
            setup_state_store=store,
        )
        assert orc.setup_state_store is store


class TestConfirmEntryPlaceholder:
    """confirm_entry is a stub in PR #S2b — always returns (False, None).
    Real LTF CHoCH/engulfing detection lands in PR #S3.

    The stub MUST exist so _advance_setup_state_tick can call it without
    AttributeError. Tests pin the contract: signature, return type, no
    side effects.
    """

    def test_returns_false_none_tuple(self, minimal_config, tmp_path):
        from engine.smc_v2.zones import ZoneSpec
        orc = SafeOrchestrator(minimal_config, state_dir=str(tmp_path), persist=False)
        result = orc.confirm_entry(
            df_15m=MagicMock(),
            zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
            direction="SHORT",
            since_ts=1700000000000,
        )
        assert result == (False, None)

    def test_does_not_mutate_inputs(self, minimal_config, tmp_path):
        from engine.smc_v2.zones import ZoneSpec
        orc = SafeOrchestrator(minimal_config, state_dir=str(tmp_path), persist=False)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        orig_low, orig_high = zone.low, zone.high
        orc.confirm_entry(df_15m=MagicMock(), zone=zone, direction="LONG",
                          since_ts=1700000000000)
        assert zone.low == orig_low
        assert zone.high == orig_high
