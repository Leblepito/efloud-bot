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
    assert price == max(102, 105)  # max(open, tp1) = 105 — but TP for LONG is sell, so adverse = MIN. Re-check: for LONG TP, _adverse_fill returns max(open, trigger). 102 < 105 so max=105.


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
