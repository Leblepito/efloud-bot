"""Tests for the 2026-06-20 algorithm audit findings H1, H5, H7, M1.

H1 — post-cap confluence bonuses (Gemini sentiment / daily / levels) get added
     AFTER calc_confluence()'s min(s,100) cap, so min_confluence stops meaning
     "structural confluence" once bonuses land. Fix: telemetry only —
     sig.meta["structural_score"] records the pre-bonus score. No gating change.

H5 — HTF bias can be "fabricated from chop" via a 40-bar slope fallback or an
     entry-TF range fallback when structural bias is UNDEF, but the +25
     "HTF aligned" confluence bonus and the entry gate don't de-rate for it.
     Fix: telemetry only — sig.meta["htf_bias_source"] tags
     "structural" | "slope_fallback" | "range_fallback". No gating change.

H7 — TP1 is always floored to >= min_rr via a synthetic 1.272 Fibonacci
     discovery clamp when no real FVG/liquidity target exists, which makes the
     `rr1 < min_rr` reject dead code. Fix: new default-OFF `strict_target_reject`
     flag — when True, reject (no trade) instead of clamping. Default False
     preserves the exact old (clamping) behavior.

M1 — `is_discovery` was derived from an empty-list proxy
     (`not htf_above_targets`/`not htf_below_targets`) that is also empty in the
     ranging-liquidity branch (which never touches those lists), misclassifying
     a real-liquidity ranging TP1 as "discovery" and giving it TP2=2.618R
     instead of the correct fib_ext. Fix: new default-OFF
     `fix_discovery_classification` flag — when True, is_discovery is derived
     from `tp1_is_synthetic` (whether TP1 actually came from the 1.272 clamp).
     Default False preserves the exact old (buggy) classification.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from engine.signals import generate_signals


def _make_mock_engine(break_obj, is_long=True, htf_bias="BULL", swing_highs=None, swing_lows=None):
    e_range = SimpleNamespace(
        discount=is_long, premium=not is_long, dev_bull=False, dev_bear=False,
        lo=95.0, hi=105.0, eq=100.0,
    )
    engine = MagicMock()
    engine.analyze.return_value = {
        "trend": htf_bias,
        "active_fvgs": [],
        "active_obs": [],
        "swing_highs": swing_highs if swing_highs is not None else [],
        "swing_lows": swing_lows if swing_lows is not None else [],
        "range": e_range,
    }
    engine.swings.return_value = ([], [])
    engine.structure.side_effect = [[], [break_obj]]
    engine.order_blocks.return_value = []
    engine.sfps.return_value = []
    engine.range_info.return_value = e_range
    engine.ote.return_value = None
    return engine


def _flat_df(n=50, price=100.0, high=100.2, low=99.8):
    return pd.DataFrame({
        "open": [price] * n, "high": [high] * n, "low": [low] * n, "close": [price] * n,
    })


def _discovery_engine(is_long=True):
    """Empty swing/FVG structures -> forces the synthetic 1.272 discovery clamp."""
    choch = SimpleNamespace(
        direction="BULL" if is_long else "BEAR", kind="CHoCH", idx=45,
        ts="2026-05-08T00:00", price=100.0,
    )
    return _make_mock_engine(choch, is_long=is_long, htf_bias="BULL" if is_long else "BEAR")


class TestH1StructuralScoreTelemetry:
    def test_structural_score_matches_confluence_when_no_bonuses(self):
        engine = _discovery_engine()
        df = _flat_df()
        sigs = generate_signals(engine, df, df, df, min_confluence=0, min_rr=1.0, recency_bars=40)
        assert len(sigs) == 1
        sig = sigs[0]
        # No levels / no ai_sentiment / no daily filter -> no post-cap bonuses fired.
        assert sig.meta["structural_score"] == sig.confluence

    def test_structural_score_diverges_from_confluence_with_post_cap_bonus(self):
        from engine.levels import Level
        engine = _discovery_engine()
        df = _flat_df()
        # Major level sitting exactly at entry (100.0) -> +5 post-cap bonus (H1).
        wo_level = Level(name="WO", price=100.0, kind="open", strength=1)
        sigs = generate_signals(
            engine, df, df, df, min_confluence=0, min_rr=1.0, recency_bars=40,
            levels=[wo_level],
        )
        assert len(sigs) == 1
        sig = sigs[0]
        assert sig.confluence == sig.meta["structural_score"] + 5


class TestH5HtfBiasSourceTelemetry:
    def test_structural_bias_tagged_when_trend_defined(self):
        choch = SimpleNamespace(direction="BULL", kind="CHoCH", idx=45, ts="t", price=100.0)
        engine = _make_mock_engine(choch, is_long=True, htf_bias="BULL")
        df = _flat_df()
        sigs = generate_signals(engine, df, df, df, min_confluence=0, min_rr=1.0, recency_bars=40)
        assert len(sigs) == 1
        assert sigs[0].meta["htf_bias_source"] == "structural"

    def test_slope_fallback_tagged_when_trend_undef_and_slope_present(self):
        choch = SimpleNamespace(direction="BULL", kind="CHoCH", idx=45, ts="t", price=100.0)
        engine = _make_mock_engine(choch, is_long=True, htf_bias="UNDEF")
        # 40+ bars with a clear >2% uptrend slope so the slope_fallback branch fires.
        closes = [100.0 + i * 0.1 for i in range(60)]
        df_htf = pd.DataFrame({
            "open": closes, "high": [c + 0.2 for c in closes],
            "low": [c - 0.2 for c in closes], "close": closes,
        })
        df_entry = _flat_df()
        sigs = generate_signals(engine, df_htf, df_entry, df_entry, min_confluence=0, min_rr=1.0, recency_bars=40)
        assert len(sigs) == 1
        assert sigs[0].meta["htf_bias_source"] == "slope_fallback"

    def test_range_fallback_tagged_when_trend_undef_and_slope_flat(self):
        choch = SimpleNamespace(direction="BULL", kind="CHoCH", idx=45, ts="t", price=100.0)
        engine = _make_mock_engine(choch, is_long=True, htf_bias="UNDEF")
        # Flat HTF (no slope) -> falls through to entry-TF range_info, which the
        # mock engine reports as discount=True (a range play), tagging BULL.
        df_htf = _flat_df(n=60)
        df_entry = _flat_df()
        sigs = generate_signals(engine, df_htf, df_entry, df_entry, min_confluence=0, min_rr=1.0, recency_bars=40)
        assert len(sigs) == 1
        assert sigs[0].meta["htf_bias_source"] == "range_fallback"


class TestH7StrictTargetReject:
    def test_default_off_preserves_synthetic_clamp_behavior(self):
        engine = _discovery_engine()
        df = _flat_df()
        sigs = generate_signals(engine, df, df, df, min_confluence=0, min_rr=1.0, recency_bars=40)
        assert len(sigs) == 1
        assert sigs[0].meta["tp1_is_synthetic"] is True

    def test_strict_target_reject_true_drops_signal_with_no_real_target(self):
        engine = _discovery_engine()
        df = _flat_df()
        sigs = generate_signals(
            engine, df, df, df, min_confluence=0, min_rr=1.0, recency_bars=40,
            strict_target_reject=True,
        )
        assert sigs == []


class TestM1DiscoveryClassificationFix:
    def _ranging_liquidity_engine(self):
        """Ranging (htf_bias=UNDEF) with a REAL swing-high liquidity target just
        above min_tp_long (~price + risk*min_rr) -> tp1 comes from real
        liquidity, not the 1.272 clamp. Kept close to min_tp_long (rather than
        far away) so neither candidate TP2 (2.618R nor fib_ext*R) collapses
        onto TP1 via the separate _enforce_tp2_beyond_tp1 guard — that guard
        is orthogonal to the is_discovery classification under test here."""
        choch = SimpleNamespace(direction="BULL", kind="CHoCH", idx=45, ts="t", price=100.0)
        return _make_mock_engine(
            choch, is_long=True, htf_bias="UNDEF",
            swing_highs=[SimpleNamespace(price=100.45, idx=5, is_high=True)],
        )

    def test_default_off_misclassifies_real_liquidity_tp1_as_discovery(self):
        engine = self._ranging_liquidity_engine()
        df = _flat_df()
        sigs = generate_signals(engine, df, df, df, min_confluence=0, min_rr=1.0, fib_ext=1.618, recency_bars=40)
        assert len(sigs) == 1
        sig = sigs[0]
        assert sig.tp1 == 100.45
        assert sig.meta["tp1_is_synthetic"] is False
        # Old (buggy) behavior: empty-list proxy still classifies this as
        # "discovery" -> TP2 uses the 2.618 extension, not fib_ext (1.618).
        assert sig.rr2 == pytest.approx(2.618, abs=0.01)

    def test_fix_enabled_uses_fib_ext_for_real_liquidity_tp1(self):
        engine = self._ranging_liquidity_engine()
        df = _flat_df()
        sigs = generate_signals(
            engine, df, df, df, min_confluence=0, min_rr=1.0, fib_ext=1.618, recency_bars=40,
            fix_discovery_classification=True,
        )
        assert len(sigs) == 1
        sig = sigs[0]
        assert sig.tp1 == 100.45
        assert sig.meta["tp1_is_synthetic"] is False
        # Fixed behavior: real-liquidity TP1 is NOT discovery -> TP2 uses fib_ext.
        assert sig.rr2 == pytest.approx(1.618, abs=0.01)
