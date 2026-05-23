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


class TestPruning:
    """Persisted file MUST contain only AWAITING_PULLBACK and IN_ZONE.
    CONFIRMED and EXPIRED are dropped from the in-memory list before save
    and never written to disk.
    """

    def _make(self, symbol, state, bars=0):
        from engine.smc_v2.setup_state import SetupCandidate
        return SetupCandidate(
            symbol=symbol, direction="SHORT", trigger_bar_ts=1700000000000,
            trigger_price=100.0, htf_bias="BEAR",
            target_zone=ZoneSpec(low=105.0, high=110.0, source="HTF_FVG"),
            htf_swing_anchor=115.0, bars_waited=bars,
            state=state, confluence_score=70, reasons=[],
        )

    def test_save_prunes_confirmed_and_expired(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        store.add(self._make("BTC/USDT", "AWAITING_PULLBACK"))
        # Manually inject CONFIRMED + EXPIRED (real orchestrator would set state)
        store.candidates.append(self._make("ETH/USDT", "CONFIRMED"))
        store.candidates.append(self._make("SOL/USDT", "EXPIRED"))
        store.add(self._make("LINK/USDT", "IN_ZONE"))
        store.save()

        # In-memory list pruned too — invariant after save
        assert len(store.candidates) == 2
        states = sorted(c.state for c in store.candidates)
        assert states == ["AWAITING_PULLBACK", "IN_ZONE"]

        # Reload from disk: only the two active ones present
        store2 = SetupStateStore(tmp_path / "state.json")
        store2.load()
        assert len(store2.candidates) == 2
        symbols = sorted(c.symbol for c in store2.candidates)
        assert symbols == ["BTC/USDT", "LINK/USDT"]

    def test_load_drops_terminal_state_entries(self, tmp_path):
        """If a legacy/corrupted file contains terminal-state entries,
        they are dropped on load with a warning."""
        from engine.smc_v2.setup_state import SetupStateStore, SCHEMA_VERSION
        import json
        # Hand-craft a file with terminal entries (simulating legacy data)
        payload = {
            "version": SCHEMA_VERSION,
            "candidates": [
                {
                    "symbol": "BTC/USDT", "direction": "SHORT",
                    "trigger_bar_ts": 1700000000000, "trigger_price": 100.0,
                    "htf_bias": "BEAR",
                    "target_zone": {"low": 105.0, "high": 110.0, "source": "HTF_FVG"},
                    "htf_swing_anchor": 115.0, "bars_waited": 0,
                    "state": "CONFIRMED", "confluence_score": 70, "reasons": [],
                },
                {
                    "symbol": "ETH/USDT", "direction": "LONG",
                    "trigger_bar_ts": 1700000000000, "trigger_price": 2400.0,
                    "htf_bias": "BULL",
                    "target_zone": {"low": 2380.0, "high": 2390.0, "source": "OTE"},
                    "htf_swing_anchor": 2350.0, "bars_waited": 2,
                    "state": "IN_ZONE", "confluence_score": 60, "reasons": [],
                },
            ],
        }
        path = tmp_path / "state.json"
        path.write_text(json.dumps(payload))

        store = SetupStateStore(path)
        store.load()
        # Only the IN_ZONE candidate survives
        assert len(store.candidates) == 1
        assert store.candidates[0].symbol == "ETH/USDT"
        assert store.candidates[0].state == "IN_ZONE"


class TestPerSymbolCap:
    """add(c) returns False (and does not append) when the per-symbol cap
    of active candidates is reached. Default cap is 3."""

    def _make(self, symbol, state="AWAITING_PULLBACK"):
        from engine.smc_v2.setup_state import SetupCandidate
        return SetupCandidate(
            symbol=symbol, direction="SHORT", trigger_bar_ts=1700000000000,
            trigger_price=100.0, htf_bias="BEAR",
            target_zone=ZoneSpec(low=105.0, high=110.0, source="HTF_FVG"),
            htf_swing_anchor=115.0, bars_waited=0,
            state=state, confluence_score=70, reasons=[],
        )

    def test_add_under_cap_returns_true(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        assert store.add(self._make("BTC/USDT")) is True
        assert store.add(self._make("BTC/USDT")) is True
        assert store.add(self._make("BTC/USDT")) is True
        # Cap reached; 4th rejected
        assert store.add(self._make("BTC/USDT")) is False
        assert len(store.candidates) == 3

    def test_cap_is_per_symbol_not_global(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        # 3 each for two symbols → 6 total, all accepted
        for _ in range(3):
            assert store.add(self._make("BTC/USDT")) is True
        for _ in range(3):
            assert store.add(self._make("ETH/USDT")) is True
        assert len(store.candidates) == 6
        # But a 4th for BTC fails
        assert store.add(self._make("BTC/USDT")) is False

    def test_cap_counts_only_active_states(self, tmp_path):
        """If 2 BTC candidates are CONFIRMED/EXPIRED, a new AWAITING_PULLBACK
        for BTC should be accepted (cap counts only AWAITING_PULLBACK + IN_ZONE)."""
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        store.add(self._make("BTC/USDT", state="AWAITING_PULLBACK"))
        # Inject terminal-state candidates directly (orchestrator would set state)
        store.candidates.append(self._make("BTC/USDT", state="CONFIRMED"))
        store.candidates.append(self._make("BTC/USDT", state="EXPIRED"))
        # 1 active + 2 terminal = 3 total, but cap counts 1 active → 2 more allowed
        assert store.add(self._make("BTC/USDT")) is True
        assert store.add(self._make("BTC/USDT")) is True
        # Now 3 active → 4th rejected
        assert store.add(self._make("BTC/USDT")) is False

    def test_custom_cap_via_constructor(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json", max_pending_per_symbol=1)
        assert store.add(self._make("BTC/USDT")) is True
        assert store.add(self._make("BTC/USDT")) is False


class TestVersionArchival:
    """On schema version mismatch, the old file is archived to
    setup_candidates.v{N}.bak.json before starting empty.
    Silent data loss is worse than archival.
    """

    def test_unknown_version_archives_and_starts_empty(self, tmp_path):
        import json
        from engine.smc_v2.setup_state import SetupStateStore
        path = tmp_path / "state.json"
        # File from a hypothetical future version 99
        path.write_text(json.dumps({"version": 99, "candidates": []}))

        store = SetupStateStore(path)
        store.load()

        # In-memory empty
        assert store.candidates == []
        # Original file moved out of the way
        assert not path.exists()
        # Archived file exists
        archive = path.with_suffix(".v99.bak.json")
        assert archive.exists()
        assert json.loads(archive.read_text()) == {"version": 99, "candidates": []}

    def test_missing_version_treated_as_mismatch(self, tmp_path):
        """A file with no `version` key is also a mismatch — archived."""
        import json
        from engine.smc_v2.setup_state import SetupStateStore
        path = tmp_path / "state.json"
        path.write_text(json.dumps({"candidates": []}))  # no version
        store = SetupStateStore(path)
        store.load()
        assert store.candidates == []
        assert not path.exists()
        # Archived with version "None" suffix
        assert any(p.name.startswith("state.vNone.bak") for p in tmp_path.iterdir())
