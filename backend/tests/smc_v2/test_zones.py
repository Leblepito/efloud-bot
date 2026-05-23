"""Tests for smc_v2.zones — pullback target builder."""
from typing import List
import pytest

from engine.smc import FVG


class TestZoneSpec:
    def test_zonespec_dataclass_has_low_high_source(self):
        from engine.smc_v2.zones import ZoneSpec
        z = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        assert z.low == 100.0
        assert z.high == 110.0
        assert z.source == "HTF_FVG"

    def test_zonespec_ote_source(self):
        from engine.smc_v2.zones import ZoneSpec
        z = ZoneSpec(low=95.0, high=98.0, source="OTE")
        assert z.source == "OTE"


class TestBuildPullbackZonesShort:
    """For a SHORT trade after a downward CHoCH, a pullback zone is a price
    range ABOVE the trigger price where price might retrace before the next
    leg down.

    Priority 1: nearest unmitigated BULL HTF FVG above trigger_price
    Priority 2 (fallback): OTE band (passed in directly)
    """

    def test_priority1_picks_nearest_bull_fvg_above(self):
        from engine.smc_v2.zones import build_pullback_zones
        # Two BULL FVGs above trigger; nearest one wins
        fvgs = [
            FVG(top=120.0, bot=115.0, idx=1, ts="t1", direction="BULL"),
            FVG(top=110.0, bot=107.0, idx=2, ts="t2", direction="BULL"),  # nearest
        ]
        ote_band = (95.0, 98.0)  # below; ignored when FVG available
        zone = build_pullback_zones(
            htf_fvgs=fvgs,
            ote_band=ote_band,
            direction="SHORT",
            trigger_price=100.0,
        )
        # Nearest by `bot` distance from trigger_price
        assert zone.low == 107.0
        assert zone.high == 110.0
        assert zone.source == "HTF_FVG"

    def test_priority2_falls_back_to_ote_when_no_fvg(self):
        from engine.smc_v2.zones import build_pullback_zones
        zone = build_pullback_zones(
            htf_fvgs=[],
            ote_band=(105.0, 108.0),
            direction="SHORT",
            trigger_price=100.0,
        )
        assert zone.low == 105.0
        assert zone.high == 108.0
        assert zone.source == "OTE"

    def test_bear_fvgs_ignored_for_short_setup(self):
        """For SHORT we look for BULL FVGs above (counter-direction gap).
        BEAR FVGs (impulse-direction) are not pullback targets."""
        from engine.smc_v2.zones import build_pullback_zones
        fvgs = [
            FVG(top=115.0, bot=110.0, idx=1, ts="t1", direction="BEAR"),
        ]
        zone = build_pullback_zones(
            htf_fvgs=fvgs,
            ote_band=(105.0, 108.0),
            direction="SHORT",
            trigger_price=100.0,
        )
        assert zone.source == "OTE"  # falls back

    def test_fvg_below_trigger_ignored_for_short(self):
        from engine.smc_v2.zones import build_pullback_zones
        # BULL FVG but below trigger — wrong side for SHORT pullback
        fvgs = [
            FVG(top=95.0, bot=92.0, idx=1, ts="t1", direction="BULL"),
        ]
        zone = build_pullback_zones(
            htf_fvgs=fvgs,
            ote_band=(105.0, 108.0),
            direction="SHORT",
            trigger_price=100.0,
        )
        assert zone.source == "OTE"


class TestBuildPullbackZonesLong:
    """Mirror of SHORT: pullback target for LONG is BELOW trigger.
    Priority 1: nearest unmitigated BEAR HTF FVG below trigger_price.
    """

    def test_priority1_picks_nearest_bear_fvg_below(self):
        from engine.smc_v2.zones import build_pullback_zones
        fvgs = [
            FVG(top=85.0, bot=80.0, idx=1, ts="t1", direction="BEAR"),
            FVG(top=92.0, bot=89.0, idx=2, ts="t2", direction="BEAR"),  # nearest
        ]
        zone = build_pullback_zones(
            htf_fvgs=fvgs,
            ote_band=(102.0, 105.0),  # above; wrong side; ignored
            direction="LONG",
            trigger_price=100.0,
        )
        assert zone.low == 89.0
        assert zone.high == 92.0
        assert zone.source == "HTF_FVG"

    def test_priority2_falls_back_to_ote_for_long(self):
        from engine.smc_v2.zones import build_pullback_zones
        zone = build_pullback_zones(
            htf_fvgs=[],
            ote_band=(92.0, 95.0),
            direction="LONG",
            trigger_price=100.0,
        )
        assert zone.source == "OTE"


class TestIsPriceInZone:
    def test_price_inside_zone(self):
        from engine.smc_v2.zones import ZoneSpec, is_price_in_zone
        z = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        assert is_price_in_zone(105.0, z) is True

    def test_price_at_low_edge_is_inside(self):
        from engine.smc_v2.zones import ZoneSpec, is_price_in_zone
        z = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        assert is_price_in_zone(100.0, z) is True

    def test_price_at_high_edge_is_inside(self):
        from engine.smc_v2.zones import ZoneSpec, is_price_in_zone
        z = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        assert is_price_in_zone(110.0, z) is True

    def test_price_below_low_is_outside(self):
        from engine.smc_v2.zones import ZoneSpec, is_price_in_zone
        z = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        assert is_price_in_zone(99.99, z) is False

    def test_price_above_high_is_outside(self):
        from engine.smc_v2.zones import ZoneSpec, is_price_in_zone
        z = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        assert is_price_in_zone(110.01, z) is False
