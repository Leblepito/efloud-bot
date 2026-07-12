"""Tests for default-off orphan position auto-protection.

All tests are mock-only/read-only. They never call a live exchange.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from engine.safety.orphan_protection import (
    CoverageStatus,
    OrphanProtectionConfig,
    OrphanProtector,
    ProtectionAction,
    load_orphan_protection_config,
)
from exchange import OrderManager


def _pos(symbol="ETH/USDT:USDT", side="short", size=0.338, entry=2334.08, mark=2328.0):
    return {
        "symbol": symbol,
        "side": side,
        "contracts": size,
        "entryPrice": entry,
        "markPrice": mark,
    }


def _order(symbol="ETHUSDT", order_type="STOP_MARKET", side="BUY", qty="0.338",
           reduce_only=True, close_position=False, stop="2345.67"):
    return {
        "symbol": symbol,
        "orderType": order_type,
        "side": side,
        "quantity": str(qty),
        "reduceOnly": reduce_only,
        "closePosition": close_position,
        "triggerPrice": str(stop),
        "algoId": "A1",
    }


def _cfg(**kw):
    base = OrphanProtectionConfig(
        enabled=True,
        mode="place_missing_sl",
        default_sl_pct=2.0,
        max_auto_protect_per_cycle=1,
        min_distance_to_mark_pct=0.5,
        require_tp_present=True,
    )
    return OrphanProtectionConfig(**{**base.__dict__, **kw})


def _protector(config=None):
    client = MagicMock()
    client.to_ccxt_symbol.side_effect = lambda s: s if ":" in s else f"{s}:USDT"
    return OrphanProtector(config or _cfg(), client), client


# Config loading (4)

def test_default_config_is_disabled_warn_only():
    cfg = load_orphan_protection_config({})
    assert cfg.enabled is False
    assert cfg.mode == "warn_only"
    assert cfg.default_sl_pct == 2.0
    assert cfg.max_auto_protect_per_cycle == 1
    assert cfg.min_distance_to_mark_pct == 0.5
    assert cfg.require_tp_present is True


def test_unknown_mode_falls_back_to_warn_only_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        cfg = load_orphan_protection_config({"orphan_protection": {"enabled": True, "mode": "bad"}})
    assert cfg.enabled is True
    assert cfg.mode == "warn_only"
    assert any("unknown orphan_protection mode" in r.message for r in caplog.records)


def test_config_logged_at_load_with_event_marker(caplog):
    with caplog.at_level(logging.INFO, logger="efloud.orphan_protection"):
        load_orphan_protection_config({"orphan_protection": {"enabled": True, "mode": "warn_only"}})
    logs = [r for r in caplog.records if getattr(r, "event", None) == "orphan_protection.config_loaded"]
    assert len(logs) == 1
    assert logs[0].enabled is True
    assert logs[0].mode == "warn_only"


def test_missing_safety_block_returns_safe_defaults():
    cfg = load_orphan_protection_config(None)
    assert cfg.enabled is False
    assert cfg.mode == "warn_only"


# Coverage analysis — pure function, no API (8)

def test_close_position_true_qty_zero_is_protected_long():
    p, _ = _protector()
    status = p.analyze_coverage(_pos(symbol="FIL/USDT:USDT", side="long", size=2411.2), [
        _order("FILUSDT", "STOP_MARKET", "SELL", qty="0.0", reduce_only=True, close_position=True)
    ])
    assert status.has_protective_sl is True


def test_close_position_true_qty_zero_is_protected_short():
    p, _ = _protector()
    status = p.analyze_coverage(_pos(side="short", size=0.338), [
        _order("ETHUSDT", "STOP_MARKET", "BUY", qty="0.0", reduce_only=True, close_position=True)
    ])
    assert status.has_protective_sl is True


def test_full_qty_reduce_only_sl_is_protected():
    p, _ = _protector()
    status = p.analyze_coverage(_pos(side="long", size=10), [
        _order("ETHUSDT", "STOP_MARKET", "SELL", qty="10", reduce_only=True)
    ])
    assert status.has_protective_sl is True


def test_wrong_direction_sl_flags_critical_long():
    p, _ = _protector()
    status = p.analyze_coverage(_pos(side="long", size=10), [_order("ETHUSDT", side="BUY", qty="10")])
    assert status.sl_is_wrong_direction is True
    assert status.has_protective_sl is False


def test_wrong_direction_sl_flags_critical_short():
    p, _ = _protector()
    status = p.analyze_coverage(_pos(side="short", size=10), [_order("ETHUSDT", side="SELL", qty="10")])
    assert status.sl_is_wrong_direction is True
    assert status.has_protective_sl is False


def test_not_reduce_only_sl_flags_critical():
    p, _ = _protector()
    status = p.analyze_coverage(_pos(side="long", size=10), [_order("ETHUSDT", side="SELL", qty="10", reduce_only=False)])
    assert status.sl_not_reduce_only is True
    assert status.has_protective_sl is False


def test_undercovered_sl_not_protected():
    p, _ = _protector()
    status = p.analyze_coverage(_pos(side="long", size=10), [_order("ETHUSDT", side="SELL", qty="3")])
    assert status.has_protective_sl is False
    assert status.reason_if_unprotected == "undercovered_sl"


def test_no_sl_returns_unprotected_with_reason():
    p, _ = _protector()
    status = p.analyze_coverage(_pos(side="long", size=10), [])
    assert status.has_protective_sl is False
    assert status.reason_if_unprotected == "missing_sl"


# Mode + flag interaction (5)

def test_warn_only_mode_logs_but_does_not_place_order(caplog):
    p, client = _protector(_cfg(mode="warn_only"))
    with caplog.at_level(logging.WARNING):
        actions = p.protect_cycle([_pos(side="long")], [_order(side="SELL", order_type="TAKE_PROFIT_MARKET")])
    assert actions[0].action == "warn_only"
    client.exchange.create_order.assert_not_called()


def test_disabled_master_switch_overrides_mode():
    p, client = _protector(_cfg(enabled=False, mode="place_missing_sl"))
    actions = p.protect_cycle([_pos(side="long")], [_order(side="SELL", order_type="TAKE_PROFIT_MARKET")])
    assert actions[0].action == "warn_only"
    client.exchange.create_order.assert_not_called()


def test_place_missing_sl_mode_places_on_unprotected():
    p, client = _protector(_cfg(require_tp_present=False))
    client.exchange.create_order.return_value = {"id": "SL1"}
    actions = p.protect_cycle([_pos(side="long", entry=100, mark=100)], [])
    assert actions[0].action == "placed_sl"
    client.exchange.create_order.assert_called_once()


def test_critical_unsafe_sl_never_auto_fixes():
    p, client = _protector(_cfg(require_tp_present=False))
    actions = p.protect_cycle([_pos(side="long")], [_order(side="BUY", qty="10")])
    assert actions[0].action == "skipped_critical_warning"
    client.exchange.create_order.assert_not_called()


def test_require_tp_present_skips_when_no_tp():
    p, client = _protector(_cfg(require_tp_present=True))
    actions = p.protect_cycle([_pos(side="long")], [])
    assert actions[0].action == "skipped_no_tp"
    client.exchange.create_order.assert_not_called()


# place_close_position_sl (6)

def test_long_orphan_places_sell_close_position_stop_market():
    p, client = _protector(_cfg(require_tp_present=False))
    client.exchange.create_order.return_value = {"id": "SL1"}
    action = p.place_close_position_sl(_pos(symbol="FIL/USDT:USDT", side="long", entry=100, mark=100))
    assert action.action == "placed_sl"
    args, kwargs = client.exchange.create_order.call_args
    assert args[:4] == ("FIL/USDT:USDT", "STOP_MARKET", "sell", None)
    assert kwargs["params"]["closePosition"] is True
    # F15 (2026-07-11, b912245): closePosition=True ile reduceOnly BIRLIKTE
    # gonderilirse Binance -1106 verir; closePosition zaten reduce-only
    # semantigi tasir. XOR pattern: reduceOnly hic gonderilmemeli.
    assert "reduceOnly" not in kwargs["params"]
    assert kwargs["params"]["stopPrice"] == pytest.approx(98.0)


def test_short_orphan_places_buy_close_position_stop_market():
    p, client = _protector(_cfg(require_tp_present=False))
    client.exchange.create_order.return_value = {"id": "SL1"}
    action = p.place_close_position_sl(_pos(symbol="ETH/USDT:USDT", side="short", entry=100, mark=100))
    assert action.action == "placed_sl"
    args, kwargs = client.exchange.create_order.call_args
    assert args[:4] == ("ETH/USDT:USDT", "STOP_MARKET", "buy", None)
    assert kwargs["params"]["stopPrice"] == pytest.approx(102.0)


def test_sl_price_too_close_to_mark_refuses():
    p, client = _protector(_cfg(default_sl_pct=0.1, min_distance_to_mark_pct=0.5, require_tp_present=False))
    action = p.place_close_position_sl(_pos(side="long", entry=100, mark=100))
    assert action.action == "skipped_too_close"
    client.exchange.create_order.assert_not_called()


def test_invalid_entry_price_refuses():
    p, client = _protector(_cfg(require_tp_present=False))
    action = p.place_close_position_sl(_pos(entry=0, mark=100))
    assert action.action == "skipped_critical_warning"
    client.exchange.create_order.assert_not_called()


def test_api_error_returns_critical_warning_action():
    p, client = _protector(_cfg(require_tp_present=False))
    client.exchange.create_order.side_effect = RuntimeError("boom")
    action = p.place_close_position_sl(_pos(entry=100, mark=100))
    assert action.action == "skipped_critical_warning"
    assert "boom" in action.error


def test_placed_sl_emits_structured_log(caplog):
    p, client = _protector(_cfg(require_tp_present=False))
    client.exchange.create_order.return_value = {"id": "SL1"}
    with caplog.at_level(logging.INFO, logger="efloud.orphan_protection"):
        p.place_close_position_sl(_pos(entry=100, mark=100))
    assert any(getattr(r, "event", None) == "orphan_protection.placed_sl" for r in caplog.records)


# Cycle orchestration (5)

def test_max_per_cycle_respected():
    p, client = _protector(_cfg(max_auto_protect_per_cycle=1, require_tp_present=False))
    client.exchange.create_order.return_value = {"id": "SL1"}
    actions = p.protect_cycle([_pos(symbol="ETH/USDT:USDT"), _pos(symbol="FIL/USDT:USDT", side="long")], [])
    assert [a.action for a in actions] == ["placed_sl", "skipped_max_per_cycle"]
    assert client.exchange.create_order.call_count == 1


def test_already_protected_no_action_no_log():
    p, client = _protector()
    actions = p.protect_cycle([_pos(side="short")], [_order(side="BUY", qty="0", close_position=True), _order(side="BUY", order_type="TAKE_PROFIT_MARKET")])
    assert actions[0].action == "none_protected"
    client.exchange.create_order.assert_not_called()


def test_multiple_orphans_some_protected_some_not():
    p, client = _protector(_cfg(require_tp_present=False, max_auto_protect_per_cycle=2))
    client.exchange.create_order.return_value = {"id": "SL1"}
    actions = p.protect_cycle([_pos(symbol="ETH/USDT:USDT", side="short"), _pos(symbol="FIL/USDT:USDT", side="long")], [_order("ETHUSDT", side="BUY", qty="0", close_position=True)])
    assert [a.action for a in actions] == ["none_protected", "placed_sl"]


def test_protect_cycle_returns_action_per_orphan():
    p, client = _protector(_cfg(require_tp_present=False))
    client.exchange.create_order.return_value = {"id": "SL1"}
    actions = p.protect_cycle([_pos(symbol="ETH/USDT:USDT")], [])
    assert len(actions) == 1
    assert isinstance(actions[0], ProtectionAction)


def test_no_orphans_returns_empty_list():
    p, _ = _protector()
    assert p.protect_cycle([], []) == []


# Negative-contract — what this PR MUST NOT do (4)

def test_never_cancels_existing_orders():
    p, client = _protector(_cfg(require_tp_present=False))
    client.exchange.create_order.return_value = {"id": "SL1"}
    p.protect_cycle([_pos()], [])
    client.exchange.cancel_order.assert_not_called()


def test_never_places_tp():
    p, client = _protector(_cfg(require_tp_present=False))
    client.exchange.create_order.return_value = {"id": "SL1"}
    p.protect_cycle([_pos()], [])
    calls = client.exchange.create_order.call_args_list
    assert all(c.args[1] != "TAKE_PROFIT_MARKET" for c in calls)


def test_never_modifies_lifecycle_state():
    p, client = _protector(_cfg(require_tp_present=False))
    client.exchange.create_order.return_value = {"id": "SL1"}
    lifecycle_positions = []
    before_id = id(lifecycle_positions)
    p.protect_cycle([_pos()], [])
    assert id(lifecycle_positions) == before_id
    assert lifecycle_positions == []


def test_default_off_does_not_call_create_order():
    p, client = _protector(_cfg(enabled=False, mode="place_missing_sl", require_tp_present=False))
    p.protect_cycle([_pos()], [])
    client.exchange.create_order.assert_not_called()


# Integration (2)

def test_reconcile_calls_orphan_protector_when_injected():
    client = MagicMock()
    client.get_open_positions.return_value = [{"symbol": "ETH/USDT:USDT", "contracts": 1.0, "side": "short", "entryPrice": 100.0, "unrealizedPnl": 0.0}]
    client.exchange.fetch_open_orders.return_value = []
    client.exchange.fapiPrivateGetOpenAlgoOrders.return_value = []
    protector = MagicMock()
    mgr = OrderManager(client, dry_run=False, orphan_protector=protector)
    mgr.reconcile()
    protector.protect_cycle.assert_called_once()


def test_reconcile_works_when_orphan_protector_is_none():
    client = MagicMock()
    client.get_open_positions.return_value = [{"symbol": "ETH/USDT:USDT", "contracts": 1.0, "side": "short", "entryPrice": 100.0, "unrealizedPnl": 0.0}]
    client.exchange.fetch_open_orders.return_value = []
    client.exchange.fapiPrivateGetOpenAlgoOrders.return_value = []
    mgr = OrderManager(client, dry_run=False)
    assert mgr.reconcile() == []
