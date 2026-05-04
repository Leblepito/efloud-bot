"""Funding fee application — 4-case sign table.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §6.5
"""
import pytest
import pandas as pd
from backtest.funding import compute_funding_delta, funding_events_in_range


@pytest.mark.parametrize("direction,rate,expected_sign", [
    ("LONG",  +0.0001, -1),  # long PAYS positive funding → balance decreases
    ("LONG",  -0.0001, +1),  # long RECEIVES negative funding → balance increases
    ("SHORT", +0.0001, +1),  # short RECEIVES positive funding → balance increases
    ("SHORT", -0.0001, -1),  # short PAYS negative funding → balance decreases
])
def test_funding_sign_convention(direction, rate, expected_sign):
    delta = compute_funding_delta(notional=1000.0, direction=direction, funding_rate=rate)
    if expected_sign > 0:
        assert delta > 0
    else:
        assert delta < 0
    assert abs(delta) == pytest.approx(0.1)  # 1000 × 0.0001
