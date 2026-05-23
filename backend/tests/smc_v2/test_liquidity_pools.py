"""Tests for SMCEngine.liquidity_pools and EqLevel dataclass.

EqLevel is the typed v2 equivalent of the existing dict-based equal_levels()
output. liquidity_pools() builds on equal_levels() to cluster equal H/L into
typed records consumed by tp_calc.
"""
import pandas as pd
import pytest

from engine.smc import SMCEngine, Swing


class TestEqLevelDataclass:
    """EqLevel must be importable from engine.smc and have the documented fields."""

    def test_eqlevel_has_price_and_kind_fields(self):
        from engine.smc import EqLevel
        e = EqLevel(price=100.0, kind="EQH", touches=2)
        assert e.price == 100.0
        assert e.kind == "EQH"
        assert e.touches == 2

    def test_eqlevel_kind_eql(self):
        from engine.smc import EqLevel
        e = EqLevel(price=50.0, kind="EQL", touches=3)
        assert e.kind == "EQL"


class TestLiquidityPools:
    """liquidity_pools() clusters equal-price swings into EqLevel records.

    Reads swings (from SMCEngine.swings()), groups by approximate price equality
    using the engine's eq_thr setting (config: structure.eq_threshold_pct / 100).
    Each cluster collapses to one EqLevel with the average price and touch count.
    """

    @pytest.fixture
    def engine(self):
        # Default eq_thr=0.001 (0.1%) per SMCEngine defaults
        return SMCEngine()

    def test_two_equal_highs_make_one_eqh(self, engine):
        swings_high = [
            Swing(price=100.0, idx=10, ts="t1", is_high=True),
            Swing(price=100.05, idx=20, ts="t2", is_high=True),  # within 0.1%
        ]
        pools = engine.liquidity_pools(swings_high, [])
        eqh = [p for p in pools if p.kind == "EQH"]
        assert len(eqh) == 1
        assert eqh[0].price == pytest.approx(100.025, rel=1e-4)
        assert eqh[0].touches == 2

    def test_two_equal_lows_make_one_eql(self, engine):
        swings_low = [
            Swing(price=50.0, idx=15, ts="t1", is_high=False),
            Swing(price=50.04, idx=25, ts="t2", is_high=False),
        ]
        pools = engine.liquidity_pools([], swings_low)
        eql = [p for p in pools if p.kind == "EQL"]
        assert len(eql) == 1
        assert eql[0].price == pytest.approx(50.02, rel=1e-4)

    def test_three_clustered_highs_one_eqh_with_three_touches(self, engine):
        swings_high = [
            Swing(price=200.0, idx=10, ts="t1", is_high=True),
            Swing(price=200.05, idx=20, ts="t2", is_high=True),
            Swing(price=200.10, idx=30, ts="t3", is_high=True),
        ]
        pools = engine.liquidity_pools(swings_high, [])
        eqh = [p for p in pools if p.kind == "EQH"]
        assert len(eqh) == 1
        assert eqh[0].touches == 3

    def test_non_equal_highs_produce_no_pool(self, engine):
        swings_high = [
            Swing(price=100.0, idx=10, ts="t1", is_high=True),
            Swing(price=105.0, idx=20, ts="t2", is_high=True),  # 5% diff, not equal
        ]
        pools = engine.liquidity_pools(swings_high, [])
        assert pools == []

    def test_empty_inputs_return_empty_list(self, engine):
        assert engine.liquidity_pools([], []) == []

    def test_single_swing_produces_no_pool(self, engine):
        """A cluster requires at least 2 touches."""
        swings = [Swing(price=100.0, idx=10, ts="t1", is_high=True)]
        assert engine.liquidity_pools(swings, []) == []
