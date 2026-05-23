"""Tests for smc_v2.swing_anchor — HTF swing anchor selection.

Per spec §10 #1:
  Return the most recent unbroken HTF swing on the 'wrong side' of the trade.
  'Unbroken' means: no HTF bar with ordinal > swing.idx has traded through
  the swing's price level.

  For SHORT: wrong side = swing_highs above entry. Unbroken = no bar.high > price.
  For LONG:  wrong side = swing_lows below entry. Unbroken = no bar.low < price.

  Returns the swing's price (float) or None if no unbroken swing exists.
  When None, the caller (PR #S3b sl_calc invocation) raises SLTooFarError.

API contract: ordinal-only axis. Both `trigger_idx` and `bar.ordinal` are
int positions in the HTF DataFrame (NOT timestamps). Mixing ts (ms-epoch)
with idx will silently fail. See test_production_shape_with_dataframe_row
for the calling convention PR #S3b will use.
"""
from dataclasses import dataclass
import pytest

from engine.smc import Swing


@dataclass
class FakeBar:
    """Minimal HTF bar shape: only needs `ordinal`, `high`, `low`.
    `.ordinal` is an int bar position (NOT a timestamp). Mirrors a row of
    an HTF OHLC DataFrame after enumeration."""
    ordinal: int
    high: float
    low: float


class TestSelectHTFSwingAnchorShort:
    """SHORT trade: wrong side = swing_highs ABOVE entry."""

    def test_picks_most_recent_unbroken_swing_high(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {
            "swing_highs": [
                Swing(price=100.0, idx=10, ts="t1", is_high=True),
                Swing(price=110.0, idx=20, ts="t2", is_high=True),  # most recent unbroken
                Swing(price=105.0, idx=15, ts="t3", is_high=True),
            ],
            "swing_lows": [],
        }
        bars = [
            FakeBar(ordinal=1, high=99, low=95),
            FakeBar(ordinal=2, high=100, low=96),
            FakeBar(ordinal=3, high=105, low=99),
            FakeBar(ordinal=4, high=108, low=100),
        ]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="SHORT",
            trigger_idx=25,   # AFTER all swings (max idx=20)
            htf_bars=bars,
        )
        assert result == 110.0

    def test_skips_broken_recent_swing_picks_earlier_unbroken(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {
            "swing_highs": [
                Swing(price=120.0, idx=5, ts="t1", is_high=True),    # earlier
                Swing(price=110.0, idx=15, ts="t2", is_high=True),   # recent
            ],
            "swing_lows": [],
        }
        bars = [
            FakeBar(ordinal=10, high=119, low=100),   # after swing@5: 119 < 120 → 120 unbroken
            FakeBar(ordinal=20, high=113, low=108),   # after swing@15: 113 > 110 → 110 broken
        ]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="SHORT",
            trigger_idx=25,
            htf_bars=bars,
        )
        # 110 (most recent) broken by bar@20; 120 still unbroken
        assert result == 120.0

    def test_returns_none_when_all_swings_broken(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {
            "swing_highs": [
                Swing(price=100.0, idx=5, ts="t1", is_high=True),
                Swing(price=105.0, idx=10, ts="t2", is_high=True),
            ],
            "swing_lows": [],
        }
        bars = [
            FakeBar(ordinal=12, high=106, low=100),   # breaks both 100 and 105
            FakeBar(ordinal=15, high=110, low=102),
        ]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="SHORT",
            trigger_idx=20,
            htf_bars=bars,
        )
        assert result is None

    def test_returns_none_when_no_swings(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {"swing_highs": [], "swing_lows": []}
        bars = [FakeBar(ordinal=1, high=100, low=90)]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="SHORT",
            trigger_idx=2,
            htf_bars=bars,
        )
        assert result is None

    def test_ignores_swings_formed_after_trigger(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {
            "swing_highs": [
                Swing(price=100.0, idx=5, ts="t1", is_high=True),
                Swing(price=115.0, idx=20, ts="t2", is_high=True),  # AFTER trigger
            ],
            "swing_lows": [],
        }
        bars = [FakeBar(ordinal=i, high=95, low=90) for i in range(25)]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="SHORT",
            trigger_idx=10,
            htf_bars=bars,
        )
        assert result == 100.0


