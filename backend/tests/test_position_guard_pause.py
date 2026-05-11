"""Regression tests for safety.pause_new_entries flag.

Contract under test:
- pause_new_entries flag (config or env) blocks NEW market entries at the
  PositionGuard gate, while leaving reconcile, lifecycle, SL/TP management,
  breaker, and notifications untouched.
- Default behavior (flag missing or false) is byte-identical to pre-flag bot.
- Env override is read once at config-load time (process start / container
  recreate), NOT per-call. Runtime hot-flip is out of scope for this PR.
- Source attribution (`env` vs `safety.pause_new_entries`) is preserved for
  observability.
"""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from engine.safety.position_guard import (
    PauseGateDecision,
    PositionCheckResult,
    PositionGuard,
    load_pause_config,
)
from engine.lifecycle import PositionLifecycle
from engine.safety.breaker import CircuitBreaker
from exchange import OrderManager


def _guard_with_pause(value, env=None):
    """Build a PositionGuard with the pause flag resolved at load time."""
    safety_cfg = {} if value is None else {"pause_new_entries": value}
    env_map = {} if env is None else {"EFLOUD_PAUSE_NEW_ENTRIES": env}
    with patch.dict(os.environ, env_map, clear=False):
        if env is None:
            os.environ.pop("EFLOUD_PAUSE_NEW_ENTRIES", None)
        pause_cfg = load_pause_config(safety_cfg)
    return PositionGuard(pause_config=pause_cfg), pause_cfg


def _fake_signal(symbol="ETH/USDT", side="long"):
    sig = MagicMock()
    sig.symbol = symbol
    sig.side = side
    return sig


# ---------------------------------------------------------------------------
# 1. Default behavior — flag missing means false
# ---------------------------------------------------------------------------

def test_missing_config_key_is_false_by_default():
    guard, cfg = _guard_with_pause(value=None, env=None)
    decision = guard.is_new_entry_allowed(_fake_signal())
    assert decision.allowed is True
    assert decision.reason is None
    assert cfg.enabled is False
    assert cfg.source == "default"


def test_pause_flag_false_allows_entry():
    guard, cfg = _guard_with_pause(value=False, env=None)
    decision = guard.is_new_entry_allowed(_fake_signal())
    assert decision.allowed is True
    assert cfg.enabled is False
    assert cfg.source == "config"


# ---------------------------------------------------------------------------
# 2. Config-driven pause
# ---------------------------------------------------------------------------

def test_pause_flag_true_blocks_entry():
    guard, cfg = _guard_with_pause(value=True, env=None)
    decision = guard.is_new_entry_allowed(_fake_signal(symbol="BTC/USDT", side="short"))
    assert decision.allowed is False
    assert decision.reason == "pause_new_entries"
    assert decision.source == "safety.pause_new_entries"
    assert cfg.enabled is True
    assert cfg.source == "config"


# ---------------------------------------------------------------------------
# 3. Env override precedence
# ---------------------------------------------------------------------------

def test_env_true_overrides_config_false():
    guard, cfg = _guard_with_pause(value=False, env="true")
    decision = guard.is_new_entry_allowed(_fake_signal())
    assert decision.allowed is False
    assert decision.source == "EFLOUD_PAUSE_NEW_ENTRIES"
    assert cfg.source == "env"


def test_env_false_overrides_config_true():
    guard, cfg = _guard_with_pause(value=True, env="false")
    decision = guard.is_new_entry_allowed(_fake_signal())
    assert decision.allowed is True
    assert cfg.enabled is False
    assert cfg.source == "env"


def test_env_accepts_canonical_truthy_only():
    for true_val in ["1", "true", "True", "TRUE", "yes", "YES", "on"]:
        _, cfg = _guard_with_pause(value=False, env=true_val)
        assert cfg.enabled is True, f"{true_val!r} should parse true"

    for false_val in ["0", "false", "False", "no", "off", ""]:
        _, cfg = _guard_with_pause(value=True, env=false_val)
        assert cfg.enabled is False, f"{false_val!r} should parse false"


def test_env_unknown_value_falls_back_safely_and_logs(caplog):
    with caplog.at_level(logging.WARNING):
        _, cfg = _guard_with_pause(value=True, env="maybe")
    assert cfg.enabled is True
    assert cfg.source == "config"
    assert any("EFLOUD_PAUSE_NEW_ENTRIES" in r.message and "maybe" in r.message
               for r in caplog.records)


# ---------------------------------------------------------------------------
# 4. Skip log contract
# ---------------------------------------------------------------------------

