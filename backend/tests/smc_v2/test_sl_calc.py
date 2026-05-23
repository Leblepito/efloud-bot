"""Tests for smc_v2.sl_calc — structural SL computation.

Behavior (spec §5.1):
1. Structural SL = (zone outer edge or HTF swing anchor, whichever is further)
                   ± sl_atr_buffer * ATR(15m)
2. Then clamp:
   - If stop_dist < min_sl_atr * ATR: widen to min_sl_atr (ATR floor)
   - If stop_dist > max_sl_atr * ATR: RAISE SLTooFarError (don't clamp — reject)
"""
from dataclasses import dataclass
import pytest

from engine.smc_v2.zones import ZoneSpec
from engine.smc_v2.exceptions import SLTooFarError


@dataclass
class FakeSafetyConfig:
    """Minimal config shape consumed by calc_sl."""
    sl_atr_buffer: float = 0.5
    min_sl_atr: float = 0.5
    max_sl_atr: float = 5.0


class TestCalcSLShort:
    """SHORT SL = above entry; structural side is zone.high or htf_swing_anchor."""

    def test_structural_uses_max_of_zone_and_swing_plus_buffer(self):
        from engine.smc_v2.sl_calc import calc_sl
        # zone.high = 110, swing anchor = 115 (further), buffer = 0.5 * ATR(4) = 2
        sl = calc_sl(
            direction="SHORT",
            entry_price=100.0,
            zone=ZoneSpec(low=105.0, high=110.0, source="HTF_FVG"),
            htf_swing_anchor=115.0,
            atr_15m=4.0,
            config=FakeSafetyConfig(),
        )
        # max(110, 115) + 0.5*4 = 117
        assert sl == pytest.approx(117.0, rel=1e-6)

    def test_zone_wins_when_higher_than_swing(self):
        from engine.smc_v2.sl_calc import calc_sl
        # zone.high=120, swing=112, ATR=10 (large enough so stop_dist <= max_dist)
        # structural = max(120, 112) + 0.5*10 = 125 → stop_dist=25; max_dist=5*10=50 ✓
        sl = calc_sl(
            direction="SHORT",
            entry_price=100.0,
            zone=ZoneSpec(low=115.0, high=120.0, source="HTF_FVG"),
            htf_swing_anchor=112.0,
            atr_15m=10.0,
            config=FakeSafetyConfig(),
        )
        assert sl == pytest.approx(125.0, rel=1e-6)

    def test_structural_used_when_within_atr_bounds(self):
        """When structural stop is within [min_dist, max_dist], use it as-is."""
        from engine.smc_v2.sl_calc import calc_sl
        # entry=100, zone.high=100.5, swing=100.3, ATR=10, buffer=0.5*10=5
        # structural = max(100.5, 100.3) + 5 = 105.5 → stop_dist = 5.5
        # min_dist = 0.5 * 10 = 5; max_dist = 5*10 = 50
        # 5 <= 5.5 <= 50 → return structural unchanged
        sl = calc_sl(
            direction="SHORT",
            entry_price=100.0,
            zone=ZoneSpec(low=100.0, high=100.5, source="HTF_FVG"),
            htf_swing_anchor=100.3,
            atr_15m=10.0,
            config=FakeSafetyConfig(),
        )
        assert sl == pytest.approx(105.5, rel=1e-6)

    def test_atr_floor_widens_too_tight_stop(self):
        """When structural stop_dist < min_sl_atr * ATR, widen to ATR floor."""
        from engine.smc_v2.sl_calc import calc_sl
        # Force structural too tight: tiny zone offset + zero buffer.
        # zone.high=100.0001, swing=100.0, ATR=1, buffer=0
        # structural = 100.0001 + 0 = 100.0001 → stop_dist = 0.0001
        # min_dist = 0.5 * 1 = 0.5 → 0.0001 < 0.5 → floor to min_dist
        # SL = entry + min_dist = 100 + 0.5 = 100.5
        cfg_no_buf = FakeSafetyConfig(sl_atr_buffer=0.0, min_sl_atr=0.5, max_sl_atr=5.0)
        sl = calc_sl(
            direction="SHORT",
            entry_price=100.0,
            zone=ZoneSpec(low=99.9, high=100.0001, source="HTF_FVG"),
            htf_swing_anchor=100.0,
            atr_15m=1.0,
            config=cfg_no_buf,
        )
        assert sl == pytest.approx(100.5, rel=1e-6)

    def test_max_clamp_raises_sl_too_far_error(self):
        from engine.smc_v2.sl_calc import calc_sl
        # entry=100, zone.high=200, swing=200, ATR=10
        # structural = 200 + 5 = 205 → stop_dist = 105
        # max_dist = 5 * 10 = 50 → 105 > 50 → REJECT
        with pytest.raises(SLTooFarError) as exc:
            calc_sl(
                direction="SHORT",
                entry_price=100.0,
                zone=ZoneSpec(low=150.0, high=200.0, source="HTF_FVG"),
                htf_swing_anchor=200.0,
                atr_15m=10.0,
                config=FakeSafetyConfig(),
            )
        assert exc.value.stop_dist == pytest.approx(105.0, rel=1e-6)
        assert exc.value.max_dist == pytest.approx(50.0, rel=1e-6)


    def test_zero_atr_rejects_via_max_clamp(self):
        """Degenerate ATR=0 → min_dist=max_dist=0, any non-zero structural
        stop_dist exceeds max → REJECT. Locks in the contract for the
        zero-ATR edge case (could happen in dead-market low-vol periods).
        """
        from engine.smc_v2.sl_calc import calc_sl
        with pytest.raises(SLTooFarError):
            calc_sl(
                direction="SHORT",
                entry_price=100.0,
                zone=ZoneSpec(low=99.0, high=101.0, source="HTF_FVG"),
                htf_swing_anchor=102.0,
                atr_15m=0.0,
                config=FakeSafetyConfig(),
            )


class TestCalcSLLong:
    """LONG SL = below entry; structural side is zone.low or htf_swing_anchor (min)."""

    def test_structural_uses_min_of_zone_and_swing_minus_buffer(self):
        from engine.smc_v2.sl_calc import calc_sl
        # zone.low = 90, swing = 85 (lower = further from LONG entry)
        sl = calc_sl(
            direction="LONG",
            entry_price=100.0,
            zone=ZoneSpec(low=90.0, high=95.0, source="HTF_FVG"),
            htf_swing_anchor=85.0,
            atr_15m=4.0,
            config=FakeSafetyConfig(),
        )
        # min(90, 85) - 0.5*4 = 83
        assert sl == pytest.approx(83.0, rel=1e-6)

    def test_long_max_clamp_raises(self):
        from engine.smc_v2.sl_calc import calc_sl
        with pytest.raises(SLTooFarError):
            calc_sl(
                direction="LONG",
                entry_price=100.0,
                zone=ZoneSpec(low=10.0, high=15.0, source="HTF_FVG"),
                htf_swing_anchor=5.0,
                atr_15m=10.0,
                config=FakeSafetyConfig(),
            )
