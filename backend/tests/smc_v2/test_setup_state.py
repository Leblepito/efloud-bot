"""Tests for smc_v2.setup_state — SetupCandidate dataclass + persistence."""
from pathlib import Path
import pytest

from engine.smc_v2.zones import ZoneSpec


class TestSetupCandidateDataclass:
    """SetupCandidate carries the state needed to track a pending pullback setup
    across orchestrator ticks (spec §4.1)."""

    def test_required_fields_present(self):
        from engine.smc_v2.setup_state import SetupCandidate
        sc = SetupCandidate(
            symbol="BTC/USDT",
            direction="SHORT",
            trigger_bar_ts=1700000000000,
            trigger_price=95000.0,
            htf_bias="BEAR",
            target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
            htf_swing_anchor=98000.0,
            bars_waited=0,
            state="AWAITING_PULLBACK",
            confluence_score=75,
            reasons=["HTF aligned", "OB confluence"],
        )
        assert sc.symbol == "BTC/USDT"
        assert sc.direction == "SHORT"
        assert sc.trigger_bar_ts == 1700000000000
        assert sc.trigger_price == 95000.0
        assert sc.htf_bias == "BEAR"
        assert sc.target_zone.low == 96000.0
        assert sc.target_zone.source == "HTF_FVG"
        assert sc.htf_swing_anchor == 98000.0
        assert sc.bars_waited == 0
        assert sc.state == "AWAITING_PULLBACK"
        assert sc.confluence_score == 75
        assert sc.reasons == ["HTF aligned", "OB confluence"]

    def test_long_direction_with_ote_zone(self):
        from engine.smc_v2.setup_state import SetupCandidate
        sc = SetupCandidate(
            symbol="ETH/USDT",
            direction="LONG",
            trigger_bar_ts=1700000060000,
            trigger_price=2400.0,
            htf_bias="BULL",
            target_zone=ZoneSpec(low=2380.0, high=2390.0, source="OTE"),
            htf_swing_anchor=2350.0,
            bars_waited=2,
            state="IN_ZONE",
            confluence_score=60,
            reasons=[],
        )
        assert sc.direction == "LONG"
        assert sc.target_zone.source == "OTE"
        assert sc.state == "IN_ZONE"
        assert sc.bars_waited == 2
