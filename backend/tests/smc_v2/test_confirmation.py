"""Tests for smc_v2.confirmation — LTF entry confirmation.

Per spec §4.1:
  For SHORT: 15m bearish engulfing close inside zone → confirmed.
  For LONG:  15m bullish engulfing close inside zone → confirmed.

Bearish engulfing: prior bar bullish (close > open); current bar bearish
                   (close < open); current open >= prior close; current
                   close <= prior open. Body fully engulfs prior body.
Bullish engulfing: mirror.

Bars at or before `since_ts` are ignored (we only look for confirmations
after the CHoCH trigger that birthed the setup).
"""
import pandas as pd
import pytest

from engine.smc_v2.zones import ZoneSpec


def _make_df(rows):
    """Build a minimal DataFrame from a list of (ts, open, high, low, close).
    `ts` is ms epoch int; DataFrame index is DatetimeIndex (UTC)."""
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.set_index("ts", inplace=True)
    return df


class TestConfirmEntryShort:
    """SHORT: bearish engulfing close inside zone."""

    def test_bearish_engulf_in_zone_confirms(self):
        from engine.smc_v2.confirmation import confirm_entry
        # Zone: [100, 110]. Confirming bar close at 102 (inside).
        # Prior bullish (104→105.5), current bearish engulf (106→102).
        # cur.open=106 >= prior.close=105.5 ✓; cur.close=102 <= prior.open=104 ✓.
        rows = [
            (1_000, 95.0, 96.0, 94.0, 95.5),
            (2_000, 96.0, 97.0, 95.0, 96.5),
            (3_000, 97.0, 105.0, 96.5, 104.0),
            (4_000, 104.0, 106.0, 102.5, 105.5),  # prior bullish
            (5_000, 106.0, 106.5, 101.0, 102.0),  # bearish engulfing
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=2_500,
        )
        assert confirmed is True
        assert entry_price == 102.0

    def test_bullish_bar_does_not_confirm_short(self):
        """A bullish bar inside the zone is NOT a SHORT confirmation."""
        from engine.smc_v2.confirmation import confirm_entry
        rows = [
            (1_000, 95.0, 96.0, 94.0, 95.5),
            (2_000, 105.0, 110.0, 100.0, 108.0),  # bullish inside zone
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=1_500,
        )
        assert confirmed is False
        assert entry_price is None

    def test_engulf_outside_zone_does_not_confirm(self):
        """A bearish engulfing whose close is OUTSIDE the zone is rejected."""
        from engine.smc_v2.confirmation import confirm_entry
        # Prior bullish (95→96); current bearish engulf (97→94).
        # cur.open=97 >= prior.close=96 ✓; cur.close=94 <= prior.open=95 ✓.
        # close=94 OUTSIDE [100, 110].
        rows = [
            (1_000, 95.0, 97.0, 94.0, 96.0),  # prior bullish
            (2_000, 97.0, 97.5, 93.0, 94.0),  # bearish engulf, close=94 OUT
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=500,
        )
        assert confirmed is False

    def test_engulf_before_since_ts_ignored(self):
        """A bearish engulfing BEFORE since_ts is ignored."""
        from engine.smc_v2.confirmation import confirm_entry
        # Prior bullish (95→95.5); current bearish engulf (96→92) BEFORE trigger.
        # cur.open=96 >= prior.close=95.5 ✓; cur.close=92 <= prior.open=95 ✓.
        # close=92 in [100,110]? No, but the test point is since_ts skip.
        # Make it land in-zone but BEFORE trigger so we can verify skip.
        # Reframe: zone [90, 95]; engulf close=92 inside zone, but at ts=2000
        # which is BEFORE since_ts=2500 → ignored.
        rows = [
            (1_000, 95.0, 96.0, 94.0, 95.5),    # prior bullish
            (2_000, 96.0, 96.5, 91.0, 92.0),    # bearish engulf @ 92 inside zone
            (3_000, 100.0, 101.0, 99.0, 100.5),
            (4_000, 101.0, 102.0, 100.5, 101.8),
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=90.0, high=95.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=2_500,
        )
        # Engulf at ts=2000 is before since_ts=2500 → ignored
        assert confirmed is False

    def test_first_confirmation_returns_immediately(self):
        """If multiple engulfings exist, return the FIRST (earliest) one."""
        from engine.smc_v2.confirmation import confirm_entry
        # First engulf at ts=3000: prior bullish (100→108), current bearish (109→105).
        # cur.open=109 >= prior.close=108 ✓; cur.close=105 <= prior.open=100? ✗
        # Reframe to ensure first engulf is actually a valid engulf:
        # prior (104→105.5 bullish), current (106→102 bearish engulf) at ts=3000.
        # Later engulf at ts=5000 should NOT be picked.
        rows = [
            (1_000, 95.0, 96.0, 94.0, 95.5),
            (2_000, 104.0, 106.0, 102.5, 105.5),  # prior bullish (for ts=3000)
            (3_000, 106.0, 106.5, 101.0, 102.0),  # FIRST bearish engulf @ 102
            (4_000, 102.0, 104.0, 101.5, 103.5),  # prior bullish (for ts=5000)
            (5_000, 104.0, 104.5, 100.5, 101.0),  # second engulf — should NOT be picked
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=1_500,
        )
        assert confirmed is True
        assert entry_price == 102.0  # FIRST engulf, not later


class TestConfirmEntryLong:
    """LONG: bullish engulfing close inside zone (mirror of SHORT)."""

    def test_bullish_engulf_in_zone_confirms(self):
        from engine.smc_v2.confirmation import confirm_entry
        # Prior bearish (92→91 small body); current bullish engulf (90.5→92.5).
        # cur.open=90.5 <= prior.close=91 ✓; cur.close=92.5 >= prior.open=92 ✓.
        # close=92.5 in zone [90, 95] ✓.
        rows = [
            (1_000, 100.0, 101.0, 99.0, 99.5),
            (2_000, 92.0, 92.5, 90.5, 91.0),    # prior bearish
            (3_000, 90.5, 92.7, 90.3, 92.5),    # bullish engulf inside zone
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=90.0, high=95.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="LONG", since_ts=1_500,
        )
        assert confirmed is True
        assert entry_price == 92.5

    def test_bearish_bar_does_not_confirm_long(self):
        from engine.smc_v2.confirmation import confirm_entry
        rows = [
            (1_000, 95.0, 96.0, 94.0, 95.5),
            (2_000, 93.0, 94.0, 88.0, 89.0),  # bearish inside zone
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=85.0, high=95.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="LONG", since_ts=500,
        )
        assert confirmed is False


class TestConfirmEntryEdgeCases:
    def test_empty_dataframe_returns_no_confirm(self):
        from engine.smc_v2.confirmation import confirm_entry
        df = _make_df([])
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=1_000,
        )
        assert confirmed is False
        assert entry_price is None

    def test_single_bar_cannot_engulf(self):
        """Engulfing requires 2 bars (prior + current). A single bar can't confirm."""
        from engine.smc_v2.confirmation import confirm_entry
        rows = [
            (2_000, 106.0, 107.0, 101.0, 102.0),
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=1_500,
        )
        assert confirmed is False