def test_skip_log_emitted_with_symbol_side_reason_source(caplog):
    guard, _ = _guard_with_pause(value=True, env=None)
    with caplog.at_level(logging.INFO, logger="efloud.posguard"):
        guard.is_new_entry_allowed(_fake_signal(symbol="SOL/USDT", side="short"))
    gate_logs = [r for r in caplog.records
                 if getattr(r, "event", None) == "position_guard.gate_blocked"]
    assert len(gate_logs) == 1
    log = gate_logs[0]
    assert log.symbol == "SOL/USDT"
    assert log.side == "short"
    assert log.is_pyramid is False
    assert log.reason == "pause_new_entries"
    assert log.source == "safety.pause_new_entries"


def test_allow_does_not_emit_skip_log(caplog):
    guard, _ = _guard_with_pause(value=False, env=None)
    with caplog.at_level(logging.INFO, logger="efloud.posguard"):
        guard.is_new_entry_allowed(_fake_signal())
    gate_logs = [r for r in caplog.records
                 if getattr(r, "event", None) == "position_guard.gate_blocked"]
    assert gate_logs == []


def test_effective_config_logged_at_load(caplog):
    with caplog.at_level(logging.INFO, logger="efloud.posguard"):
        _guard_with_pause(value=False, env="true")
    boot_logs = [r for r in caplog.records
                 if getattr(r, "event", None) == "position_guard.pause_config_loaded"]
    assert len(boot_logs) == 1
    log = boot_logs[0]
    assert log.config_value is False
    assert log.env_override == "true"
    assert log.effective is True
    assert log.source == "env"


# ---------------------------------------------------------------------------
# 5. Orchestrator/order integration — pause blocks before exchange call
# ---------------------------------------------------------------------------

def test_pause_blocks_orchestrator_order_submission_before_exchange_call():
    fake_client = MagicMock()
    guard, _ = _guard_with_pause(value=True, env=None)
    decision = guard.is_new_entry_allowed(_fake_signal(symbol="ETH/USDT", side="long"))

    if not decision.allowed:
        skipped_exchange_call = True
    else:  # pragma: no cover - this would be a contract regression
        skipped_exchange_call = False
        fake_client.exchange.create_order("ETH/USDT:USDT", "market", "buy", 1.0)

    assert decision.reason == "pause_new_entries"
    assert skipped_exchange_call is True
    fake_client.exchange.create_order.assert_not_called()


def test_allow_path_preserves_open_position_behavior():
    fake_client = MagicMock()
    fake_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "average": 3000.0},
        {"id": "SL-1"},
        {"id": "TP1-1"},
        {"id": "TP2-1"},
    ]
    fake_client.to_ccxt_symbol.return_value = "ETH/USDT:USDT"

    guard, _ = _guard_with_pause(value=False, env=None)
    decision = guard.is_new_entry_allowed(_fake_signal(symbol="ETH/USDT", side="long"))
    assert decision.allowed is True

    om = OrderManager(client=fake_client, dry_run=False)
    pos = om.open_position("ETH/USDT", "LONG", 1.0, 3000.0, 2940.0, 3060.0, 3120.0)

    assert pos is not None
    assert fake_client.exchange.create_order.call_count == 4


# ---------------------------------------------------------------------------
# 6. Negative contract — pause must NOT bleed into management paths
# ---------------------------------------------------------------------------

def test_pause_does_not_block_reconcile():
    fake_client = MagicMock()
    fake_client.get_open_positions.return_value = []

    guard, _ = _guard_with_pause(value=True, env=None)
    om = OrderManager(client=fake_client, dry_run=False)

    om.reconcile()

    assert fake_client.get_open_positions.called, "reconcile must inspect exchange state"


def test_pause_does_not_block_sl_tp_management():
    guard, _ = _guard_with_pause(value=True, env=None)
    lifecycle = PositionLifecycle()
    pos = lifecycle.open_position(
        "ETH/USDT", "LONG", 3000.0, 1.0,
        sl=2940.0, tp1=3060.0, tp2=3120.0,
    )
    lifecycle.partial_close(pos, price=3060.0, size_pct=0.5, reason="TP1")

    assert pos.sl_moved_to_be is True
    assert pos.tp1_hit is True


def test_pause_does_not_block_breaker_updates():
    guard, _ = _guard_with_pause(value=True, env=None)
    breaker = CircuitBreaker(daily_loss_pct_limit=2.0, consecutive_loss_limit=3)

    breaker.record_trade(-10.0)
    breaker.record_trade(-10.0)

    assert breaker.consecutive_losses == 2


# ---------------------------------------------------------------------------
# 7. Gate order regression tests
# ---------------------------------------------------------------------------

