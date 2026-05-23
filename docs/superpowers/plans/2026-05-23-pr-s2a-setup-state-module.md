# PR #S2a: SetupCandidate State Module — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure `engine/smc_v2/setup_state.py` module: `SetupCandidate` dataclass + JSON persistence with atomic write, pruning, per-symbol cap, version archival, and corruption recovery. No orchestrator wiring (that lands in PR #S2b).

**Architecture:** A single Python module containing `SetupCandidate` dataclass, `SetupStateStore` class managing the persistence file, and `load_state`/`save_state` functions. Atomic write via `tempfile + os.fsync + os.replace` mirrors the existing `OrderManager._persist` pattern (`exchange/__init__.py:890-904`). Pruning invariant: persisted file contains ONLY candidates with `state ∈ {AWAITING_PULLBACK, IN_ZONE}` — CONFIRMED/EXPIRED dropped before save.

**Tech Stack:** Python 3.12, dataclasses, json stdlib, pathlib, pytest. Zero new external dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §4.1 (setup_state.py) + §4.3 (data flow steps 1/4/5). Spec lives on `origin/feat/smc-v2-spec` (PR #64). To read: `git show origin/feat/smc-v2-spec:docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md`.

**Branch:** `feat/smc-v2-setup-state` — **stacked on `feat/smc-v2-pure-modules`** (PR #65). This is a stacked PR; base of the GitHub PR is PR #65's branch, not master. When PR #65 merges to master, this PR rebases automatically.

**Risk classification:** **Low risk.** New module only, no modification of existing trading code paths. No `engine/safety/`, `exchange/`, `config.yaml` risk/safety, `docker-compose.prod.yml`, or migrations touched. Per CLAUDE.md §4, `efloud-code-reviewer` sufficient; no `efloud-risk-ops-reviewer` gate.

---

## Pre-flight Checks

- [ ] **P1:** Confirm worktree + branch.

```bash
git rev-parse --show-toplevel  # Expected: .../efloud-bot/.worktrees/smc-v2-setup-state
git branch --show-current      # Expected: feat/smc-v2-setup-state
git log --oneline -3
# Expected: HEAD includes "25d31b3 fixup(smc_v2): apply code-review feedback for PR #S1"
```

- [ ] **P2:** Confirm baseline tests pass.

```bash
python -m pytest backend/tests/smc_v2/ -q
# Expected: 41 passed (the PR #S1 modules)
```

- [ ] **P3:** Confirm `engine/smc_v2/` package + dependencies exist.

```bash
ls engine/smc_v2/__init__.py engine/smc_v2/exceptions.py engine/smc_v2/zones.py
# Expected: all three exist (added in PR #S1)
```

If any drift, stop and reconcile before continuing.

---

## File Structure

**Created files** (2):

- `engine/smc_v2/setup_state.py` — `SetupCandidate` dataclass + `SetupStateStore` class + module-level `load_state`/`save_state` helpers
- `backend/tests/smc_v2/test_setup_state.py` — comprehensive unit tests (dataclass shape, round-trip persistence, pruning, cap, version archival, corruption recovery, atomic-write crash recovery)

**Modified files** (0).

**File responsibility boundaries:**

- `SetupCandidate` knows ONLY its own shape (the data of a pending setup). It does not know about state machines or persistence.
- `SetupStateStore` knows ONLY how to manage one JSON file on disk: read on init, atomic-write on demand. It does not advance candidates' state — that's the orchestrator's job in PR #S2b.
- The store enforces the **persistence invariant** (only AWAITING_PULLBACK/IN_ZONE persisted) and **per-symbol cap** (returns `False` from `add_candidate` if over the limit).

**No changes to**: `engine/smc.py`, `engine/smc_v2/zones.py`, `engine/smc_v2/sl_calc.py`, `engine/smc_v2/tp_calc.py`, `engine/smc_v2/exceptions.py`, or any other file outside the two listed above.

---

## Chunk 1: Foundation — SetupCandidate dataclass + ZoneSpec import

### Task 1: SetupCandidate dataclass

**Files:**
- Create: `engine/smc_v2/setup_state.py`
- Create: `backend/tests/smc_v2/test_setup_state.py`

- [ ] **Step 1.1: Write the failing test (dataclass shape)**

Create `backend/tests/smc_v2/test_setup_state.py`:

```python
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
```

- [ ] **Step 1.2: Run to verify it fails**

```bash
python -m pytest backend/tests/smc_v2/test_setup_state.py::TestSetupCandidateDataclass -v
# Expected: FAIL with ModuleNotFoundError: engine.smc_v2.setup_state
```

- [ ] **Step 1.3: Implement the dataclass**

Create `engine/smc_v2/setup_state.py`:

```python
"""SetupCandidate + persistence for SMC v2 pending setups.

A SetupCandidate is created when an LTF CHoCH triggers; the orchestrator
(PR #S2b) advances it across ticks waiting for a pullback into the target
zone and a confirmation. Persisted across bot restarts via SetupStateStore.

Persistence rules (spec §4.1):
- Atomic write via tempfile + os.fsync + os.replace (mirrors OrderManager._persist).
- Persisted file contains ONLY candidates with state ∈ {AWAITING_PULLBACK, IN_ZONE}.
  CONFIRMED and EXPIRED are dropped from the in-memory list before save.
- Per-symbol cap (default 3): trigger phase rejects new candidates if existing
  pending count for that symbol reaches the cap.
- Schema versioned: {"version": 1, "candidates": [...]}.
- Version mismatch on load → archive to setup_candidates.v{N}.bak.json.
- JSON parse error on load → archive to setup_candidates.corrupt.{ts}.bak.json.
- File size cap on load (default 1 MB) → ERROR log, start empty.

Spec: docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md §4.1
"""
from dataclasses import dataclass, field
from typing import List, Literal

from engine.smc_v2.zones import ZoneSpec


@dataclass
class SetupCandidate:
    """A pending pullback setup tracked across orchestrator ticks.

    State machine (one-way forward, no rollback):
        AWAITING_PULLBACK → IN_ZONE → CONFIRMED  (entry placed)
                                  ↘ EXPIRED      (timeout / SL too far / TP too close)

    `bars_waited` increments each tick regardless of price in/out of zone.
    Setup expires only when bars_waited > pullback_timeout_bars.
    """
    symbol: str
    direction: Literal["LONG", "SHORT"]
    trigger_bar_ts: int                            # CHoCH bar timestamp (ms)
    trigger_price: float                           # break price at CHoCH
    htf_bias: str                                  # "BULL" | "BEAR" | "UNDEF"
    target_zone: ZoneSpec
    htf_swing_anchor: float                        # HTF swing for structural SL
    bars_waited: int                               # incremented per orchestrator tick
    state: Literal["AWAITING_PULLBACK", "IN_ZONE", "CONFIRMED", "EXPIRED"]
    confluence_score: int
    reasons: List[str] = field(default_factory=list)
```

- [ ] **Step 1.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_setup_state.py::TestSetupCandidateDataclass -v
# Expected: 2 passed
```

- [ ] **Step 1.5: Commit**

```bash
git add engine/smc_v2/setup_state.py backend/tests/smc_v2/test_setup_state.py
git commit -m "feat(smc_v2): SetupCandidate dataclass

State machine carrier (AWAITING_PULLBACK → IN_ZONE → CONFIRMED/EXPIRED)
for SMC v2 pullback setups tracked across orchestrator ticks.
Persistence (SetupStateStore) lands in next commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: SetupStateStore — round-trip persistence

### Task 2: Round-trip save/load

**Files:**
- Modify: `engine/smc_v2/setup_state.py` — add `SetupStateStore` class + `load_state`/`save_state` helpers
- Modify: `backend/tests/smc_v2/test_setup_state.py` — add `TestSetupStateStoreRoundTrip`

- [ ] **Step 2.1: Write the failing test**

Append to `backend/tests/smc_v2/test_setup_state.py`:

```python
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
```

- [ ] **Step 2.2: Run to verify it fails**

```bash
python -m pytest backend/tests/smc_v2/test_setup_state.py::TestSetupStateStoreRoundTrip -v
# Expected: FAIL with "cannot import name 'SetupStateStore'"
```

- [ ] **Step 2.3: Implement SetupStateStore**

Append to `engine/smc_v2/setup_state.py`:

```python
import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import logging
log = logging.getLogger("efloud.smc_v2.setup_state")


# Persistence config (defaults; can be overridden in constructor)
PERSISTED_STATES = frozenset({"AWAITING_PULLBACK", "IN_ZONE"})
SCHEMA_VERSION = 1
DEFAULT_MAX_FILE_BYTES = 1_000_000   # 1 MB sanity cap on load
DEFAULT_MAX_PENDING_PER_SYMBOL = 3


class SetupStateStore:
    """Manages the on-disk pending-candidates file.

    Lifecycle:
      __init__ → in-memory list empty; file not read yet
      .load()  → read file, populate self.candidates (corrupt files quarantined)
      .add(c)  → append, return True; or return False if over per-symbol cap
      .save()  → atomic write; only AWAITING_PULLBACK/IN_ZONE persisted

    Pruning, cap, and corruption-handling are described in spec §4.1.
    """

    def __init__(
        self,
        path: Path,
        max_pending_per_symbol: int = DEFAULT_MAX_PENDING_PER_SYMBOL,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    ) -> None:
        self.path = Path(path)
        self.max_pending_per_symbol = max_pending_per_symbol
        self.max_file_bytes = max_file_bytes
        self.candidates: list[SetupCandidate] = []

    def add(self, candidate: "SetupCandidate") -> bool:
        """Append a new pending candidate.

        Returns False (and does not append) if the per-symbol cap is reached
        for candidates in active states (AWAITING_PULLBACK, IN_ZONE).
        """
        active_for_symbol = sum(
            1 for c in self.candidates
            if c.symbol == candidate.symbol and c.state in PERSISTED_STATES
        )
        if active_for_symbol >= self.max_pending_per_symbol:
            return False
        self.candidates.append(candidate)
        return True

    def save(self) -> None:
        """Atomic write of active candidates only.

        Prunes CONFIRMED/EXPIRED from the in-memory list before serializing.
        """
        # Prune in-memory list first — CONFIRMED/EXPIRED never persisted
        self.candidates = [c for c in self.candidates if c.state in PERSISTED_STATES]

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "version": SCHEMA_VERSION,
            "candidates": [asdict(c) for c in self.candidates],
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def load(self) -> None:
        """Read the file, populate self.candidates.

        - Nonexistent file → empty list (no error)
        - File > max_file_bytes → ERROR log, empty list
        - Version mismatch → archive + empty list
        - Corrupt JSON → archive + empty list
        - Any candidate with state ∉ PERSISTED_STATES → drop with warning
        """
        self.candidates = []
        if not self.path.exists():
            return

        size = self.path.stat().st_size
        if size > self.max_file_bytes:
            log.error(
                f"setup_state file too large ({size} > {self.max_file_bytes} bytes); "
                f"refusing to load. Investigate {self.path}"
            )
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            self._archive(f"corrupt.{int(time.time())}", reason=f"parse error: {e}")
            return

        ver = payload.get("version")
        if ver != SCHEMA_VERSION:
            self._archive(f"v{ver}", reason=f"schema version mismatch (got {ver})")
            return

        raw = payload.get("candidates", [])
        from engine.smc_v2.zones import ZoneSpec as _ZoneSpec  # local import: clarity
        for item in raw:
            state = item.get("state")
            if state not in PERSISTED_STATES:
                log.warning(
                    f"setup_state load: dropping candidate with state={state} "
                    f"(symbol={item.get('symbol')})"
                )
                continue
            zone_raw = item.get("target_zone", {})
            zone = _ZoneSpec(
                low=zone_raw.get("low"),
                high=zone_raw.get("high"),
                source=zone_raw.get("source"),
            )
            try:
                self.candidates.append(SetupCandidate(
                    symbol=item["symbol"],
                    direction=item["direction"],
                    trigger_bar_ts=item["trigger_bar_ts"],
                    trigger_price=item["trigger_price"],
                    htf_bias=item["htf_bias"],
                    target_zone=zone,
                    htf_swing_anchor=item["htf_swing_anchor"],
                    bars_waited=item["bars_waited"],
                    state=item["state"],
                    confluence_score=item["confluence_score"],
                    reasons=item.get("reasons", []),
                ))
            except (KeyError, TypeError) as e:
                log.warning(
                    f"setup_state load: dropping malformed candidate ({e}): {item}"
                )
                continue

    def _archive(self, suffix: str, reason: str) -> None:
        """Move a problematic file out of the way so a fresh start can proceed."""
        try:
            backup = self.path.with_suffix(f".{suffix}.bak.json")
            os.replace(self.path, backup)
            log.warning(
                f"setup_state archived {self.path} → {backup} (reason: {reason})"
            )
        except OSError as e:
            log.error(f"setup_state archive failed: {e}")
```

- [ ] **Step 2.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_setup_state.py::TestSetupStateStoreRoundTrip -v
# Expected: 4 passed
```

- [ ] **Step 2.5: Commit**

```bash
git add engine/smc_v2/setup_state.py backend/tests/smc_v2/test_setup_state.py
git commit -m "feat(smc_v2): SetupStateStore round-trip persistence

Atomic JSON write (tempfile + fsync + os.replace) mirroring
OrderManager._persist pattern at exchange/__init__.py:890-904.
Mkdir on save; nonexistent on load → empty list.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3: Pruning + per-symbol cap

### Task 3: Pruning invariant — CONFIRMED/EXPIRED dropped before save

**Files:**
- Modify: `backend/tests/smc_v2/test_setup_state.py`

- [ ] **Step 3.1: Write the failing test**

Append:

```python
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
```

- [ ] **Step 3.2: Run to verify (existing code already handles this)**

```bash
python -m pytest backend/tests/smc_v2/test_setup_state.py::TestPruning -v
# Expected: 2 passed (the .save() impl already prunes; .load() already filters)
```

These are **regression pins** for the pruning invariant — they protect against a future refactor that might drop the filter.

- [ ] **Step 3.3: Commit**

```bash
git add backend/tests/smc_v2/test_setup_state.py
git commit -m "test(smc_v2): pin pruning invariant for setup_state persistence

CONFIRMED/EXPIRED never written to disk (save() prunes in-memory
list first). Load() also filters defensively in case a legacy file
contains terminal-state entries.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Per-symbol cap

**Files:**
- Modify: `backend/tests/smc_v2/test_setup_state.py`

- [ ] **Step 4.1: Write the failing test**

Append:

```python
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
```

- [ ] **Step 4.2: Run**

```bash
python -m pytest backend/tests/smc_v2/test_setup_state.py::TestPerSymbolCap -v
# Expected: 4 passed (cap impl is already in place via add())
```

- [ ] **Step 4.3: Commit**

```bash
git add backend/tests/smc_v2/test_setup_state.py
git commit -m "test(smc_v2): pin per-symbol cap behavior for setup_state

add() returns False when the cap is reached. Cap is per-symbol
(not global) and counts only active states (AWAITING_PULLBACK +
IN_ZONE), not terminal states.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 4: Recovery — version archival + corruption + size cap

### Task 5: Version mismatch archival

**Files:**
- Modify: `backend/tests/smc_v2/test_setup_state.py`

- [ ] **Step 5.1: Write the failing test**

Append:

```python
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
```

- [ ] **Step 5.2: Run**

```bash
python -m pytest backend/tests/smc_v2/test_setup_state.py::TestVersionArchival -v
# Expected: 2 passed
```

- [ ] **Step 5.3: Commit**

```bash
git add backend/tests/smc_v2/test_setup_state.py
git commit -m "test(smc_v2): pin version-mismatch archival for setup_state

Unknown / missing version → archive to .v{N}.bak.json, start empty.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Corruption recovery

**Files:**
- Modify: `backend/tests/smc_v2/test_setup_state.py`

- [ ] **Step 6.1: Write the failing test**

Append:

```python
class TestCorruptionRecovery:
    """On JSON parse error, the file is archived to
    setup_candidates.corrupt.{ts}.bak.json before starting empty.
    """

    def test_invalid_json_archives_and_starts_empty(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        path = tmp_path / "state.json"
        path.write_text("{ this is not valid JSON !!! ")

        store = SetupStateStore(path)
        store.load()

        assert store.candidates == []
        assert not path.exists()
        # Some .corrupt.{ts}.bak.json file in the dir
        archives = [p for p in tmp_path.iterdir() if ".corrupt." in p.name]
        assert len(archives) == 1
        assert archives[0].read_text() == "{ this is not valid JSON !!! "

    def test_empty_file_treated_as_corrupt(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        path = tmp_path / "state.json"
        path.write_text("")  # zero-byte file → JSON parse error

        store = SetupStateStore(path)
        store.load()

        assert store.candidates == []
        archives = [p for p in tmp_path.iterdir() if ".corrupt." in p.name]
        assert len(archives) == 1
```

- [ ] **Step 6.2: Run**

```bash
python -m pytest backend/tests/smc_v2/test_setup_state.py::TestCorruptionRecovery -v
# Expected: 2 passed
```

- [ ] **Step 6.3: Commit**

```bash
git add backend/tests/smc_v2/test_setup_state.py
git commit -m "test(smc_v2): pin corruption recovery for setup_state

Invalid JSON / empty file → archive to .corrupt.{ts}.bak.json,
start empty. Spec §4.1 — silent data loss is worse than archival.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: File size cap

**Files:**
- Modify: `backend/tests/smc_v2/test_setup_state.py`

- [ ] **Step 7.1: Write the failing test**

Append:

```python
class TestFileSizeCap:
    """Files larger than max_file_bytes are rejected on load.
    Pathologically large files (~thousands of candidates) indicate
    a bug in the orchestrator — refuse to load, log ERROR, start empty.
    Do NOT archive (we don't want to encourage repeated triggering).
    """

    def test_oversized_file_refused(self, tmp_path):
        import json
        from engine.smc_v2.setup_state import SetupStateStore, SCHEMA_VERSION
        path = tmp_path / "state.json"
        # Write a file larger than our cap
        cap = 1000
        bulk = "x" * (cap + 1)
        path.write_text(json.dumps({
            "version": SCHEMA_VERSION,
            "candidates": [],
            "_padding": bulk,
        }))
        assert path.stat().st_size > cap

        store = SetupStateStore(path, max_file_bytes=cap)
        store.load()

        # Refused: empty list, file NOT moved (operator must investigate)
        assert store.candidates == []
        assert path.exists()  # NOT archived

    def test_under_cap_loads_normally(self, tmp_path):
        import json
        from engine.smc_v2.setup_state import SetupStateStore, SCHEMA_VERSION
        path = tmp_path / "state.json"
        path.write_text(json.dumps({
            "version": SCHEMA_VERSION,
            "candidates": [],
        }))
        store = SetupStateStore(path, max_file_bytes=1_000_000)
        store.load()
        assert store.candidates == []
        assert path.exists()  # still there
```

- [ ] **Step 7.2: Run**

```bash
python -m pytest backend/tests/smc_v2/test_setup_state.py::TestFileSizeCap -v
# Expected: 2 passed
```

- [ ] **Step 7.3: Commit**

```bash
git add backend/tests/smc_v2/test_setup_state.py
git commit -m "test(smc_v2): pin file-size-cap behavior for setup_state

Files > max_file_bytes refused on load (start empty, no archive).
Operator must investigate manually — archiving would encourage
the bug to repeat.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 5: Regression sweep

### Task 8: Whole-suite + py_compile

- [ ] **Step 8.1: Full smc_v2 suite**

```bash
python -m pytest backend/tests/smc_v2/ -v 2>&1 | tail -10
# Expected: 41 (PR #S1) + new TestSetup* tests (2 + 4 + 2 + 4 + 2 + 2 + 2 = 18) = 59
```

- [ ] **Step 8.2: Full backend suite**

```bash
python -m pytest backend/tests/ -q 2>&1 | tail -3
# Expected: 466 baseline + 41 (S1) + 18 (S2a) = 525 passed
```

- [ ] **Step 8.3: py_compile**

```bash
python -m py_compile engine/smc_v2/setup_state.py && echo "compile OK"
# Expected: compile OK
```

- [ ] **Step 8.4: Diff inventory**

```bash
git log feat/smc-v2-setup-state ^feat/smc-v2-pure-modules --oneline
git diff feat/smc-v2-pure-modules..HEAD --stat
# Expected: 7 commits (1 plan + 6 task), only setup_state.py + test_setup_state.py + plan
```

No commit at step 8 unless 8.1-8.3 produced changes.

---

## Out of Scope (explicitly NOT in PR #S2a)

- Orchestrator wiring — PR #S2b (loads state, advances candidates, persists at tick end)
- Confirmation logic + `confirm_entry` — PR #S3
- `select_htf_swing_anchor()` — PR #S3
- Signals dispatch / feature flag — PR #S3
- Backtest in-memory state container — PR #S4
- Lifecycle / db telemetry — PR #S5
- Config block — PR #S6
- Production rollout — PR #S7

---

## Acceptance Criteria

PR #S2a is complete and ready for review when:

1. All steps in Tasks 1-8 are checked off.
2. `python -m pytest backend/tests/smc_v2/test_setup_state.py -v` shows **18 tests passing** (2 dataclass + 4 round-trip + 2 pruning + 4 cap + 2 version + 2 corruption + 2 size).
3. `python -m pytest backend/tests/smc_v2/ -v` shows **59 tests passing** (41 from PR #S1 + 18 new).
4. `python -m pytest backend/tests/ -q` shows the full suite still green (~525 passed).
5. `git log feat/smc-v2-setup-state ^feat/smc-v2-pure-modules --oneline` shows 7 commits (1 plan + 6 task commits + 0 extras).
6. `git diff feat/smc-v2-pure-modules..HEAD --stat` shows **only** `engine/smc_v2/setup_state.py` + `backend/tests/smc_v2/test_setup_state.py` + plan doc — no other files.
7. `efloud-code-reviewer` agent reviewed the diff. No risk-ops gate (no risk-sensitive files touched).
8. GitHub PR opened with base = `feat/smc-v2-pure-modules` (stacked on PR #65).

---

## Post-Plan Workflow

1. After implementation: `superpowers:verification-before-completion` (Iron Law).
2. `superpowers:requesting-code-review` → `efloud-code-reviewer` agent.
3. Apply review feedback if any.
4. `superpowers:finishing-a-development-branch` → push + PR (user-confirm shared-state).
5. Update `memory/smc_v2_rework_initiative.md` PR Status: mark PR #S2a done with PR # link.

---

## References

- Spec: `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §4.1, §4.3
- Persistence pattern reference: `exchange/__init__.py:890-904` (`OrderManager._persist`)
- Initiative tracker: `memory/smc_v2_rework_initiative.md`
- CLAUDE.md §4 (atomic PR discipline)
