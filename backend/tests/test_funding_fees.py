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


def test_position_closed_between_funding_events_pays_zero():
    """Position opened 09:00, closed 13:00. Funding events at 16:00, 00:00 — none apply."""
    funding_df = pd.DataFrame(
        {"funding_rate": [0.0001, 0.0001]},
        index=pd.to_datetime(["2026-01-01 16:00", "2026-01-02 00:00"]),
    )
    events = funding_events_in_range(
        funding_df,
        start_ts=pd.Timestamp("2026-01-01 09:00"),
        end_ts=pd.Timestamp("2026-01-01 13:00"),
    )
    assert len(events) == 0


def test_multi_funding_cumulative():
    """Position open across 3 funding events → accumulates net delta correctly."""
    funding_df = pd.DataFrame(
        {"funding_rate": [0.0001, 0.0002, -0.0001]},
        index=pd.to_datetime(["2026-01-01 00:00", "2026-01-01 08:00", "2026-01-01 16:00"]),
    )
    events = funding_events_in_range(
        funding_df,
        start_ts=pd.Timestamp("2025-12-31 22:00"),
        end_ts=pd.Timestamp("2026-01-01 17:00"),
    )
    assert len(events) == 3
    # Cumulative delta for LONG, notional=1000:
    # rate=+0.0001 → -0.1 (long pays)
    # rate=+0.0002 → -0.2 (long pays)
    # rate=-0.0001 → +0.1 (long receives)
    # Net: -0.1 - 0.2 + 0.1 = -0.2
    total = sum(compute_funding_delta(notional=1000.0, direction="LONG", funding_rate=r)
                for r in events["funding_rate"])
    assert total == pytest.approx(-0.2)
