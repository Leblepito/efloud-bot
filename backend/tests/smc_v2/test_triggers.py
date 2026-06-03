"""Tests for engine.smc_v2.triggers — pure CHoCH → SetupCandidate generator."""
from dataclasses import dataclass
import pandas as pd
import pytest

from engine.smc import Swing, StructBreak, FVG


@dataclass
class FakeBar:
    """HTF bar shape for swing_anchor."""
    ordinal: int
    high: float
    low: float


class TestGenerateSetupCandidatesShort:
    """SHORT trigger: CHoCH BEAR aligned with HTF bias BEAR."""

    def test_emits_candidate_for_aligned_choch(self):
        from engine.smc_v2.triggers import generate_setup_candidates
        trigger_iso = "2026-01-01T06:15:00+00:00"
        trigger_ms = int(pd.Timestamp(trigger_iso).timestamp() * 1000)
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=25, ts=trigger_iso, broken_level=95.0),
        ]
        htf_swings = {
            "swing_highs": [
                Swing(price=120.0, idx=10, ts="t10", is_high=True),
            ],
            "swing_lows": [],
        }
        htf_bars = [
            FakeBar(ordinal=15, high=115, low=100),
            FakeBar(ordinal=20, high=118, low=105),
        ]
        htf_fvgs = [
            FVG(top=115.0, bot=110.0, idx=12, ts="t12", direction="BULL"),
        ]
        ote_band = (105.0, 108.0)

        candidates = generate_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings=htf_swings,
            htf_bars=htf_bars,
            htf_fvgs=htf_fvgs,
            ote_band=ote_band,
            ltf_trigger_idx_min=20,
        )
        assert len(candidates) == 1
        c = candidates[0]
        assert c.symbol == "BTC/USDT"
        assert c.direction == "SHORT"
        assert c.trigger_price == 100.0
        # C6: trigger_bar_ts must be the CHoCH bar's ms-epoch timestamp (the axis
        # confirm_entry's since_ts compares against), NOT the bar ordinal. Storing
        # the ordinal (25) made confirm_entry's "only AFTER the trigger" guard dead
        # code (ordinal << ms always → never skipped pre-trigger engulfings).
        assert c.trigger_bar_ts == trigger_ms
        assert c.trigger_bar_ts != 25  # not the ordinal
        assert c.htf_bias == "BEAR"
        assert c.htf_swing_anchor == 120.0
        assert c.target_zone.low == 110.0
        assert c.target_zone.high == 115.0
        assert c.target_zone.source == "HTF_FVG"
        assert c.state == "AWAITING_PULLBACK"
        assert c.bars_waited == 0

    def test_skips_choch_misaligned_with_bias(self):
        from engine.smc_v2.triggers import generate_setup_candidates
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BULL", price=100.0,
                        idx=25, ts="t25", broken_level=95.0),
        ]
        candidates = generate_setup_candidates(
            symbol="BTC/USDT", htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [], "swing_lows": []},
            htf_bars=[], htf_fvgs=[], ote_band=(0.0, 0.0),
            ltf_trigger_idx_min=20,
        )
        assert candidates == []

    def test_skips_bos_only_choch_in_pr_s3c_1(self):
        from engine.smc_v2.triggers import generate_setup_candidates
        ltf_brks = [
            StructBreak(kind="BOS", direction="BEAR", price=100.0,
                        idx=25, ts="t25", broken_level=95.0),
        ]
        candidates = generate_setup_candidates(
            symbol="BTC/USDT", htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [], "swing_lows": []},
            htf_bars=[], htf_fvgs=[], ote_band=(0.0, 0.0),
            ltf_trigger_idx_min=20,
        )
        assert candidates == []

    def test_skips_stale_choch_before_trigger_window(self):
        from engine.smc_v2.triggers import generate_setup_candidates
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=10, ts="t10", broken_level=95.0),
        ]
        candidates = generate_setup_candidates(
            symbol="BTC/USDT", htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [Swing(120.0, 5, "t5", True)],
                        "swing_lows": []},
            htf_bars=[FakeBar(ordinal=8, high=115, low=100)],
            htf_fvgs=[FVG(top=115.0, bot=110.0, idx=4, ts="t4", direction="BULL")],
            ote_band=(105.0, 108.0),
            ltf_trigger_idx_min=20,
        )
        assert candidates == []

    def test_skips_when_no_unbroken_swing_anchor(self):
        from engine.smc_v2.triggers import generate_setup_candidates
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=25, ts="t25", broken_level=95.0),
        ]
        candidates = generate_setup_candidates(
            symbol="BTC/USDT", htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [], "swing_lows": []},
            htf_bars=[], htf_fvgs=[], ote_band=(105.0, 108.0),
            ltf_trigger_idx_min=20,
        )
        assert candidates == []


