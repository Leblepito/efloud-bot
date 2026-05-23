"""State-reload roundtrip preserves tp2=None (PR #S5.6 hotfix).

PR #S5 widened Position.tp2 to Optional[float]. Two state-reload sites need
audit:

1. engine.lifecycle.Position.from_full_dict (line 224):
   Uses d.get("tp2", 0.0). Python semantics: .get returns default ONLY when
   key is absent. If key exists with None value, returns None. So this is
   ALREADY None-safe — but we lock the contract with a test.

2. engine.safe_orchestrator legacy-compact restore path (line 294):
   Uses float(d.get("tp2") or 0.0). The `or` operator treats None AND 0.0
   as falsy → coerces None → 0.0. THIS IS BROKEN. Single-target Position
   restart → silently downgraded to two-target.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.lifecycle import Position


def test_lifecycle_from_full_dict_preserves_tp2_none():
    """Roundtrip: tp2=None must survive to_full_dict → from_full_dict.
    Locks the Python .get() default-only-when-absent contract."""
    p = Position(id="x", symbol="ETH/USDT", direction="LONG",
                 sl=95.0, tp1=110.0, tp2=None)
    d = p.to_full_dict()
    assert d["tp2"] is None  # persisted as None, not 0.0
    restored = Position.from_full_dict(d)
    assert restored.tp2 is None


def test_lifecycle_from_full_dict_preserves_tp2_numeric():
    """Regression: numeric tp2 still loads as float."""
    p = Position(id="x", symbol="ETH/USDT", direction="LONG",
                 sl=95.0, tp1=110.0, tp2=120.0)
    d = p.to_full_dict()
    restored = Position.from_full_dict(d)
    assert restored.tp2 == 120.0


def test_lifecycle_from_full_dict_missing_tp2_key_defaults_to_zero():
    """Backward-compat: pre-PR-#S5 state files lack tp2 key entirely.
    Must NOT crash; defaults to 0.0 (legacy v1 numeric default)."""
    d = {"id": "x", "symbol": "ETH/USDT", "direction": "LONG",
         "entries": [], "exits": [],
         "sl": 95.0, "tp1": 110.0}  # no tp2 key
    restored = Position.from_full_dict(d)
    assert restored.tp2 == 0.0


# ──────────────────────────────────────────────────────────────────
# safe_orchestrator legacy-compact path (the actually-broken site)
# ──────────────────────────────────────────────────────────────────

def test_safe_orchestrator_legacy_compact_restore_preserves_tp2_none(tmp_path):
    """The legacy-compact (single-Entry) restore path in SafeOrchestrator
    must preserve tp2=None instead of coercing to 0.0.

    State file shape: StateStore writes positions.json with list of compact dicts.
    Compact dicts have avg_entry / remaining_size / sl / tp1 / tp2 (no entries list).
    """
    from engine.safe_orchestrator import SafeOrchestrator
    # StateStore reads {state_dir}/positions.json
    state_file = tmp_path / "positions.json"
    state_file.write_text(json.dumps({
        "saved_at": "2025-01-01T00:00:00",
        "data": [{
            "id": "p1", "symbol": "ETH/USDT", "direction": "LONG",
            "avg_entry": 100.0, "remaining_size": 1.0,
            "sl": 95.0, "tp1": 110.0, "tp2": None,
            "tp1_hit": False, "opened_at": "2025-01-01T00:00:00",
        }],
    }), encoding="utf-8")

    minimal_cfg = {
        "structure": {"swing_lookback": 5, "ob_sequential": 5,
                      "body_mode": True, "eq_threshold_pct": 0.1, "range_lookback": 50},
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {"max_open_positions": 7, "min_rr": 1.8, "min_confluence": 55,
                 "risk_per_trade_pct": 0.75, "recency_bars": 40,
                 "position_size_calculation": "legacy",
                 "max_loss_per_trade_usdt": 10, "target_stop_distance_pct": 5},
        "safety": {"daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
                   "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
                   "starting_balance": 10000, "max_position_notional_pct": 20,
                   "max_total_exposure": 5.0, "max_holding_hours": 48,
                   "max_pyramid_adds": 2, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
                   "adx_trend_threshold": 25, "adx_range_threshold": 20,
                   "volatile_atr_mult": 2.5, "reverse_min_profit_pct": 0.2,
                   "sl_atr_buffer": 0.5},
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "operation": {"check_interval_sec": 30, "log_level": "INFO"},
    }
    orc = SafeOrchestrator(minimal_cfg, state_dir=str(tmp_path), persist=False)
    # The legacy restore path runs in __init__ when state_file exists.
    # Check the restored Position carries tp2=None, not 0.0.
    assert len(orc.lifecycle.positions) == 1
    restored = orc.lifecycle.positions[0]
    assert restored.symbol == "ETH/USDT"
    assert restored.tp2 is None, (
        f"Expected tp2=None but got {restored.tp2!r} — "
        "legacy-compact restore coerced None to 0.0"
    )


def test_safe_orchestrator_legacy_compact_restore_preserves_tp2_numeric(tmp_path):
    """Regression: numeric tp2 still loads as float (no widening side-effect)."""
    from engine.safe_orchestrator import SafeOrchestrator
    state_file = tmp_path / "positions.json"
    state_file.write_text(json.dumps({
        "saved_at": "2025-01-01T00:00:00",
        "data": [{
            "id": "p1", "symbol": "ETH/USDT", "direction": "LONG",
            "avg_entry": 100.0, "remaining_size": 1.0,
            "sl": 95.0, "tp1": 110.0, "tp2": 120.0,
            "tp1_hit": False, "opened_at": "2025-01-01T00:00:00",
        }],
    }), encoding="utf-8")

    minimal_cfg = {
        "structure": {"swing_lookback": 5, "ob_sequential": 5,
                      "body_mode": True, "eq_threshold_pct": 0.1, "range_lookback": 50},
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {"max_open_positions": 7, "min_rr": 1.8, "min_confluence": 55,
                 "risk_per_trade_pct": 0.75, "recency_bars": 40,
                 "position_size_calculation": "legacy",
                 "max_loss_per_trade_usdt": 10, "target_stop_distance_pct": 5},
        "safety": {"daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
                   "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
                   "starting_balance": 10000, "max_position_notional_pct": 20,
                   "max_total_exposure": 5.0, "max_holding_hours": 48,
                   "max_pyramid_adds": 2, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
                   "adx_trend_threshold": 25, "adx_range_threshold": 20,
                   "volatile_atr_mult": 2.5, "reverse_min_profit_pct": 0.2,
                   "sl_atr_buffer": 0.5},
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "operation": {"check_interval_sec": 30, "log_level": "INFO"},
    }
    orc = SafeOrchestrator(minimal_cfg, state_dir=str(tmp_path), persist=False)
    assert len(orc.lifecycle.positions) == 1
    assert orc.lifecycle.positions[0].tp2 == 120.0
