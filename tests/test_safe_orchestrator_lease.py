"""
Fail-closed unit tests for SafeOrchestrator lease integration.
Tests that lease failure blocks trades and cross-symbol isolation works.
"""
import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from engine.safe_orchestrator import SafeOrchestrator
from engine.instance_manager import InstanceManager


@pytest.fixture
def sample_dataframes():
    """Create sample dataframes for testing."""
    # Use current time to avoid freshness check failures
    now = pd.Timestamp.now(tz='UTC').floor('15min')
    dates = pd.date_range(end=now, periods=100, freq='15min')

    df_entry = pd.DataFrame({
        'open': range(100, 200),
        'high': range(105, 205),
        'low': range(95, 195),
        'close': range(100, 200),
        'volume': range(1000, 1100)
    }, index=dates)

    # MTF and HTF are resampled versions
    df_mtf = df_entry.resample('1h').last()
    df_htf = df_entry.resample('4h').last()
    df_daily = df_entry.resample('1D').last()

    return df_htf, df_mtf, df_entry, df_daily


@pytest.fixture
def orchestrator():
    """Create SafeOrchestrator with mocked instance manager."""
    config = {
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "structure": {
            "swing_lookback": 5,
            "ob_sequential": 5,
            "body_mode": True,
            "eq_threshold_pct": 0.1,
            "range_lookback": 50
        },
        "fibonacci": {
            "ote_lower": 0.618,
            "ote_upper": 0.786,
            "ext_tp2": 1.618
        },
        "safety": {
            "starting_balance": 10000,
            "daily_loss_limit_pct": 3.0,
            "weekly_drawdown_limit_pct": 8.0
        },
        "risk": {
            "max_open_positions": 20,
            "min_confluence": 55,
            "min_rr": 1.5
        },
        "operation": {
            "watch_only": False
        }
    }
    # Create orchestrator with freshness_check disabled to avoid stale data issues
    orch = SafeOrchestrator(config=config, order_manager=None, freshness_check=False)
    orch.instance_mgr = Mock(spec=InstanceManager)
    return orch


class TestLeaseBlocking:
    """Test that lease failure blocks trades."""

    def test_lease_failure_blocks_trade(self, orchestrator, sample_dataframes):
        """When sync_acquire_symbol returns False, run_cycle should return can_trade=False."""
        orchestrator.instance_mgr.sync_acquire_symbol.return_value = False

        df_htf, df_mtf, df_entry, df_daily = sample_dataframes

        result = orchestrator.run_cycle(
            symbol="BTCUSDT",
            df_htf=df_htf,
            df_mtf=df_mtf,
            df_entry=df_entry,
            df_daily=df_daily,
            balance=10000
        )

        # Should be blocked by lease
        assert result.can_trade is False
        assert "[LEASE] BLOCKED" in result.actions_taken[0]
        orchestrator.instance_mgr.sync_acquire_symbol.assert_called_once_with("BTCUSDT")

    def test_lease_success_allows_trade(self, orchestrator, sample_dataframes):
        """When sync_acquire_symbol returns True, trade logic should proceed normally."""
        orchestrator.instance_mgr.sync_acquire_symbol.return_value = True

        df_htf, df_mtf, df_entry, df_daily = sample_dataframes

        result = orchestrator.run_cycle(
            symbol="BTCUSDT",
            df_htf=df_htf,
            df_mtf=df_mtf,
            df_entry=df_entry,
            df_daily=df_daily,
            balance=10000
        )

        # Verify the orchestrator completed the cycle
        assert result.symbol == "BTCUSDT"
        orchestrator.instance_mgr.sync_acquire_symbol.assert_called_once_with("BTCUSDT")
        orchestrator.instance_mgr.sync_release_symbol.assert_called_once_with("BTCUSDT")

    def test_lease_released_after_cycle(self, orchestrator, sample_dataframes):
        """Lease should be released after trade cycle completes."""
        orchestrator.instance_mgr.sync_acquire_symbol.return_value = True

        df_htf, df_mtf, df_entry, df_daily = sample_dataframes

        result = orchestrator.run_cycle(
            symbol="ETHUSDT",
            df_htf=df_htf,
            df_mtf=df_mtf,
            df_entry=df_entry,
            df_daily=df_daily,
            balance=10000
        )

        # Verify the cycle completed and lease was released
        assert result.symbol == "ETHUSDT"
        orchestrator.instance_mgr.sync_release_symbol.assert_called_once_with("ETHUSDT")


