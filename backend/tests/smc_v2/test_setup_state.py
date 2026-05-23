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


class TestSetupStateStoreRoundTrip:
    """Save → load round-trip preserves SetupCandidate identity exactly."""

    def _make_candidate(self, symbol="BTC/USDT", state="AWAITING_PULLBACK", bars=0):
        from engine.smc_v2.setup_state import SetupCandidate
        return SetupCandidate(
            symbol=symbol,
            direction="SHORT",
            trigger_bar_ts=1700000000000,
            trigger_price=95000.0,
            htf_bias="BEAR",
            target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
            htf_swing_anchor=98000.0,
            bars_waited=bars,
            state=state,
            confluence_score=75,
            reasons=["HTF aligned"],
        )

    def test_save_then_load_single_candidate(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "setup_candidates.json")
        sc = self._make_candidate()
        store.add(sc)
        store.save()

        # Fresh store reads the same file
        store2 = SetupStateStore(tmp_path / "setup_candidates.json")
        store2.load()
        assert len(store2.candidates) == 1
        loaded = store2.candidates[0]
        assert loaded.symbol == sc.symbol
        assert loaded.direction == sc.direction
        assert loaded.trigger_bar_ts == sc.trigger_bar_ts
        assert loaded.trigger_price == sc.trigger_price
        assert loaded.htf_bias == sc.htf_bias
        assert loaded.target_zone.low == sc.target_zone.low
        assert loaded.target_zone.high == sc.target_zone.high
        assert loaded.target_zone.source == sc.target_zone.source
        assert loaded.htf_swing_anchor == sc.htf_swing_anchor
        assert loaded.bars_waited == sc.bars_waited
        assert loaded.state == sc.state
        assert loaded.confluence_score == sc.confluence_score
        assert loaded.reasons == sc.reasons

    def test_save_then_load_multiple_candidates(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "setup_candidates.json")
        store.add(self._make_candidate(symbol="BTC/USDT"))
        store.add(self._make_candidate(symbol="ETH/USDT", bars=2))
        store.add(self._make_candidate(symbol="SOL/USDT", state="IN_ZONE", bars=4))
        store.save()

        store2 = SetupStateStore(tmp_path / "setup_candidates.json")
        store2.load()
        assert len(store2.candidates) == 3
        symbols = sorted(c.symbol for c in store2.candidates)
        assert symbols == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

    def test_load_from_nonexistent_file_yields_empty(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "nonexistent.json")
        store.load()
        assert store.candidates == []

    def test_save_creates_parent_dir(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        nested_path = tmp_path / "deep" / "nested" / "state.json"
        store = SetupStateStore(nested_path)
        store.add(self._make_candidate())
        store.save()
        assert nested_path.exists()
