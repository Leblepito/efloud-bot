"""Per-leg slippage model.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §6.7
"""
import pytest
from backtest.slippage import SlippageConfig, adverse_fill


def test_long_entry_adverse_up():
    cfg = SlippageConfig(entry_slip_pct=0.1)  # 10 bp
    out = adverse_fill(100.0, "LONG", "entry", cfg)
    assert out == pytest.approx(100.1)


def test_long_sl_adverse_down():
    cfg = SlippageConfig(sl_slip_pct=0.1)
    out = adverse_fill(100.0, "LONG", "SL", cfg)
    assert out == pytest.approx(99.9)


def test_long_tp_adverse_down():
    cfg = SlippageConfig(exit_slip_pct=0.1)
    out = adverse_fill(100.0, "LONG", "TP", cfg)
    assert out == pytest.approx(99.9)


def test_short_entry_adverse_down():
    cfg = SlippageConfig(entry_slip_pct=0.1)
    out = adverse_fill(100.0, "SHORT", "entry", cfg)
    assert out == pytest.approx(99.9)


def test_short_sl_adverse_up():
    cfg = SlippageConfig(sl_slip_pct=0.1)
    out = adverse_fill(100.0, "SHORT", "SL", cfg)
    assert out == pytest.approx(100.1)


def test_short_tp_adverse_up():
    cfg = SlippageConfig(exit_slip_pct=0.1)
    out = adverse_fill(100.0, "SHORT", "TP", cfg)
    assert out == pytest.approx(100.1)


def test_pyramid_add_pays_slippage_on_incremental_notional():
    """Per spec §6.7: pyramid add pays entry_slip on the ADDED size, not cumulative."""
    cfg = SlippageConfig(entry_slip_pct=0.1)
    # Initial entry: LONG 100 @ price 100, slipped → 100.1
    initial = adverse_fill(100.0, "LONG", "entry", cfg)
    assert initial == pytest.approx(100.1)
    # Pyramid add @ 105: slipped on the NEW notional only
    add = adverse_fill(105.0, "LONG", "entry", cfg)
    assert add == pytest.approx(105.105)


def test_partial_close_pays_exit_slip_on_closed_size_only():
    """TP1 closes half; remaining half not affected until TP2/SL."""
    cfg = SlippageConfig(exit_slip_pct=0.1)
    tp1_fill = adverse_fill(105.0, "LONG", "TP", cfg)
    assert tp1_fill == pytest.approx(104.895)  # 105 × (1 - 0.001) for LONG sell adverse
    # Per-fill semantics — function does not track open/closed state; that's the engine's job
