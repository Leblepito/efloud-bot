"""Characterization tests for `risk.calc_position_size` / `calc_fixed_position_size`.

`risk/` had no direct test (REGRESSION.md ledger gap, T-20261107-12). These pin
the current sizing math; they do not change it.
"""
from __future__ import annotations

import pytest

from risk import calc_fixed_position_size, calc_position_size


def test_risk_based_size_is_risk_amount_over_sl_distance():
    # 1000 * 1.5% = 15 USDT risk, SL 2 away -> 7.5 contracts
    assert calc_position_size(1000, 1.5, entry=100, sl=98) == pytest.approx(7.5)


def test_short_side_uses_absolute_sl_distance():
    assert calc_position_size(1000, 1.5, entry=100, sl=102) == pytest.approx(7.5)


def test_notional_cap_wins_when_smaller():
    # cap = 1000 * 3% * 10x = 300 USDT notional -> 3 contracts (< 7.5)
    size = calc_position_size(1000, 1.5, entry=100, sl=98, leverage=10, max_notional_pct=3.0)
    assert size == pytest.approx(3.0)


def test_notional_cap_ignored_when_larger():
    size = calc_position_size(1000, 1.5, entry=100, sl=98, leverage=10, max_notional_pct=50.0)
    assert size == pytest.approx(7.5)


def test_zero_sl_distance_returns_zero():
    assert calc_position_size(1000, 1.5, entry=100, sl=100) == 0.0


def test_zero_balance_returns_zero():
    assert calc_position_size(0, 1.5, entry=100, sl=98) == 0.0


def test_fixed_size_is_margin_times_leverage_over_entry():
    assert calc_fixed_position_size(100, entry=50, leverage=10) == pytest.approx(20.0)


@pytest.mark.parametrize("entry", [0, -1])
def test_fixed_size_non_positive_entry_returns_zero(entry):
    assert calc_fixed_position_size(100, entry=entry, leverage=10) == 0.0
