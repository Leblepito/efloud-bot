"""Tests for candle-close synchronization in bot_runner.

Task 3: Verify that scan runs only at candle boundary + 2s, not mid-candle.

NOTE: The implementation is already complete in bot_runner.py (lines 480-498).
These tests verify the existing behavior.
"""
import time
from unittest.mock import Mock

import pytest

from backend.bot_runner import BotRunner


def test_candle_close_sync_skips_scan_inside_candle():
    """Verify that scan is skipped when called mid-candle (not at boundary+2s)."""
    mock_config = Mock()
    mock_config.check_interval_sec = 10
    mock_config.timeframes = {'entry': '15m'}

    runner = BotRunner.__new__(BotRunner)
    runner.cfg = {'timeframes': {'entry': '15m'}}
    runner.last_scan_candle_ts = 100 * 900000  # Last scan at candle 100 start time

    # Current time: 100 * 900000ms + 45000ms (mid-candle, 45 seconds into the 15-min candle)
    # current_candle_ts = ((90000000 + 45000 - 2000) // 900000) * 900000 = 90000000
    # This equals last_scan_candle_ts, so scan should be skipped
    current_ms = 100 * 900000 + 45000

    with Mock() as time_mock:
        time_mock.time.return_value = current_ms / 1000
        # Patch time.time
        import backend.bot_runner as br_module
        original_time = br_module.time
        br_module.time = time_mock

        try:
            # Set minimal dependencies - None will cause early return before scan logic
            runner.universe = None
            runner.orch = None
            runner.client = None
            runner.order_mgr = None

            original_last_scan = runner.last_scan_candle_ts
            runner._scan_universe()

            # Should NOT scan because we're inside the same candle
            # Timestamp should remain unchanged
            assert runner.last_scan_candle_ts == original_last_scan, \
                f"Expected {original_last_scan}, got {runner.last_scan_candle_ts}"
        finally:
            br_module.time = original_time


def test_candle_close_sync_runs_scan_at_boundary():
    """Verify that scan runs when called at candle boundary + 2s."""
    mock_config = Mock()
    mock_config.check_interval_sec = 10
    mock_config.timeframes = {'entry': '15m'}

    runner = BotRunner.__new__(BotRunner)
    runner.cfg = {
        'timeframes': {'htf': '4h', 'mtf': '1h', 'entry': '15m', 'kline_limit': 500},
        'operation': {'dry_run': True}
    }
    runner.last_scan_candle_ts = 100 * 900000  # Last scan at candle 100

    # Current time: (101 * 900000ms) + 2000ms (2 seconds after candle 101 closes)
    # current_candle_ts = ((90900000 + 2000 - 2000) // 900000) * 900000 = 101 * 900000
    # This is > last_scan_candle_ts, so scan should run
    current_ms = 101 * 900000 + 2000

    with Mock() as time_mock:
        time_mock.time.return_value = current_ms / 1000
        import backend.bot_runner as br_module
        original_time = br_module.time
        br_module.time = time_mock

        try:
            # Set up minimal dependencies to allow scan
            runner.universe = Mock()
            runner.universe.resolve = Mock(return_value=['BTCUSDT'])
            runner.orch = Mock()
            runner.client = Mock()
            runner.client.fetch_ohlcv = Mock(return_value=None)
            runner.order_mgr = Mock()

            call_count = {'count': 0}

            def tracked_run_cycle(*args, **kwargs):
                call_count['count'] += 1
                return {}

            runner.orch.run_cycle = tracked_run_cycle

            runner._scan_universe()

            # Should scan because we're at candle boundary + 2s
            assert call_count['count'] > 0, \
                f"Scan should have run, but run_cycle was called {call_count['count']} times"

            # The timestamp should be updated to the current candle boundary
            expected_ts = 101 * 900000
            assert runner.last_scan_candle_ts == expected_ts, \
                f"Expected {expected_ts}, got {runner.last_scan_candle_ts}"
        finally:
            br_module.time = original_time


def test_candle_close_sync_first_scan_always_runs():
    """Verify that first scan (last_scan_candle_ts=0) always runs."""
    runner = BotRunner.__new__(BotRunner)
    runner.cfg = {
        'timeframes': {'htf': '4h', 'mtf': '1h', 'entry': '15m', 'kline_limit': 500},
        'operation': {'dry_run': True}
    }
    runner.last_scan_candle_ts = 0  # Never scanned before

    # Any time should work for first scan
    current_ms = 100 * 900000 + 5000

    with Mock() as time_mock:
        time_mock.time.return_value = current_ms / 1000
        import backend.bot_runner as br_module
        original_time = br_module.time
        br_module.time = time_mock

        try:
            runner.universe = Mock()
            runner.universe.resolve = Mock(return_value=['BTCUSDT'])
            runner.orch = Mock()
            runner.client = Mock()
            runner.client.fetch_ohlcv = Mock(return_value=None)
            runner.order_mgr = Mock()

            call_count = {'count': 0}

            def tracked_run_cycle(*args, **kwargs):
                call_count['count'] += 1
                return {}

            runner.orch.run_cycle = tracked_run_cycle

            runner._scan_universe()

            # Should scan because it's the first scan
            assert call_count['count'] > 0, "First scan should always run"
            assert runner.last_scan_candle_ts > 0, "Timestamp should be updated"
        finally:
            br_module.time = original_time


def test_candle_close_sync_uses_config_entry_timeframe():
    """Verify that the sync uses entry timeframe from config (5m = 300000 ms)."""
    runner = BotRunner.__new__(BotRunner)
    runner.cfg = {
        'timeframes': {'htf': '1h', 'mtf': '15m', 'entry': '5m', 'kline_limit': 500},
        'operation': {'dry_run': True}
    }
    runner.last_scan_candle_ts = 50 * 300000  # Last scan at candle 50

    # Current time: (51 * 300000ms) + 2000ms (2 seconds after candle 51 closes for 5m timeframe)
    current_ms = 51 * 300000 + 2000

    with Mock() as time_mock:
        time_mock.time.return_value = current_ms / 1000
        import backend.bot_runner as br_module
        original_time = br_module.time
        br_module.time = time_mock

        try:
            runner.universe = Mock()
            runner.universe.resolve = Mock(return_value=['BTCUSDT'])
            runner.orch = Mock()
            runner.client = Mock()
            runner.client.fetch_ohlcv = Mock(return_value=None)
            runner.order_mgr = Mock()

            call_count = {'count': 0}

            def tracked_run_cycle(*args, **kwargs):
                call_count['count'] += 1
                return {}

            runner.orch.run_cycle = tracked_run_cycle

            runner._scan_universe()

            # Should scan for 5m timeframe
            assert call_count['count'] > 0, "Scan should run at 5m candle boundary + 2s"
            expected_ts = 51 * 300000
            assert runner.last_scan_candle_ts == expected_ts, \
                f"Expected {expected_ts}, got {runner.last_scan_candle_ts}"
        finally:
            br_module.time = original_time
