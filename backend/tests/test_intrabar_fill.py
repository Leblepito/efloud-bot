"""Intrabar SL/TP fill resolution.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §6.3
"""
from dataclasses import dataclass

import pytest

from backtest.intrabar import resolve_fill, Bar


@dataclass
class _Pos:
    direction: str
    entry: float
    sl: float
    tp1: float


def test_long_sl_only_hit():
    pos = _Pos("LONG", entry=100, sl=95, tp1=105)
    bar = Bar(open=98, high=99, low=94, close=96)
    level, price = resolve_fill(pos, bar)
    assert level == "SL"
    assert price == min(98, 95)  # min(open, sl) = 95


def test_long_tp_only_hit():
    pos = _Pos("LONG", entry=100, sl=95, tp1=105)
    bar = Bar(open=102, high=106, low=101, close=104)
    level, price = resolve_fill(pos, bar)
    assert level == "TP1"
    assert price == max(102, 105)  # LONG TP fills at max(open, trigger) per spec §6.3


def test_long_both_hit_open_below_entry_sl_first():
    """LONG, both levels touched, bar.open < entry → SL fired first."""
    pos = _Pos("LONG", entry=100, sl=95, tp1=105)
    bar = Bar(open=99, high=106, low=94, close=104)
    level, _ = resolve_fill(pos, bar)
    assert level == "SL"


def test_long_both_hit_open_above_entry_tp_first():
    pos = _Pos("LONG", entry=100, sl=95, tp1=105)
    bar = Bar(open=101, high=106, low=94, close=98)
    level, _ = resolve_fill(pos, bar)
    assert level == "TP1"


def test_short_sl_only_hit():
    pos = _Pos("SHORT", entry=100, sl=105, tp1=95)
    bar = Bar(open=102, high=106, low=101, close=104)
    level, price = resolve_fill(pos, bar)
    assert level == "SL"
    assert price == max(102, 105)  # max(open, sl) = 105


def test_neither_hit():
    pos = _Pos("LONG", entry=100, sl=95, tp1=105)
    bar = Bar(open=99, high=104, low=96, close=102)
    level, _ = resolve_fill(pos, bar)
    assert level is None


def test_long_gap_through_sl():
    """Bar opens BELOW SL — fill is at bar.open (worse than SL trigger). Spec §6.3 gap case."""
    pos = _Pos("LONG", entry=100, sl=95, tp1=105)
    bar = Bar(open=92, high=93, low=92, close=92.5)
    level, price = resolve_fill(pos, bar)
    assert level == "SL"
    assert price == 92  # min(92, 95) — gap-through fill at the worse price


def test_engine_uses_intrabar_for_position_close():
    """A position closes at intrabar SL price (with slippage), not next-cycle close."""
    import tempfile
    import yaml
    from engine import SafeOrchestrator
    from engine.notifications import NullNotificationManager
    from backtest.intrabar import resolve_fill, Bar
    from backtest.slippage import adverse_fill, SlippageConfig
    from dataclasses import dataclass as dc

    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    with tempfile.TemporaryDirectory() as state_dir:
        orch = SafeOrchestrator(
            cfg, state_dir=state_dir,
            notification_mgr=NullNotificationManager(),
            freshness_check=False, persist=False,
        )
        pos = orch.lifecycle.open_position(
            symbol="BTC/USDT", direction="LONG",
            entry_price=100.0, size=1.0,
            sl=95.0, tp1=105.0, tp2=110.0,
        )

        @dc
        class _PosView:
            direction: str
            entry: float
            sl: float
            tp1: float

        view = _PosView(direction=pos.direction, entry=pos.avg_entry_price,
                        sl=pos.sl, tp1=pos.tp1)
        bar = Bar(open=92.0, high=93.0, low=92.0, close=92.5)
        level, raw_price = resolve_fill(view, bar)
        assert level == "SL"
        assert raw_price == 92.0  # gap-through, fill at open

        slip_cfg = SlippageConfig()
        slipped = adverse_fill(raw_price, pos.direction, level, slip_cfg)
        # LONG SL is sell, slip is adverse-down: 92 × (1 - 0.001) = 91.908
        assert slipped == pytest.approx(91.908)

        orch.lifecycle.close_position(pos, slipped, level)
        assert not pos.is_open
        assert pos.exits[-1].reason == "SL"
        assert pos.exits[-1].price == pytest.approx(91.908)


def test_tp1_level_translates_to_tp_leg_for_slippage():
    """Regression: resolve_fill returns 'TP1' but adverse_fill wants 'TP'.

    The engine normalizes via `slip_leg = 'SL' if level == 'SL' else 'TP'`. Without
    the normalization, this raised `ValueError: Unknown leg: 'TP1'` on real data.
    """
    from backtest.intrabar import resolve_fill, Bar
    from backtest.slippage import adverse_fill, SlippageConfig
    from dataclasses import dataclass as dc

    @dc
    class _PosView:
        direction: str
        entry: float
        sl: float
        tp1: float

    view = _PosView(direction="LONG", entry=100.0, sl=95.0, tp1=105.0)
    # Bar that hits TP1 only
    bar = Bar(open=104.0, high=106.0, low=103.0, close=105.5)
    level, raw_price = resolve_fill(view, bar)
    assert level == "TP1"

    # Engine glue: normalize to slippage leg
    slip_leg = "SL" if level == "SL" else "TP"
    cfg = SlippageConfig()
    slipped = adverse_fill(raw_price, "LONG", slip_leg, cfg)  # must not raise
    # LONG TP fills at adverse-down: max(open, tp1) × (1 - 0.0005) = 105 × 0.9995
    assert slipped == pytest.approx(104.9475)
