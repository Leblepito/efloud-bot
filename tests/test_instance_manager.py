"""
Fail-closed unit tests for InstanceManager.sync_acquire_symbol and sync_release_symbol.
Tests decision logic without actual DB dependencies.
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from engine.instance_manager import InstanceManager


@pytest.fixture
def instance_manager():
    """Create InstanceManager with mocked dependencies."""
    mock_db = Mock()
    config = {
        "INSTANCE_COORDINATION_ENABLED": True,
        "INSTANCE_ID": "test-instance",
        "INSTANCE_SYMBOLS": "BTCUSDT,ETHUSDT",
        "INSTANCE_MAX_INSTANCES": 3,
        "INSTANCE_ACQUIRE_TIMEOUT_SEC": 1.5,
        "INSTANCE_RELEASE_TIMEOUT_SEC": 3.0,
        "INSTANCE_LEASE_DURATION_SEC": 30
    }
    manager = InstanceManager(db=mock_db, config=config)
    return manager


class TestSyncAcquireSymbolFailClosed:
    """Test fail-closed behavior of sync_acquire_symbol."""

    def test_coordination_disabled_returns_true_no_call(self, instance_manager):
        """When coordination_enabled=False, should return True without calling acquire_lease."""
        instance_manager.coordination_enabled = False

        result = instance_manager.sync_acquire_symbol("BTCUSDT")

        assert result is True
        instance_manager.db.acquire_lease.assert_not_called()

    def test_event_loop_missing_returns_false_with_alert(self, instance_manager):
        """When event loop is None/missing, should return False with alert."""
        instance_manager.coordination_enabled = True
        instance_manager._loop = None

        with patch.object(instance_manager, '_alert') as mock_alert:
            result = instance_manager.sync_acquire_symbol("BTCUSDT")

            assert result is False
            mock_alert.assert_called_once_with("coord_event_loop_missing",
                "coordination enabled but loop missing — blocking BTCUSDT")

    def test_event_loop_closed_returns_false_with_alert(self, instance_manager):
        """When event loop is closed, should return False with alert."""
        instance_manager.coordination_enabled = True
        instance_manager._loop = Mock()
        instance_manager._loop.is_closed.return_value = True

        with patch.object(instance_manager, '_alert') as mock_alert:
            result = instance_manager.sync_acquire_symbol("BTCUSDT")

            assert result is False
            mock_alert.assert_called_once_with("coord_event_loop_missing",
                "coordination enabled but loop missing — blocking BTCUSDT")

    def test_db_timeout_returns_false_with_alert(self, instance_manager):
        """When DB times out, should return False with alert."""
        instance_manager.coordination_enabled = True
        instance_manager._loop = Mock()
        instance_manager._loop.is_closed.return_value = False

        # Create completed future that will raise timeout when result() is called
        future = Mock()
        future.result.side_effect = asyncio.TimeoutError()

        with patch('asyncio.run_coroutine_threadsafe', return_value=future), \
             patch.object(instance_manager, '_alert') as mock_alert:
            result = instance_manager.sync_acquire_symbol("BTCUSDT")

            assert result is False
            mock_alert.assert_called_once_with("coord_db_timeout",
                "lease acquire BTCUSDT timed out — blocking")

    def test_db_exception_returns_false_with_alert(self, instance_manager):
        """When DB raises exception, should return False with alert."""
        instance_manager.coordination_enabled = True
        instance_manager._loop = Mock()
        instance_manager._loop.is_closed.return_value = False

        # Mock future that raises exception
        future = Mock()
        future.result.side_effect = Exception("Connection lost")

        with patch('asyncio.run_coroutine_threadsafe', return_value=future), \
             patch.object(instance_manager, '_alert') as mock_alert:
            result = instance_manager.sync_acquire_symbol("ETHUSDT")

            assert result is False
            mock_alert.assert_called_once_with("coord_db_error",
                "lease acquire ETHUSDT failed (Connection lost) — blocking")

    def test_contention_returns_false_no_alert(self, instance_manager):
        """When acquire_lease returns None (contention), should return False without alert."""
        instance_manager.coordination_enabled = True
        instance_manager._loop = Mock()
        instance_manager._loop.is_closed.return_value = False

        # Mock future that returns None (contention)
        future = Mock()
        future.result.return_value = None

        with patch('asyncio.run_coroutine_threadsafe', return_value=future), \
             patch.object(instance_manager, '_alert') as mock_alert:
            result = instance_manager.sync_acquire_symbol("BTCUSDT")

            assert result is False
            mock_alert.assert_not_called()  # Contention is normal, no alert

    def test_success_returns_true_stores_token_string(self, instance_manager):
        """When acquire_lease succeeds, should return True and store token as string."""
        instance_manager.coordination_enabled = True
        instance_manager._loop = Mock()
        instance_manager._loop.is_closed.return_value = False

        # Mock asyncio.run_coroutine_threadsafe to return token string
        token = "test-lease-token-abc123"
        future = Mock()
        future.result.return_value = token

        with patch('asyncio.run_coroutine_threadsafe', return_value=future):
            result = instance_manager.sync_acquire_symbol("BTCUSDT")

            assert result is True
            assert instance_manager._active_leases["BTCUSDT"] == token
            assert isinstance(instance_manager._active_leases["BTCUSDT"], str)

    def test_cross_symbol_non_contamination(self, instance_manager):
        """Lease failure for one symbol should not affect other symbols."""
        instance_manager.coordination_enabled = True
        instance_manager._loop = Mock()
        instance_manager._loop.is_closed.return_value = False

        # BTC fails (contention)
        btc_future = Mock()
        btc_future.result.return_value = None

        # ETH succeeds
        eth_token = "eth-lease-token-xyz789"
        eth_future = Mock()
        eth_future.result.return_value = eth_token

        call_count = [0]

        with patch('asyncio.run_coroutine_threadsafe') as mock_run:
            # Configure mock to return different futures on alternating calls
            def side_effect(coro, loop):
                call_count[0] += 1
                if call_count[0] == 1:  # First call (BTC)
                    return btc_future
                else:  # Second call (ETH)
                    return eth_future

            mock_run.side_effect = side_effect

            btc_result = instance_manager.sync_acquire_symbol("BTCUSDT")
            eth_result = instance_manager.sync_acquire_symbol("ETHUSDT")

            assert btc_result is False
            assert eth_result is True
            assert "BTCUSDT" not in instance_manager._active_leases
            assert instance_manager._active_leases["ETHUSDT"] == eth_token


class TestSyncReleaseSymbol:
    """Test sync_release_symbol behavior."""

    def test_release_success_pops_token(self, instance_manager):
        """Successful release should remove token from active_leases."""
        instance_manager.coordination_enabled = True
        instance_manager._loop = Mock()
        instance_manager._loop.is_closed.return_value = False
        instance_manager._active_leases["BTCUSDT"] = "token-abc123"

        # Mock successful release
        future = Mock()
        future.result.return_value = True

        with patch('asyncio.run_coroutine_threadsafe', return_value=future):
            result = instance_manager.sync_release_symbol("BTCUSDT")

            assert result is True
            assert "BTCUSDT" not in instance_manager._active_leases

    def test_release_failure_returns_false_no_warning(self, instance_manager):
        """Failed release (no exception) should return False without warning."""
        instance_manager.coordination_enabled = True
        instance_manager._loop = Mock()
        instance_manager._loop.is_closed.return_value = False
        instance_manager._active_leases["BTCUSDT"] = "token-abc123"

        # Mock failed release (returns False, no exception)
        future = Mock()
        future.result.return_value = False

        with patch('asyncio.run_coroutine_threadsafe', return_value=future), \
             patch('engine.instance_manager.log') as mock_log:
            result = instance_manager.sync_release_symbol("BTCUSDT")

            assert result is False
            mock_log.warning.assert_not_called()  # No exception, so no warning

    def test_release_no_token_returns_true(self, instance_manager):
        """Release when no token exists should return True (idempotent)."""
        instance_manager.coordination_enabled = True
        instance_manager._loop = Mock()
        instance_manager._loop.is_closed.return_value = False

        result = instance_manager.sync_release_symbol("BTCUSDT")

        assert result is True
        # Should not call DB if no token

    def test_release_no_loop_returns_true(self, instance_manager):
        """Release when event loop missing should return True (graceful degradation)."""
        instance_manager.coordination_enabled = True
        instance_manager._loop = None
        instance_manager._active_leases["BTCUSDT"] = "token-abc123"

        result = instance_manager.sync_release_symbol("BTCUSDT")

        assert result is True

    def test_release_loop_closed_returns_false_with_warning(self, instance_manager):
        """Release when event loop closed should attempt operation and fail gracefully."""
        instance_manager.coordination_enabled = True
        instance_manager._loop = Mock()
        instance_manager._loop.is_closed.return_value = True
        instance_manager._active_leases["BTCUSDT"] = "token-abc123"

        # Mock run_coroutine_threadsafe to raise exception on closed loop
        future = Mock()
        future.result.side_effect = RuntimeError("Event loop is closed")

        with patch('asyncio.run_coroutine_threadsafe', return_value=future), \
             patch('engine.instance_manager.log') as mock_log:
            result = instance_manager.sync_release_symbol("BTCUSDT")

            assert result is False
            mock_log.warning.assert_called()  # Should log warning about failure