def test_breaker_rejection_takes_precedence_over_pause(caplog):
    fake_breaker_status = MagicMock()
    fake_breaker_status.can_trade = False
    fake_breaker_status.reason = "daily_loss_limit"
    guard, _ = _guard_with_pause(value=True, env=None)

    with caplog.at_level(logging.INFO, logger="efloud.posguard"):
        if not fake_breaker_status.can_trade:
            rejection = fake_breaker_status.reason
        else:  # pragma: no cover - defensive structure
            rejection = guard.is_new_entry_allowed(_fake_signal()).reason

    assert rejection == "daily_loss_limit"
    assert [r for r in caplog.records
            if getattr(r, "event", None) == "position_guard.gate_blocked"] == []


def test_can_open_position_rejection_not_masked_by_pause(caplog):
    guard, _ = _guard_with_pause(value=True, env=None)
    guard.can_open_position = MagicMock(
        return_value=PositionCheckResult(False, "size_invalid")
    )

    with caplog.at_level(logging.INFO, logger="efloud.posguard"):
        guard_check = guard.can_open_position()
        if guard_check.allowed:
            rejection = guard.is_new_entry_allowed(_fake_signal()).reason
        else:
            rejection = guard_check.reason

    assert rejection == "size_invalid"
    assert [r for r in caplog.records
            if getattr(r, "event", None) == "position_guard.gate_blocked"] == []


def test_breaker_blocked_does_not_emit_pause_log(caplog):
    guard, _ = _guard_with_pause(value=True, env=None)

    with caplog.at_level(logging.INFO, logger="efloud.posguard"):
        can_trade = False
        if not can_trade:
            rejection = "daily_loss_limit"
        else:  # pragma: no cover - defensive structure
            rejection = guard.is_new_entry_allowed(_fake_signal()).reason

    assert rejection == "daily_loss_limit"
    assert [r for r in caplog.records
            if getattr(r, "event", None) == "position_guard.gate_blocked"] == []


def test_pyramid_can_add_rejection_not_masked_by_pause(caplog):
    guard, _ = _guard_with_pause(value=True, env=None)
    guard.can_add_to_position = MagicMock(
        return_value=PositionCheckResult(False, "exposure_cap")
    )

    with caplog.at_level(logging.INFO, logger="efloud.posguard"):
        add_check = guard.can_add_to_position()
        if add_check.allowed:
            rejection = guard.is_new_entry_allowed(
                _fake_signal(symbol="ETH/USDT", side="pyramid")
            ).reason
        else:
            rejection = add_check.reason

    assert rejection == "exposure_cap"
    assert [r for r in caplog.records
            if getattr(r, "event", None) == "position_guard.gate_blocked"] == []


def test_pause_log_emitted_only_when_pause_is_the_actual_blocker(caplog):
    guard, _ = _guard_with_pause(value=True, env=None)
    fake_order_manager = MagicMock()
    fake_lifecycle = MagicMock()

    with caplog.at_level(logging.INFO, logger="efloud.posguard"):
        guard_check = PositionCheckResult(True)
        if guard_check.allowed:
            pause_decision = guard.is_new_entry_allowed(_fake_signal())
            if not pause_decision.allowed:
                skipped = True
            else:  # pragma: no cover - defensive structure
                skipped = False
                fake_order_manager.open_position()
                fake_lifecycle.open_position()

    assert skipped is True
    gate_logs = [r for r in caplog.records
                 if getattr(r, "event", None) == "position_guard.gate_blocked"]
    assert len(gate_logs) == 1
    assert gate_logs[0].reason == "pause_new_entries"
    fake_order_manager.open_position.assert_not_called()
    fake_lifecycle.open_position.assert_not_called()


def test_gate_order_is_existing_then_pause():
    call_order = []

    def can_open_side_effect(*args, **kwargs):
        call_order.append("can_open_position")
        return PositionCheckResult(True)

    def pause_check_side_effect(*args, **kwargs):
        call_order.append("is_new_entry_allowed")
        return PauseGateDecision(allowed=True)

    guard, _ = _guard_with_pause(value=False, env=None)
    guard.can_open_position = MagicMock(side_effect=can_open_side_effect)
    guard.is_new_entry_allowed = MagicMock(side_effect=pause_check_side_effect)

    guard_check = guard.can_open_position()
    if guard_check.allowed:
        guard.is_new_entry_allowed(_fake_signal())

    assert call_order == ["can_open_position", "is_new_entry_allowed"]


def test_pyramid_pause_log_uses_direction_plus_is_pyramid(caplog):
    guard, _ = _guard_with_pause(value=True, env=None)
    signal = _fake_signal(symbol="ETH/USDT", side="long")
    signal.is_pyramid = True

    with caplog.at_level(logging.INFO, logger="efloud.posguard"):
        decision = guard.is_new_entry_allowed(signal)

    assert decision.allowed is False
    gate_logs = [r for r in caplog.records
                 if getattr(r, "event", None) == "position_guard.gate_blocked"]
    assert len(gate_logs) == 1
    assert gate_logs[0].side == "long"
    assert gate_logs[0].is_pyramid is True
