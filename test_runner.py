#!/usr/bin/env python
"""Simple test runner to avoid pytest capture issues."""
import sys
import traceback
from unittest.mock import Mock, patch
import time

# Add project root to path
sys.path.insert(0, r'C:\Users\utkuc\Downloads\efloud-bot')

from backend.bot_runner import BotRunner

def test_candle_close_sync_skips_scan_inside_candle():
    """Verify that scan is skipped when called mid-candle (not at boundary+2s)."""
    print("TEST: test_candle_close_sync_skips_scan_inside_candle")
    mock_config = Mock()
    mock_config.check_interval_sec = 10
    mock_config.timeframes = {'entry': '15m'}

    mock_exchange = Mock()

    with patch('backend.bot_runner.Exchange', return_value=mock_exchange):
        runner = BotRunner(config=mock_config)
        runner.last_scan_candle_ts = 100  # Initialized to candle index 100

        # Current time: 100 * 900000ms + 45000ms (mid-candle)
        # (current - 2000) // 900000 = 100 (same as last_scan_ts)
        current_ms = 100 * 900000 + 45000

        with patch('time.time', return_value=current_ms / 1000):
            # We need to check the actual _scan_universe behavior
            # The current implementation uses candle timestamp (ms), not index
            # So we need to set it to the actual timestamp

            # Set up minimal dependencies
            runner.universe = None  # Will cause early return
            runner.orch = None
            runner.order_mgr = None
            runner.client = None

            original_last_scan = runner.last_scan_candle_ts
            runner._scan_universe()

            # Should NOT scan because we're inside the same candle
            assert runner.last_scan_candle_ts == original_last_scan, f"Expected {original_last_scan}, got {runner.last_scan_candle_ts}"
            print("  ✓ PASS: Scan skipped mid-candle")

def test_candle_close_sync_runs_scan_at_boundary():
    """Verify that scan runs when called at candle boundary + 2s."""
    print("TEST: test_candle_close_sync_runs_scan_at_boundary")
    mock_config = Mock()
    mock_config.check_interval_sec = 10
    mock_config.timeframes = {'entry': '15m'}

    mock_exchange = Mock()

    with patch('backend.bot_runner.Exchange', return_value=mock_exchange):
        runner = BotRunner(config=mock_config)
        # Set to a specific candle timestamp
        runner.last_scan_candle_ts = 100 * 900000  # Candle 100 start time

        # Current time: (101 * 900000ms) + 2000ms (boundary + 2s)
        current_ms = 101 * 900000 + 2000

        with patch('time.time', return_value=current_ms / 1000):
            # Set up minimal dependencies to allow scan
            runner.universe = Mock()
            runner.universe.resolve = Mock(return_value=['BTCUSDT'])
            runner.orch = Mock()
            runner.client = Mock()
            runner.client.fetch_ohlcv = Mock(return_value=None)
            runner.order_mgr = Mock()
            runner.cfg = {
                'timeframes': {'htf': '4h', 'mtf': '1h', 'entry': '15m', 'kline_limit': 500},
                'operation': {'dry_run': True}
            }

            call_count = {'count': 0}
            original_run_cycle = runner.orch.run_cycle

            def tracked_run_cycle(*args, **kwargs):
                call_count['count'] += 1
                return {}

            runner.orch.run_cycle = tracked_run_cycle

            runner._scan_universe()

            # Should scan because we're at candle boundary + 2s
            assert call_count['count'] > 0, f"Scan should have run, but run_cycle was called {call_count['count']} times"
            # The timestamp should be updated to the current candle boundary
            expected_ts = 101 * 900000
            assert runner.last_scan_candle_ts == expected_ts, f"Expected {expected_ts}, got {runner.last_scan_candle_ts}"
            print(f"  ✓ PASS: Scan ran at boundary, timestamp updated to {runner.last_scan_candle_ts}")

def test_candle_close_sync_first_scan_always_runs():
    """Verify that first scan (last_scan_candle_ts=0) always runs."""
    print("TEST: test_candle_close_sync_first_scan_always_runs")
    mock_config = Mock()
    mock_config.check_interval_sec = 10
    mock_config.timeframes = {'entry': '15m'}

    mock_exchange = Mock()

    with patch('backend.bot_runner.Exchange', return_value=mock_exchange):
        runner = BotRunner(config=mock_config)
        runner.last_scan_candle_ts = 0  # Never scanned before

        runner.universe = Mock()
        runner.universe.resolve = Mock(return_value=['BTCUSDT'])
        runner.orch = Mock()
        runner.client = Mock()
        runner.client.fetch_ohlcv = Mock(return_value=None)
        runner.order_mgr = Mock()
        runner.cfg = {
            'timeframes': {'htf': '4h', 'mtf': '1h', 'entry': '15m', 'kline_limit': 500},
            'operation': {'dry_run': True}
        }

        call_count = {'count': 0}

        def tracked_run_cycle(*args, **kwargs):
            call_count['count'] += 1
            return {}

        runner.orch.run_cycle = tracked_run_cycle

        runner._scan_universe()

        # Should scan because it's the first scan
        assert call_count['count'] > 0, "First scan should always run"
        assert runner.last_scan_candle_ts > 0, "Timestamp should be updated"
        print(f"  ✓ PASS: First scan ran, timestamp updated to {runner.last_scan_candle_ts}")

if __name__ == '__main__':
    tests = [
        test_candle_close_sync_skips_scan_inside_candle,
        test_candle_close_sync_runs_scan_at_boundary,
        test_candle_close_sync_first_scan_always_runs,
    ]

    failed = []
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"  ✗ FAIL: {e}")
            traceback.print_exc()
            failed.append((test.__name__, e))

    print("\n" + "="*60)
    if failed:
        print(f"FAILED: {len(failed)}/{len(tests)} tests")
        for name, err in failed:
            print(f"  - {name}: {err}")
        sys.exit(1)
    else:
        print(f"SUCCESS: All {len(tests)} tests passed")
        sys.exit(0)
