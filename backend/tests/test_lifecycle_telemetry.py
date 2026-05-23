"""SMC v2 telemetry on engine.lifecycle.Position (PR #S5).

Adds 4 nullable fields:
- entry_setup_source: "FVG_PULLBACK" | "OTE_RETRACE" | "V1_LEGACY" | None
- tp1_target_type:    "LIQUIDITY" | "FVG_NEAR" | "RR_PROJECTION" | None
- tp2_target_type:    "FVG_FAR" | "FIB_EXT" | "NONE" | None
- bars_to_pullback:   int | None

All forward-compatible: v1 path writes None throughout, single-target close
branch (tp2=None) is dormant in prod until v2 emits it (PR #S6 flips flag).
"""
from __future__ import annotations

from engine.lifecycle import Position, PositionLifecycle


# ────────────────────────────────────────────────────────────────────
# Section: Position dataclass fields
# ────────────────────────────────────────────────────────────────────

def test_position_telemetry_fields_default_none():
    p = Position(id="x", symbol="ETH/USDT", direction="LONG")
    assert p.entry_setup_source is None
    assert p.tp1_target_type is None
    assert p.tp2_target_type is None
    assert p.bars_to_pullback is None


def test_position_to_full_dict_roundtrip_with_telemetry():
    p = Position(
        id="x", symbol="ETH/USDT", direction="LONG",
        entry_setup_source="FVG_PULLBACK",
        tp1_target_type="LIQUIDITY",
        tp2_target_type="FVG_FAR",
        bars_to_pullback=3,
    )
    d = p.to_full_dict()
    p2 = Position.from_full_dict(d)
    assert p2.entry_setup_source == "FVG_PULLBACK"
    assert p2.tp1_target_type == "LIQUIDITY"
    assert p2.tp2_target_type == "FVG_FAR"
    assert p2.bars_to_pullback == 3


def test_position_from_full_dict_missing_keys_default_none():
    """Backwards-compat: old state files lack telemetry keys."""
    d = {
        "id": "x", "symbol": "ETH/USDT", "direction": "LONG",
        "entries": [], "exits": [],
    }
    p = Position.from_full_dict(d)
    assert p.entry_setup_source is None
    assert p.tp1_target_type is None
    assert p.tp2_target_type is None
    assert p.bars_to_pullback is None


def test_open_position_accepts_telemetry_kwargs():
    lc = PositionLifecycle()
    p = lc.open_position(
        "ETH/USDT", "LONG", 100.0, 1.0, sl=95.0, tp1=110.0, tp2=120.0,
        entry_setup_source="OTE_RETRACE",
        tp1_target_type="LIQUIDITY",
        tp2_target_type="FIB_EXT",
        bars_to_pullback=5,
    )
    assert p.entry_setup_source == "OTE_RETRACE"
    assert p.tp1_target_type == "LIQUIDITY"
    assert p.tp2_target_type == "FIB_EXT"
    assert p.bars_to_pullback == 5


def test_open_position_telemetry_kwargs_optional():
    """v1 path: omitting telemetry kwargs must not break existing callers."""
    lc = PositionLifecycle()
    p = lc.open_position("ETH/USDT", "LONG", 100.0, 1.0, sl=95.0, tp1=110.0, tp2=120.0)
    assert p.entry_setup_source is None
    assert p.tp1_target_type is None
    assert p.tp2_target_type is None
    assert p.bars_to_pullback is None


# ────────────────────────────────────────────────────────────────────
# Section: Single-target close branch (tp2=None) — Task 2
# ────────────────────────────────────────────────────────────────────

def test_partial_close_single_target_full_close_on_tp1():
    """Single-target mode: when tp2 is None, TP1 fill triggers full close.

    Inert in production: only v2 (currently flag-off) emits tp2=None.
    """
    lc = PositionLifecycle()
    p = lc.open_position(
        "ETH/USDT", "LONG", 100.0, 1.0, sl=95.0, tp1=110.0, tp2=None,
    )
    assert p.tp2 is None
    result = lc.partial_close(p, 110.0, 0.5, reason="TP1")
    assert result is True
    assert not p.is_open  # FULL closed, not partial
    assert p.tp1_hit is True
    # Only one exit (close_position writes TP1 with 100% size, no BE move)
    assert len(p.exits) == 1
    assert p.exits[0].reason == "TP1"
    # SL must NOT have been moved to BE (we did a full close, not a BE step)
    assert p.sl_moved_to_be is False


def test_partial_close_two_target_unchanged():
    """Regression: two-target mode (v1 default) keeps old behavior."""
    lc = PositionLifecycle()
    p = lc.open_position(
        "ETH/USDT", "LONG", 100.0, 1.0, sl=95.0, tp1=110.0, tp2=120.0,
    )
    assert p.tp2 == 120.0
    lc.partial_close(p, 110.0, 0.5, reason="TP1")
    assert p.is_open  # half remaining
    assert p.tp1_hit is True
    assert p.sl_moved_to_be is True
    assert p.sl == 100.0  # moved to entry


def test_partial_close_single_target_non_tp1_reason_unchanged():
    """A WEAKNESS partial on a single-target Position is still partial,
    not full close — the single-target branch is TP1-specific."""
    lc = PositionLifecycle()
    p = lc.open_position(
        "ETH/USDT", "LONG", 100.0, 1.0, sl=95.0, tp1=110.0, tp2=None,
    )
    lc.partial_close(p, 103.0, 0.3, reason="WEAKNESS")
    assert p.is_open  # 70% remaining
    assert p.tp1_hit is False