class TestSelectHTFSwingAnchorLong:
    """LONG trade: wrong side = swing_lows BELOW entry. Mirror of SHORT."""

    def test_picks_most_recent_unbroken_swing_low(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {
            "swing_highs": [],
            "swing_lows": [
                Swing(price=100.0, idx=10, ts="t1", is_high=False),
                Swing(price=95.0, idx=20, ts="t2", is_high=False),
            ],
        }
        bars = [
            FakeBar(ordinal=1, high=110, low=100),
            FakeBar(ordinal=2, high=105, low=99),
            FakeBar(ordinal=3, high=103, low=96),
        ]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="LONG",
            trigger_idx=25,
            htf_bars=bars,
        )
        assert result == 95.0

    def test_long_skips_broken_picks_earlier(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {
            "swing_highs": [],
            "swing_lows": [
                Swing(price=80.0, idx=5, ts="t1", is_high=False),    # earlier
                Swing(price=90.0, idx=15, ts="t2", is_high=False),   # recent
            ],
        }
        bars = [
            FakeBar(ordinal=10, high=100, low=85),   # after swing@5: 85 > 80 → 80 unbroken
            FakeBar(ordinal=20, high=91, low=88),    # after swing@15: 88 < 90 → 90 broken
        ]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="LONG",
            trigger_idx=25,
            htf_bars=bars,
        )
        # 90 (most recent) broken by bar@20; 80 still unbroken (low=85 > 80)
        assert result == 80.0


class TestProductionShapeContract:
    """Lock the calling convention PR #S3b will use: convert HTF DataFrame
    rows to (ordinal, high, low) tuples, then pass alongside Swing.idx
    (which is already an int from SMCEngine.swings()).

    This test guards against silently introducing ms-epoch values as
    `ordinal` — the comparison would always be `huge > small_int` = True
    for SHORT, causing every swing to look broken.
    """

    def test_production_shape_with_dataframe_row(self):
        """Construct a realistic HTF DataFrame, convert to BarLike sequence,
        verify ordinal coercion is correct."""
        from dataclasses import dataclass
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        import pandas as pd
        from datetime import datetime, timezone

        # Simulate an HTF DataFrame with 30 bars and real ms-epoch timestamps
        idx = pd.date_range(
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            periods=30, freq="4h", tz="UTC",
        )
        df = pd.DataFrame({
            "high": [100.0 + i for i in range(30)],
            "low": [90.0 + i for i in range(30)],
        }, index=idx)

        # PR #S3b conversion pattern: enumerate to get ordinal positions
        @dataclass
        class BarRow:
            ordinal: int
            high: float
            low: float

        bars = [
            BarRow(ordinal=i, high=row["high"], low=row["low"])
            for i, (_, row) in enumerate(df.iterrows())
        ]
        # Sanity: ordinal is a small int (0..29), NOT a ms-epoch
        assert bars[0].ordinal == 0
        assert bars[-1].ordinal == 29
        assert isinstance(bars[0].ordinal, int)
        assert bars[0].ordinal < 100  # nowhere near 1.7e12 ms-epoch

        # Swing at ordinal 5 with price=200 (above all bar highs); never broken
        swings = {
            "swing_highs": [
                Swing(price=200.0, idx=5, ts=str(idx[5]), is_high=True),
            ],
            "swing_lows": [],
        }
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="SHORT",
            trigger_idx=29,
            htf_bars=bars,
        )
        # 200 is never breached by any bar.high (max is 100+29=129)
        assert result == 200.0