class TestCrossSymbolNonContamination:
    """Test that lease failure for one symbol doesn't affect others."""

    def test_btc_failure_doesnt_block_eth(self, orchestrator, sample_dataframes):
        """BTC lease failure should not affect ETH trading."""
        # Configure instance_mgr to fail BTC but succeed ETH
        def mock_acquire(symbol):
            return symbol != "BTCUSDT"  # Fail BTC, succeed others

        orchestrator.instance_mgr.sync_acquire_symbol.side_effect = mock_acquire

        df_htf, df_mtf, df_entry, df_daily = sample_dataframes

        btc_result = orchestrator.run_cycle(
            symbol="BTCUSDT",
            df_htf=df_htf,
            df_mtf=df_mtf,
            df_entry=df_entry,
            df_daily=df_daily,
            balance=10000
        )

        eth_result = orchestrator.run_cycle(
            symbol="ETHUSDT",
            df_htf=df_htf,
            df_mtf=df_mtf,
            df_entry=df_entry,
            df_daily=df_daily,
            balance=10000
        )

        # BTC should be blocked by lease
        assert btc_result.can_trade is False
        assert "[LEASE] BLOCKED" in btc_result.actions_taken[0]

        # ETH should complete normally
        assert eth_result.symbol == "ETHUSDT"
        orchestrator.instance_mgr.sync_release_symbol.assert_called_with("ETHUSDT")

    def test_concurrent_symbols_independent_leases(self, orchestrator, sample_dataframes):
        """Multiple symbols should maintain independent lease states."""
        # All leases succeed
        orchestrator.instance_mgr.sync_acquire_symbol.return_value = True

        df_htf, df_mtf, df_entry, df_daily = sample_dataframes

        # Run multiple symbols
        symbols = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
        results = {}
        for sym in symbols:
            results[sym] = orchestrator.run_cycle(
                symbol=sym,
                df_htf=df_htf,
                df_mtf=df_mtf,
                df_entry=df_entry,
                df_daily=df_daily,
                balance=10000
            )

        # All should complete their cycles
        for sym, result in results.items():
            assert result.symbol == sym

        # Each should call acquire and release exactly once
        assert orchestrator.instance_mgr.sync_acquire_symbol.call_count == 3
        assert orchestrator.instance_mgr.sync_release_symbol.call_count == 3


class TestLeaseGateEdgeCases:
    """Test edge cases in lease gate behavior."""

    def test_lease_then_breaker_trip_still_releases(self, orchestrator, sample_dataframes):
        """Even if breaker trips, lease should be released."""
        orchestrator.instance_mgr.sync_acquire_symbol.return_value = True

        df_htf, df_mtf, df_entry, df_daily = sample_dataframes

        # Mock breaker to be tripped
        with patch.object(orchestrator.breaker, 'check', return_value=MagicMock(can_trade=False, state=MagicMock(value='tripped'), reason='Test breaker trip')):
            result = orchestrator.run_cycle(
                symbol="BTCUSDT",
                df_htf=df_htf,
                df_mtf=df_mtf,
                df_entry=df_entry,
                df_daily=df_daily,
                balance=10000
            )

        # Should be breaker-blocked
        assert result.can_trade is False
        assert "tripped" in result.breaker_state.lower() or result.breaker_state != "active"

        # But lease should still be released
        orchestrator.instance_mgr.sync_release_symbol.assert_called_once_with("BTCUSDT")

    def test_lease_failure_skips_expensive_analysis(self, orchestrator, sample_dataframes):
        """Lease failure should prevent expensive analysis from running."""
        orchestrator.instance_mgr.sync_acquire_symbol.return_value = False

        df_htf, df_mtf, df_entry, df_daily = sample_dataframes

        result = orchestrator.run_cycle(
            symbol="BTCUSDT",
            df_htf=df_htf,
            df_mtf=df_mtf,
            df_entry=df_entry,
            df_daily=df_daily,
            balance=10000
        )

        # Should be blocked by lease immediately
        assert result.can_trade is False
        assert "[LEASE] BLOCKED" in result.actions_taken[0]

        # Lease should not be released since it was never acquired
        orchestrator.instance_mgr.sync_release_symbol.assert_not_called()