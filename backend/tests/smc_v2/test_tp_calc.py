"""Tests for smc_v2.tp_calc — TP1/TP2 target computation.

Behavior (spec §5.2):
  TP1 sources (priority):
    1. Nearest liquidity (EQH/EQL clusters + HTF swing extrema) at correct side
       with |target - entry| >= min_rr * risk
    2. Fallback: nearest HTF FVG near-edge satisfying the same constraint
    3. If candidates exist but none satisfy min_rr → RAISE InsufficientTPDistanceError
    4. If no candidates at all → projection: entry ± min_rr * risk (RR_PROJECTION)

  TP2 sources:
    1. HTF FVG far-edge beyond TP1
    2. Fallback: fib_ext * risk projection beyond TP1
    3. If neither satisfies TP2 > TP1 (strict) → return None (single-target mode)

  Source attribution (with explicit precedence to avoid float-equality ambiguity):
    LIQUIDITY > FVG_NEAR on ties.
"""
from dataclasses import dataclass
import pytest

from engine.smc import FVG, EqLevel, Swing
from engine.smc_v2.exceptions import InsufficientTPDistanceError


@dataclass
class FakeRiskConfig:
    min_rr: float = 1.8
    fib_ext: float = 1.618


def htf_swings_dict(highs=(), lows=()):
    """Build the htf_swings dict shape calc_tp_targets expects."""
    return {
        "swing_highs": [Swing(price=p, idx=i, ts=f"t{i}", is_high=True)
                        for i, p in enumerate(highs)],
        "swing_lows":  [Swing(price=p, idx=i, ts=f"t{i}", is_high=False)
                        for i, p in enumerate(lows)],
    }


class TestCalcTPLongLiquidityWins:
    """LONG: TP1 above entry. Liquidity preferred over FVG."""

    def test_nearest_liquidity_above_minrr_is_tp1(self):
        from engine.smc_v2.tp_calc import calc_tp_targets
        # entry=100, sl=90, risk=10, min_rr=1.8 → min_dist=18
        # EQH at 120 (dist 20, > 18 ✓), EQH at 115 (dist 15, < 18 ✗)
        # nearest qualifying = 120
        eq_levels = [EqLevel(price=115, kind="EQH", touches=2),
                     EqLevel(price=120, kind="EQH", touches=3)]
        tp1, tp2, tags = calc_tp_targets(
            direction="LONG", entry_price=100, sl_price=90,
            htf_swings=htf_swings_dict(highs=(), lows=()),
            htf_fvgs=[], eq_levels=eq_levels, config=FakeRiskConfig(),
        )
        assert tp1 == 120
        assert tags["tp1_source"] == "LIQUIDITY"

    def test_swing_high_qualifies_when_no_eqh(self):
        from engine.smc_v2.tp_calc import calc_tp_targets
        # risk=10, min_rr=1.8 → 18+ required
        tp1, tp2, tags = calc_tp_targets(
            direction="LONG", entry_price=100, sl_price=90,
            htf_swings=htf_swings_dict(highs=(130,), lows=()),
            htf_fvgs=[], eq_levels=[], config=FakeRiskConfig(),
        )
        assert tp1 == 130
        assert tags["tp1_source"] == "LIQUIDITY"

    def test_fvg_near_used_when_no_liquidity(self):
        from engine.smc_v2.tp_calc import calc_tp_targets
        # No EQ/swing, just a BEAR FVG at bot=125 above entry
        fvgs = [FVG(top=130, bot=125, idx=1, ts="t1", direction="BEAR")]
        tp1, tp2, tags = calc_tp_targets(
            direction="LONG", entry_price=100, sl_price=90,
            htf_swings=htf_swings_dict(),
            htf_fvgs=fvgs, eq_levels=[], config=FakeRiskConfig(),
        )
        assert tp1 == 125
        assert tags["tp1_source"] == "FVG_NEAR"

    def test_liquidity_wins_over_fvg_on_price_tie(self):
        """If a LIQUIDITY price equals an FVG_NEAR price, LIQUIDITY label wins."""
        from engine.smc_v2.tp_calc import calc_tp_targets
        eq_levels = [EqLevel(price=125, kind="EQH", touches=2)]
        fvgs = [FVG(top=130, bot=125, idx=1, ts="t1", direction="BEAR")]
        tp1, tp2, tags = calc_tp_targets(
            direction="LONG", entry_price=100, sl_price=90,
            htf_swings=htf_swings_dict(),
            htf_fvgs=fvgs, eq_levels=eq_levels, config=FakeRiskConfig(),
        )
        assert tp1 == 125
        assert tags["tp1_source"] == "LIQUIDITY"

    def test_insufficient_distance_raises(self):
        """Candidates exist but ALL are within min_rr * risk → REJECT."""
        from engine.smc_v2.tp_calc import calc_tp_targets
        # risk=10, min_dist=18; only candidate at 115 (dist=15)
        eq_levels = [EqLevel(price=115, kind="EQH", touches=2)]
        with pytest.raises(InsufficientTPDistanceError) as exc:
            calc_tp_targets(
                direction="LONG", entry_price=100, sl_price=90,
                htf_swings=htf_swings_dict(),
                htf_fvgs=[], eq_levels=eq_levels, config=FakeRiskConfig(),
            )
        assert exc.value.nearest == 115
        assert exc.value.required == pytest.approx(18, rel=1e-6)

    def test_no_candidates_falls_back_to_rr_projection(self):
        """Empty inputs → TP1 = entry + min_rr * risk."""
        from engine.smc_v2.tp_calc import calc_tp_targets
        tp1, tp2, tags = calc_tp_targets(
            direction="LONG", entry_price=100, sl_price=90,
            htf_swings=htf_swings_dict(), htf_fvgs=[], eq_levels=[],
            config=FakeRiskConfig(),
        )
        assert tp1 == pytest.approx(118.0, rel=1e-6)  # 100 + 1.8*10
        assert tags["tp1_source"] == "RR_PROJECTION"