class TestGenerateSetupCandidatesLong:
    """LONG trigger: CHoCH BULL aligned with HTF bias BULL (mirror)."""

    def test_emits_candidate_for_aligned_bull_choch(self):
        from engine.smc_v2.triggers import generate_setup_candidates
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BULL", price=2400.0,
                        idx=25, ts="t25", broken_level=2450.0),
        ]
        htf_swings = {
            "swing_highs": [],
            "swing_lows": [
                Swing(price=2350.0, idx=10, ts="t10", is_high=False),
            ],
        }
        htf_bars = [
            FakeBar(ordinal=15, high=2440, low=2380),
        ]
        htf_fvgs = [
            FVG(top=2390.0, bot=2380.0, idx=12, ts="t12", direction="BEAR"),
        ]
        ote_band = (2370.0, 2375.0)

        candidates = generate_setup_candidates(
            symbol="ETH/USDT", htf_bias="BULL",
            ltf_structure_breaks=ltf_brks,
            htf_swings=htf_swings,
            htf_bars=htf_bars,
            htf_fvgs=htf_fvgs, ote_band=ote_band,
            ltf_trigger_idx_min=20,
        )
        assert len(candidates) == 1
        c = candidates[0]
        assert c.direction == "LONG"
        assert c.htf_swing_anchor == 2350.0
        assert c.target_zone.source == "HTF_FVG"


class TestMultipleBreaks:
    def test_emits_for_each_aligned_recent_choch(self):
        from engine.smc_v2.triggers import generate_setup_candidates
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=22, ts="t22", broken_level=95.0),
            StructBreak(kind="CHoCH", direction="BULL", price=98.0,
                        idx=23, ts="t23", broken_level=100.0),
            StructBreak(kind="CHoCH", direction="BEAR", price=99.0,
                        idx=25, ts="t25", broken_level=94.0),
            StructBreak(kind="BOS", direction="BEAR", price=97.0,
                        idx=26, ts="t26", broken_level=93.0),
        ]
        htf_swings = {
            "swing_highs": [Swing(120.0, 10, "t10", True)],
            "swing_lows": [],
        }
        htf_bars = [FakeBar(ordinal=15, high=115, low=100)]
        htf_fvgs = [FVG(top=115.0, bot=110.0, idx=12, ts="t12", direction="BULL")]
        ote_band = (105.0, 108.0)

        candidates = generate_setup_candidates(
            symbol="BTC/USDT", htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings=htf_swings, htf_bars=htf_bars,
            htf_fvgs=htf_fvgs, ote_band=ote_band,
            ltf_trigger_idx_min=20,
        )
        assert len(candidates) == 2
        assert all(c.direction == "SHORT" for c in candidates)


class TestUndefinedBias:
    def test_undefined_bias_emits_nothing(self):
        from engine.smc_v2.triggers import generate_setup_candidates
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=25, ts="t25", broken_level=95.0),
        ]
        candidates = generate_setup_candidates(
            symbol="BTC/USDT", htf_bias="UNDEF",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [], "swing_lows": []},
            htf_bars=[], htf_fvgs=[], ote_band=(0.0, 0.0),
            ltf_trigger_idx_min=20,
        )
        assert candidates == []
