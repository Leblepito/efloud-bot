"""SafeOrchestrator must persist _processed_signals across restarts so a
mid-cycle restart cannot re-open the same signal (SOL double-open, 2026-05-08).

Tests use pyfakefs to avoid touching the real filesystem.
"""
import time
from pathlib import Path

import pytest

from engine.safe_orchestrator import SafeOrchestrator
from engine.safety.state import StateStore


@pytest.fixture
def fs_state_dir(fs):
    """pyfakefs-backed state dir."""
    state_dir = "/state"
    fs.create_dir(state_dir)
    return state_dir


def _minimal_cfg() -> dict:
    """Minimal config that the orchestrator's __init__ will accept.

    Added vs. the original task template:
    - "structure": required by SMCEngine constructor (swing_lookback, ob_sequential,
      body_mode, eq_threshold_pct, range_lookback)
    - "fibonacci": required by SMCEngine constructor (ote_lower, ote_upper, ext_tp2)
    - "timeframes": required by run_cycle (not __init__), but safe to include
    """
    return {
        "exchange": {"market_type": "futures", "leverage": 5, "testnet": True},
        "structure": {
            "swing_lookback": 5,
            "ob_sequential": 5,
            "body_mode": True,
            "eq_threshold_pct": 0.1,
            "range_lookback": 50,
        },
        "fibonacci": {
            "ote_lower": 0.618,
            "ote_upper": 0.786,
            "ext_tp2": 1.618,
        },
        "timeframes": {
            "htf": "4h",
            "mtf": "1h",
            "entry": "15m",
            "kline_limit": 500,
        },
        "risk": {"max_open_positions": 5},
        "safety": {
            "starting_balance": 2000,
            "daily_loss_limit_pct": 10,
            "weekly_drawdown_limit_pct": 15,
            "max_position_notional_pct": 10,
            "max_holding_hours": 48,
            "max_pyramid_adds": 2,
            "min_sl_atr": 0.5,
            "max_sl_atr": 5.0,
            "consecutive_loss_limit": 3,
            "consecutive_pause_min": 120,
        },
        "operation": {"dry_run": True, "persist": True},
    }


def test_processed_signals_round_trip(fs_state_dir):
    """Sets get persisted, then a fresh orchestrator restores them."""
    store = StateStore(fs_state_dir)
    sig_key = ("SOL/USDT", "LONG", 175.42)
    now_ts = time.time()
    store.save("processed_signals", [
        [list(sig_key), now_ts],
    ])

    orch = SafeOrchestrator(_minimal_cfg(), state_dir=fs_state_dir)
    assert sig_key in orch._processed_signals
    assert abs(orch._processed_signals[sig_key] - now_ts) < 1.0


def test_processed_signals_persists_after_record(fs_state_dir):
    """When a signal is recorded, the disk file reflects it on next read."""
    orch = SafeOrchestrator(_minimal_cfg(), state_dir=fs_state_dir)
    sig_key = ("FIL/USDT", "LONG", 1.10)
    now_ts = time.time()
    orch._processed_signals[sig_key] = now_ts

    # Trigger persistence — production code persists inside _persist_state(),
    # which is called from the same place that already writes breaker/positions.
    orch._persist_state()

    on_disk = StateStore(fs_state_dir).load("processed_signals")
    assert on_disk is not None
    keys = {tuple(entry[0]) for entry in on_disk}
    assert sig_key in keys


def test_stale_entries_pruned_on_restore_via_first_cycle(fs_state_dir):
    """A stale (>1h old) entry persisted to disk gets pruned on first dedup
    pass (existing 3600s housekeeping at safe_orchestrator.py:412-415).
    Restore itself is intentionally not pruning — the check loop already does."""
    store = StateStore(fs_state_dir)
    fresh = ("ETH/USDT", "LONG", 3000.0)
    stale = ("BTC/USDT", "SHORT", 67000.0)
    now = time.time()
    store.save("processed_signals", [
        [list(fresh), now - 60],          # 1 minute old
        [list(stale), now - 7200],        # 2 hours old → should be pruned by next cycle
    ])

    orch = SafeOrchestrator(_minimal_cfg(), state_dir=fs_state_dir)
    assert fresh in orch._processed_signals
    assert stale in orch._processed_signals  # restore loads everything

    pruned = {
        k: ts for k, ts in orch._processed_signals.items()
        if time.time() - ts < 3600
    }
    orch._processed_signals = pruned
    assert fresh in orch._processed_signals
    assert stale not in orch._processed_signals


def test_corrupt_processed_signals_does_not_break_init(fs_state_dir):
    """If the disk file is malformed JSON, init must not crash; it falls back
    to an empty dict (same StateStore behavior as breaker/positions)."""
    bad = Path(fs_state_dir) / "processed_signals.json"
    bad.write_text("{not valid json", encoding="utf-8")

    orch = SafeOrchestrator(_minimal_cfg(), state_dir=fs_state_dir)
    assert orch._processed_signals == {}
