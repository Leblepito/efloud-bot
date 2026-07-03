"""Integration tests for SMC v2 pullback detection in safe_orchestrator.

Tests the full orchestrator flow:
1. Price enters zone for first time → NO entry (must leave first)
2. Price leaves zone → has_left_zone=True, state=AWAITING_REENTRY
3. Price re-enters zone → ENTRY (pullback complete)
"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pandas as pd

from engine.smc_v2.zones import ZoneSpec


class TestOrchestratorPullbackDetection:
    """Test orchestrator pullback detection state machine."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock SafeOrchestrator with minimal dependencies."""
        from engine.safe_orchestrator import SafeOrchestrator
        from engine.smc_v2.setup_state import SetupStateStore
        from engine.smc_v2.zones import ZoneSpec
        from engine.journal import TradeJournal
        from engine.smc_v2.setup_state import SetupCandidate

        # Minimal config
        config = {
            "structure": {
                "swing_lookback": 5,
                "ob_sequential": 5,
                "body_mode": "strict",
                "eq_threshold_pct": 50,
                "range_lookback": 20,
            },
            "fibonacci": {
                "ote_lower": 0.618,
                "ote_upper": 0.786,
            },
            "safety": {
                "sl_atr_buffer": 0.5,
                "min_sl_atr": 0.5,
                "max_sl_atr": 5.0,
                "daily_loss_limit_pct": 3.0,
                "weekly_drawdown_limit_pct": 8.0,
            },
            "risk": {
                "max_position_size_usd": 100,
                "default_risk_pct": 1.0,
            },
            "smc_v2": {
                "require_confirmation": False,  # Test without confirmation first
                "pullback_timeout_bars": 50,
                "smc_v2_shadow": True,  # Shadow mode, no actual orders
            },
            "exchange": {
                "maker_fee": 0.0002,
                "taker_fee": 0.0004,
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "setup_candidates.json"
            journal_path = Path(tmpdir) / "trades.jsonl"

            # Create instances
            journal = TradeJournal(journal_path=journal_path)
            setup_store = SetupStateStore(path=state_path)

            # Create orchestrator with minimal deps (order_manager=None is fine for shadow mode)
            orch = SafeOrchestrator(
                config=config,
                state_dir=tmpdir,
                order_manager=None,  # No real orders needed
                trade_journal=journal,
                setup_state_store=setup_store,
                persist=False,  # Don't persist state in tests
                freshness_check=False,  # No freshness checks in tests
            )
            yield orch, state_path

    def test_first_zone_entry_no_entry_without_leaving(
        self, mock_orchestrator
    ):
        """Price entering zone for FIRST time should NOT trigger entry (must leave first)."""
        orch, state_path = mock_orchestrator

        # Create a candidate in AWAITING_PULLBACK
        from engine.smc_v2.setup_state import SetupCandidate

        cand = SetupCandidate(
            symbol="BTC/USDT",
            direction="LONG",
            trigger_bar_ts=1234567890000,
            trigger_price=50000.0,
            htf_bias="BULL",
            target_zone=ZoneSpec(low=49000.0, high=49500.0, source="OTE"),
            htf_swing_anchor=48000.0,
            bars_waited=0,
            state="AWAITING_PULLBACK",
            confluence_score=60,
            has_left_zone=False,
        )
        orch.setup_state_store.add(cand)

        # Sim: price enters zone (49200 is inside 49000-49500)
        # Expected: state -> IN_ZONE, NO entry (has_left_zone is false)
        with patch.object(orch, "_place_v2_entry_order") as mock_place:
            orch._advance_setup_state_tick(
                symbol="BTC/USDT",
                current_price=49200.0,
                current_bar_ts=1234567900000,
                df_15m=None,
            )

            # Verify: NO entry placed, state moved to IN_ZONE
            mock_place.assert_not_called()
            assert cand.state == "IN_ZONE"
            assert cand.has_left_zone is False

    def test_price_leaves_zone_sets_has_left_zone_true(self, mock_orchestrator):
        """Price leaving zone should set has_left_zone=True and move to AWAITING_REENTRY."""
        orch, state_path = mock_orchestrator

        # Create candidate already in IN_ZONE
        from engine.smc_v2.setup_state import SetupCandidate

        cand = SetupCandidate(
            symbol="BTC/USDT",
            direction="LONG",
            trigger_bar_ts=1234567890000,
            trigger_price=50000.0,
            htf_bias="BULL",
            target_zone=ZoneSpec(low=49000.0, high=49500.0, source="OTE"),
            htf_swing_anchor=48000.0,
            bars_waited=5,
            state="IN_ZONE",
            confluence_score=60,
            has_left_zone=False,
        )
        orch.setup_state_store.add(cand)

        # Sim: price leaves zone (49800 is above 49500)
        with patch.object(orch, "_place_v2_entry_order") as mock_place:
            orch._advance_setup_state_tick(
                symbol="BTC/USDT",
                current_price=49800.0,
                current_bar_ts=1234567910000,
                df_15m=None,
            )

            # Verify: has_left_zone set, state moved to AWAITING_REENTRY
            mock_place.assert_not_called()
            assert cand.state == "AWAITING_REENTRY"
            assert cand.has_left_zone is True

    def test_price_re_enters_zone_triggers_entry(self, mock_orchestrator):
        """Price re-entering zone AFTER leaving should trigger entry (pullback complete)."""
        orch, state_path = mock_orchestrator

        # Create candidate in AWAITING_REENTRY (has_left_zone=True)
        from engine.smc_v2.setup_state import SetupCandidate

        cand = SetupCandidate(
            symbol="BTC/USDT",
            direction="LONG",
            trigger_bar_ts=1234567890000,
            trigger_price=50000.0,
            htf_bias="BULL",
            target_zone=ZoneSpec(low=49000.0, high=49500.0, source="OTE"),
            htf_swing_anchor=48000.0,
            bars_waited=10,
            state="AWAITING_REENTRY",
            confluence_score=60,
            has_left_zone=True,
        )
        orch.setup_state_store.add(cand)

        # Sim: price re-enters zone (49200 is inside 49000-49500)
        # Expected: ENTRY placed (has_left_zone is true, this is a pullback)
        with patch.object(orch, "_place_v2_entry_order") as mock_place:
            orch._advance_setup_state_tick(
                symbol="BTC/USDT",
                current_price=49200.0,
                current_bar_ts=1234567920000,
                df_15m=None,
            )

            # Verify: ENTRY placed
            mock_place.assert_called_once()
            assert cand.state == "CONFIRMED"

    def test_full_flow_no_entry_on_first_visit(self, mock_orchestrator):
        """Full flow: first zone visit → leave → re-entry → entry."""
        orch, state_path = mock_orchestrator

        # Create candidate
        from engine.smc_v2.setup_state import SetupCandidate

        cand = SetupCandidate(
            symbol="ETH/USDT",
            direction="SHORT",
            trigger_bar_ts=1234567890000,
            trigger_price=3000.0,
            htf_bias="BEAR",
            target_zone=ZoneSpec(low=3050.0, high=3100.0, source="HTF_FVG"),
            htf_swing_anchor=3200.0,
            bars_waited=0,
            state="AWAITING_PULLBACK",
            confluence_score=70,
            has_left_zone=False,
        )
        orch.setup_state_store.add(cand)

        with patch.object(orch, "_place_v2_entry_order") as mock_place:
            # Step 1: Price enters zone (3080 inside 3050-3100)
            orch._advance_setup_state_tick(symbol="ETH/USDT", current_price=3080.0, current_bar_ts=1234567900000, df_15m=None)
            assert cand.state == "IN_ZONE"
            assert not cand.has_left_zone
            mock_place.assert_not_called()

            # Step 2: Price leaves zone (3040 below 3050)
            orch._advance_setup_state_tick(symbol="ETH/USDT", current_price=3040.0, current_bar_ts=1234567910000, df_15m=None)
            assert cand.state == "AWAITING_REENTRY"
            assert cand.has_left_zone is True
            mock_place.assert_not_called()

            # Step 3: Price re-enters zone (3070 inside 3050-3100) - THIS should trigger entry
            orch._advance_setup_state_tick(symbol="ETH/USDT", current_price=3070.0, current_bar_ts=1234567920000, df_15m=None)
            assert cand.state == "CONFIRMED"
            mock_place.assert_called_once()

    def test_stays_in_zone_no_leave_no_entry(self, mock_orchestrator):
        """Price stays in zone without leaving → NO entry (waiting for leave)."""
        orch, state_path = mock_orchestrator

        # Create candidate in IN_ZONE
        from engine.smc_v2.setup_state import SetupCandidate

        cand = SetupCandidate(
            symbol="BTC/USDT",
            direction="LONG",
            trigger_bar_ts=1234567890000,
            trigger_price=50000.0,
            htf_bias="BULL",
            target_zone=ZoneSpec(low=49000.0, high=49500.0, source="OTE"),
            htf_swing_anchor=48000.0,
            bars_waited=5,
            state="IN_ZONE",
            confluence_score=60,
            has_left_zone=False,
        )
        orch.setup_state_store.add(cand)

        with patch.object(orch, "_place_v2_entry_order") as mock_place:
            # Price stays in zone across multiple ticks
            for i, price in enumerate([49200, 49300, 49100, 49400]):
                orch._advance_setup_state_tick(symbol="BTC/USDT", current_price=price, current_bar_ts=1234567890000 + i * 60000, df_15m=None)

            # Verify: Still IN_ZONE, NO entry (never left)
            assert cand.state == "IN_ZONE"
            assert not cand.has_left_zone
            mock_place.assert_not_called()


class TestOrchestratorPullbackWithConfirmation:
    """Test pullback detection WITH confirmation enabled."""

    @pytest.fixture
    def mock_orchestrator_with_conf(self):
        """Create orchestrator with confirmation REQUIRED."""
        from engine.safe_orchestrator import SafeOrchestrator
        from engine.smc_v2.setup_state import SetupStateStore
        from engine.journal import TradeJournal

        config = {
            "structure": {
                "swing_lookback": 5,
                "ob_sequential": 5,
                "body_mode": "strict",
                "eq_threshold_pct": 50,
                "range_lookback": 20,
            },
            "fibonacci": {
                "ote_lower": 0.618,
                "ote_upper": 0.786,
            },
            "safety": {
                "sl_atr_buffer": 0.5,
                "min_sl_atr": 0.5,
                "max_sl_atr": 5.0,
                "daily_loss_limit_pct": 3.0,
                "weekly_drawdown_limit_pct": 8.0,
            },
            "risk": {
                "max_position_size_usd": 100,
                "default_risk_pct": 1.0,
            },
            "smc_v2": {
                "require_confirmation": True,  # Confirmation REQUIRED
                "pullback_timeout_bars": 50,
                "smc_v2_shadow": True,
            },
            "exchange": {
                "maker_fee": 0.0002,
                "taker_fee": 0.0004,
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "setup_candidates.json"
            journal_path = Path(tmpdir) / "trades.jsonl"

            journal = TradeJournal(journal_path=journal_path)
            setup_store = SetupStateStore(path=state_path)

            orch = SafeOrchestrator(
                config=config,
                state_dir=tmpdir,
                order_manager=None,
                trade_journal=journal,
                setup_state_store=setup_store,
                persist=False,
                freshness_check=False,
            )
            yield orch

    def test_with_confirmation_re_entry_requires_engulfing(
        self, mock_orchestrator_with_conf
    ):
        """With confirmation: re-entry still requires engulfing pattern."""
        orch = mock_orchestrator_with_conf

        # Create candidate in AWAITING_REENTRY (has_left_zone=True)
        from engine.smc_v2.setup_state import SetupCandidate

        cand = SetupCandidate(
            symbol="BTC/USDT",
            direction="LONG",
            trigger_bar_ts=1234567890000,
            trigger_price=50000.0,
            htf_bias="BULL",
            target_zone=ZoneSpec(low=49000.0, high=49500.0, source="OTE"),
            htf_swing_anchor=48000.0,
            bars_waited=10,
            state="AWAITING_REENTRY",
            confluence_score=60,
            has_left_zone=True,
        )
        orch.setup_state_store.add(cand)

        # Mock df_15m with engulfing pattern
        # Bullish engulfing: prior bar bearish (close < open), current bar bullish (close > open)
        base_ts = 1234567900000  # After trigger
        mock_df = pd.DataFrame({
            "open": [49150, 49100],
            "high": [49200, 49300],
            "low": [49050, 49080],
            "close": [49100, 49250],  # Prior: bearish, Current: bullish engulfing
        }, index=pd.to_datetime([base_ts, base_ts + 60000], unit="ms"))

        with patch.object(orch, "_place_v2_entry_order") as mock_place:
            # Tick 1: Price re-enters zone, moves from AWAITING_REENTRY → IN_ZONE (waiting for engulfing)
            orch._advance_setup_state_tick(
                symbol="BTC/USDT",
                current_price=49250.0,
                current_bar_ts=base_ts + 60000,
                df_15m=mock_df,
            )
            # State moved to IN_ZONE, no entry yet (waiting for engulfing)
            assert cand.state == "IN_ZONE"
            mock_place.assert_not_called()

            # Tick 2: Still in zone, now IN_ZONE block runs engulfing check → CONFIRMED
            orch._advance_setup_state_tick(
                symbol="BTC/USDT",
                current_price=49250.0,
                current_bar_ts=base_ts + 120000,
                df_15m=mock_df,
            )

            mock_place.assert_called_once()
            assert cand.state == "CONFIRMED"