class TestCalcTPLongTP2:
    def test_tp2_fvg_far_edge_when_available(self):
        from engine.smc_v2.tp_calc import calc_tp_targets
        # TP1 will land at 120 (liquidity). FVG far edge at top=135
        eq_levels = [EqLevel(price=120, kind="EQH", touches=2)]
        fvgs = [FVG(top=135, bot=130, idx=1, ts="t1", direction="BEAR")]
        tp1, tp2, tags = calc_tp_targets(
            direction="LONG", entry_price=100, sl_price=90,
            htf_swings=htf_swings_dict(),
            htf_fvgs=fvgs, eq_levels=eq_levels, config=FakeRiskConfig(),
        )
        assert tp1 == 120
        assert tp2 == 135
        assert tags["tp2_source"] == "FVG_FAR"

    def test_tp2_fib_ext_fallback(self):
        from engine.smc_v2.tp_calc import calc_tp_targets
        # No FVG far edge beyond TP1; use fib_ext=1.618 * risk(10) = 16.18 → 116.18
        # But TP1=120, so fib_ext (116.18) <= TP1 → not valid → tp2 = None
        eq_levels = [EqLevel(price=120, kind="EQH", touches=2)]
        tp1, tp2, tags = calc_tp_targets(
            direction="LONG", entry_price=100, sl_price=90,
            htf_swings=htf_swings_dict(),
            htf_fvgs=[], eq_levels=eq_levels, config=FakeRiskConfig(),
        )
        assert tp1 == 120
        assert tp2 is None
        assert tags["tp2_source"] == "NONE"

    def test_tp2_fib_ext_when_beyond_tp1(self):
        from engine.smc_v2.tp_calc import calc_tp_targets
        # Configure with very low min_rr so TP1 lands close to entry,
        # leaving room for fib_ext > TP1
        cfg_low = FakeRiskConfig(min_rr=0.5)
        eq_levels = [EqLevel(price=110, kind="EQH", touches=2)]  # dist=10 ✓
        tp1, tp2, tags = calc_tp_targets(
            direction="LONG", entry_price=100, sl_price=90,
            htf_swings=htf_swings_dict(),
            htf_fvgs=[], eq_levels=eq_levels, config=cfg_low,
        )
        # min_dist = 0.5 * 10 = 5; eq at 110 (dist 10 ✓) → tp1=110
        # fib_ext = 100 + 1.618 * 10 = 116.18 > 110 → tp2=116.18 FIB_EXT
        assert tp1 == 110
        assert tp2 == pytest.approx(116.18, rel=1e-4)
        assert tags["tp2_source"] == "FIB_EXT"


class TestCalcTPShortMirror:
    """SHORT is the mirror of LONG. One canonical test to ensure symmetry."""

    def test_short_liquidity_below_entry(self):
        from engine.smc_v2.tp_calc import calc_tp_targets
        # entry=100, sl=110, risk=10, min_dist=18
        # Candidates sorted descending (closest to entry first): [85, 80]
        # 85: dist 15 < 18 → disqualified
        # 80: dist 20 >= 18 → qualifies → tp1=80
        eq_levels = [EqLevel(price=80, kind="EQL", touches=2),
                     EqLevel(price=85, kind="EQL", touches=2)]
        tp1, tp2, tags = calc_tp_targets(
            direction="SHORT", entry_price=100, sl_price=110,
            htf_swings=htf_swings_dict(),
            htf_fvgs=[], eq_levels=eq_levels, config=FakeRiskConfig(),
        )
        assert tp1 == 80
        assert tags["tp1_source"] == "LIQUIDITY"

    def test_short_tp2_fvg_far_below_tp1(self):
        from engine.smc_v2.tp_calc import calc_tp_targets
        eq_levels = [EqLevel(price=80, kind="EQL", touches=2)]
        # BULL FVG below entry, bot at 65 (further than TP1=80)
        fvgs = [FVG(top=70, bot=65, idx=1, ts="t1", direction="BULL")]
        tp1, tp2, tags = calc_tp_targets(
            direction="SHORT", entry_price=100, sl_price=110,
            htf_swings=htf_swings_dict(),
            htf_fvgs=fvgs, eq_levels=eq_levels, config=FakeRiskConfig(),
        )
        assert tp1 == 80
        assert tp2 == 65
        assert tags["tp2_source"] == "FVG_FAR"
