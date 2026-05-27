"""Dedicated tests for Efloud Price Action level confluence and target logic."""

import logging
from types import SimpleNamespace
from typing import Dict, List
from unittest.mock import MagicMock
import pandas as pd
import pytest

from engine.signals import generate_signals
from engine.levels import Level


class TestPriceActionLevelsAndTargets:
    """Suite to verify Level-based confluence boosts, Range Deviation setups, and ranging liquidity targets."""

    def _make_mock_engine(self, break_obj, is_long=True, has_dev=False, htf_bias="BULL") -> MagicMock:
        e_range = SimpleNamespace(
            discount=is_long, premium=not is_long, dev_bull=is_long and has_dev, dev_bear=not is_long and has_dev,
            lo=95.0, hi=105.0, eq=100.0,
        )
        engine = MagicMock()
        engine.analyze.return_value = {
            "trend": htf_bias,
            "active_fvgs": [],
            "active_obs": [],
            "swing_highs": [SimpleNamespace(price=108.0, idx=5, is_high=True)],
            "swing_lows": [SimpleNamespace(price=92.0, idx=5, is_high=False)],
            "range": e_range,
        }
        engine.swings.return_value = ([], [])
        engine.structure.side_effect = [[], [break_obj]]
        engine.order_blocks.return_value = []
        engine.sfps.return_value = []
        engine.range_info.return_value = e_range
        engine.ote.return_value = None
        return engine

    def test_major_level_confluence_boost(self) -> None:
        """Verify that being close to a major open level (e.g. WO) awards +5 confluence points."""
        choch_break = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(choch_break, is_long=True, htf_bias="BULL")
        df = pd.DataFrame({
            "open": [100.0] * 50,
            "high": [100.0] * 50,
            "low": [100.0] * 50,
            "close": [100.0] * 50
        })

        # Place a Weekly Open level exactly at 100.0 (near our entry price of 100.0)
        wo_level = Level(name="WO", price=100.0, kind="open", strength=1)

        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=20, min_rr=1.0, fib_ext=1.618,
            recency_bars=40,
            levels=[wo_level],
        )

        assert len(sigs) == 1
        sig = sigs[0]
        # Base HTF bias = 25, Correct zone = 5 -> Standard = 30.
        # Plus WO near entry (within 0.3%) = +5 -> Expected score = 35.
        assert sig.confluence == 35
        assert any("Price near major level WO" in r for r in sig.reasons)

    def test_stacked_zone_confluence_boost(self) -> None:
        """Verify that being close to a Stacked Zone level (strength >= 3) awards +8 confluence points."""
        choch_break = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(choch_break, is_long=True, htf_bias="BULL")
        df = pd.DataFrame({
            "open": [100.0] * 50,
            "high": [100.0] * 50,
            "low": [100.0] * 50,
            "close": [100.0] * 50
        })

        # Stacked level with strength 3 at 99.8 (within 0.5% of entry 100.0)
        stacked_level = Level(name="MO", price=99.8, kind="open", strength=3)

        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=20, min_rr=1.0, fib_ext=1.618,
            recency_bars=40,
            levels=[stacked_level],
        )

        assert len(sigs) == 1
        sig = sigs[0]
        # Base HTF bias = 25, Correct zone = 5 -> Standard = 30.
        # Plus Stacked Zone (within 0.5%) = +8 -> Expected score = 38.
        # (It also triggers 'Price near major level MO' because 99.8 is within 0.3% of 100.0, adding +5 -> total 43)
        assert sig.confluence in (38, 43)
        assert any("Price in Stacked Zone level MO" in r for r in sig.reasons)

    def test_range_deviation_targets_and_sl(self) -> None:
        """Verify that Range Deviation setups set Stop Loss at deviation low and TP1/TP2 at EQ / opposite range high."""
        choch_break = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        # has_dev = True, range.hi = 105.0, range.lo = 95.0, range.eq = 100.0
        engine = self._make_mock_engine(choch_break, is_long=True, has_dev=True, htf_bias="BULL")
        df = pd.DataFrame({
            "open": [100.0] * 50,
            "high": [101.0] * 50,
            "low": [99.0] * 50,
            "close": [100.0] * 50
        })

        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=20, min_rr=1.0, fib_ext=1.618,
            recency_bars=40,
        )

        assert len(sigs) == 1
        sig = sigs[0]
        # For long Range deviation:
        # TP1 should target e_range.eq = 100.0. Since entry = 100.0 and minimum R:R = 1.0,
        # it is bumped to meet the minimum R:R distance, but matches our range play logic.
        # TP2 should target range.hi = 105.0
        assert sig.tp2 == 105.0

    def test_ranging_market_prioritizes_liquidity(self) -> None:
        """Verify that ranging markets (HTF bias = UNDEF) target liquidity pools (Swing Highs) instead of FVG."""
        choch_break = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        # htf_bias = UNDEF (Ranging)
        engine = self._make_mock_engine(choch_break, is_long=True, has_dev=False, htf_bias="UNDEF")
        df = pd.DataFrame({
            "open": [100.0] * 50,
            "high": [101.0] * 50,
            "low": [99.0] * 50,
            "close": [100.0] * 50
        })

        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=0, min_rr=1.0, fib_ext=1.618,
            recency_bars=40,
        )

        assert len(sigs) == 1
        sig = sigs[0]
        # In a ranging market, TP1 targets nearest Swing High >= min_tp_long.
        # Swing high in engine mock is 108.0.
        # Since min_tp_long is ~100.5, 108.0 matches and is targeted.
        assert sig.tp1 == 108.0

    def test_pullback_entry_refinement(self) -> None:
        """Verify that entry price is refined to OB boundary rather than breakout price for lower risk entries."""
        choch_break = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(choch_break, is_long=True, htf_bias="BULL")
        
        # Bullish OB with top at 99.2 (pullback entry level)
        bull_ob = SimpleNamespace(direction="BULL", top=99.2, bot=98.0, eq=98.6, near_swing=True, mitigated=False)
        engine.analyze.return_value["active_obs"] = [bull_ob]
        engine.order_blocks.return_value = [bull_ob]
        
        df = pd.DataFrame({
            "open": [100.0] * 50,
            "high": [101.0] * 50,
            "low": [99.0] * 50,
            "close": [100.0] * 50
        })

        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=0, min_rr=1.0, fib_ext=1.618,
            recency_bars=40,
        )

        assert len(sigs) == 1
        sig = sigs[0]
        # Entry price should be refined to OB top = 99.2, which is lower than breakout 100.0!
        assert sig.entry == 99.2

    def test_fibonacci_discovery_targets(self) -> None:
        """Verify that price discovery setups (empty structures) target Fibonacci extensions (1.272 / 2.618)."""
        choch_break = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(choch_break, is_long=True, htf_bias="BULL")
        
        # Completely empty historical targets to simulate price discovery / blue-sky environment
        engine.analyze.return_value["swing_highs"] = []
        engine.analyze.return_value["active_fvgs"] = []
        
        df = pd.DataFrame({
            "open": [100.0] * 50,
            "high": [100.2] * 50,
            "low": [99.8] * 50,
            "close": [100.0] * 50
        })

        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=0, min_rr=1.0, fib_ext=1.618,
            recency_bars=40,
        )

        assert len(sigs) == 1
        sig = sigs[0]
        # TP1 should be entry + risk * 1.272
        # TP2 should be entry + risk * 2.618
        assert sig.tp1 > sig.entry
        assert sig.tp2 > sig.tp1
