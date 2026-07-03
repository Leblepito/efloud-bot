"""Unit tests for candle close synchronization in BotRunner and main.py loop."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
import pytest

from backend.bot_runner import BotRunner
from main import run_cycle

def test_bot_runner_scan_universe_only_runs_on_candle_close():
    """BotRunner._scan_universe should skip execution if within the same candle timeframe,
    and trigger exactly when the candle close boundary is crossed."""
    runner = BotRunner()
    runner.universe = MagicMock()
    runner.universe.resolve.return_value = ["BTC/USDT"]
    runner.orch = MagicMock()
    runner.order_mgr = MagicMock()
    runner.client = MagicMock()
    runner.cfg = {
        "timeframes": {"entry": "15m", "htf": "4h", "mtf": "1h"},
        "operation": {"dry_run": True}
    }

    # Initial state: last_scan_candle_ts should be 0
    assert runner.last_scan_candle_ts == 0

    # 1) First execution (startup): must run the scan regardless of timeframe
    runner._scan_universe()
    assert runner.orch.run_cycle.call_count == 1
    initial_ts = runner.last_scan_candle_ts
    assert initial_ts > 0

    # 2) Second execution (still within the same 15m candle, e.g. 10s later): must skip
    with patch("time.time", return_value=(initial_ts / 1000.0) + 10.0):
        runner._scan_universe()
    # Call count remains 1
    assert runner.orch.run_cycle.call_count == 1

    # 3) Third execution (crosses the candle boundary, e.g. 15 minutes + 5 seconds later): must scan
    # entry_tf_ms = 900,000 ms.
    with patch("time.time", return_value=(initial_ts / 1000.0) + 905.0):
        runner._scan_universe()
    # Call count incremented to 2
    assert runner.orch.run_cycle.call_count == 2
    assert runner.last_scan_candle_ts > initial_ts


def test_main_run_cycle_only_scans_on_candle_close():
    """run_cycle in main.py should only scan symbols on candle close boundaries."""
    orch = MagicMock()
    client = MagicMock()
    order_mgr = MagicMock()
    rate_limiter = MagicMock()
    universe = MagicMock()
    universe.resolve.return_value = ["BTC/USDT"]

    cfg = {
        "timeframes": {"entry": "15m", "htf": "4h", "mtf": "1h"},
        "operation": {"dry_run": True, "symbol_scan_mode": "sequential"}
    }

    # 1) Startup: last_scan_ts = 0
    # Should run the sequential/parallel scan
    with patch("main._scan_sequential") as mock_scan:
        ts1 = run_cycle(orch, client, order_mgr, rate_limiter, universe, cfg, 0)
        assert mock_scan.call_count == 1
        assert ts1 > 0

    # 2) Same candle: call run_cycle again with return timestamp
    with patch("main._scan_sequential") as mock_scan:
        # Simulate time 10 seconds after ts1
        with patch("time.time", return_value=(ts1 / 1000.0) + 10.0):
            ts2 = run_cycle(orch, client, order_mgr, rate_limiter, universe, cfg, ts1)
            # Should skip scanning
            assert mock_scan.call_count == 0
            assert ts2 == ts1

    # 3) Next candle close: simulation crosses boundary (15 minutes + 5 seconds later)
    with patch("main._scan_sequential") as mock_scan:
        with patch("time.time", return_value=(ts1 / 1000.0) + 905.0):
            ts3 = run_cycle(orch, client, order_mgr, rate_limiter, universe, cfg, ts1)
            # Should trigger scan
            assert mock_scan.call_count == 1
            assert ts3 > ts1
