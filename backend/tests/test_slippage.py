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
