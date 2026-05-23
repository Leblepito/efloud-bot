"""SMC v2 telemetry on exchange.Position + OrderManager.open_position (PR #S5).

Mirrors lifecycle.Position contract — 4 nullable telemetry fields, all
forward-compatible. v1 callers omit the kwargs; v2 (PR #71) passes them.
"""
from __future__ import annotations

import pytest

from exchange import Position, OrderManager


def test_exchange_position_telemetry_fields_default_none():
    p = Position(
        symbol="ETH/USDT", direction="LONG", entry=100.0,
        sl=95.0, tp1=110.0, tp2=120.0, size=1.0,
    )
    assert p.entry_setup_source is None
    assert p.tp1_target_type is None
    assert p.tp2_target_type is None
    assert p.bars_to_pullback is None


def test_exchange_position_accepts_telemetry_fields():
    p = Position(
        symbol="ETH/USDT", direction="LONG", entry=100.0,
        sl=95.0, tp1=110.0, tp2=120.0, size=1.0,
        entry_setup_source="FVG_PULLBACK",
        tp1_target_type="LIQUIDITY",
        tp2_target_type="FVG_FAR",
        bars_to_pullback=4,
    )
    assert p.entry_setup_source == "FVG_PULLBACK"
    assert p.tp1_target_type == "LIQUIDITY"
    assert p.tp2_target_type == "FVG_FAR"
    assert p.bars_to_pullback == 4


def test_order_manager_open_position_dry_run_threads_telemetry(tmp_path):
    """In dry_run, OrderManager.open_position constructs a Position; telemetry
    kwargs (PR #S5) must round-trip to the dataclass."""
    om = OrderManager(client=None, dry_run=True, state_dir=str(tmp_path))
    pos = om.open_position(
        symbol="ETH/USDT", direction="LONG", size=1.0,
        entry=100.0, sl=95.0, tp1=110.0, tp2=120.0,
        entry_setup_source="OTE_RETRACE",
        tp1_target_type="FVG_NEAR",
        tp2_target_type="FIB_EXT",
        bars_to_pullback=2,
    )
    assert pos is not None
    assert pos.entry_setup_source == "OTE_RETRACE"
    assert pos.tp1_target_type == "FVG_NEAR"
    assert pos.tp2_target_type == "FIB_EXT"
    assert pos.bars_to_pullback == 2


def test_order_manager_open_position_dry_run_telemetry_optional(tmp_path):
    """Legacy v1 path: omit telemetry kwargs, must still work."""
    om = OrderManager(client=None, dry_run=True, state_dir=str(tmp_path))
    pos = om.open_position(
        symbol="ETH/USDT", direction="LONG", size=1.0,
        entry=100.0, sl=95.0, tp1=110.0, tp2=120.0,
    )
    assert pos is not None
    assert pos.entry_setup_source is None
    assert pos.bars_to_pullback is None
