# PR #S3c-1: Trigger Phase (Pure Module + Inert Orchestrator Wiring) — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `engine/smc_v2/triggers.py` — a pure function `generate_setup_candidates(...)` that detects new CHoCH events aligned with HTF bias and produces `SetupCandidate` instances (via `select_htf_swing_anchor` + `build_pullback_zones`). Wire into `SafeOrchestrator.run_cycle` behind the existing `setup_state_store is not None` gate. **NO order placement** — that lands in PR #S3c-2.

**Architecture:** Pure detection module orchestrates existing PR #65/#68 primitives. Orchestrator calls it after `_advance_setup_state_tick` to emit new candidates each tick. Per-symbol cap enforced via `store.add()` (returns False if cap reached — silently dropped, logged).

**Tech Stack:** Python 3.12, pandas, pytest. Zero new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §4.3 step 3 (trigger phase data flow).

**Branch:** `feat/smc-v2-trigger-phase` (from master).

**Risk classification:** **RISK-OPS SENSITIVE** — `engine/safe_orchestrator.py` modified. Change is **inert by feature-flag**: `setup_state_store=None` (current production default) → trigger phase not invoked. When wired (PR #S6 feature flag), no orders are placed either — only state mutations. **Real exchange call lands in PR #S3c-2 with explicit risk-ops second pass.**

**Scope discipline**: PR #S3c-1 is ONLY trigger detection + state emission. **Out of scope** (deferred to PR #S3c-2): feature flag dispatch, entry order placement on CONFIRMED, SL/TP calculation invocation, OrderManager.open_position call.

---

## Pre-flight Checks

- [ ] **P1:** Confirm worktree + branch.

```bash
git rev-parse --show-toplevel  # Expected: .../efloud-bot/.worktrees/smc-v2-trigger-phase
git branch --show-current      # Expected: feat/smc-v2-trigger-phase
git log --oneline -3           # Expected: PR #69 squash-merge at top (0f88588)
```

- [ ] **P2:** Confirm baseline tests.

```bash
python -m pytest backend/tests/smc_v2/ -q
# Expected: 104 passed (99 + 5 from PR #S3b)
```

- [ ] **P3:** Confirm dependencies exist.

```bash
python -c "from engine.smc_v2.swing_anchor import select_htf_swing_anchor; from engine.smc_v2.zones import build_pullback_zones, ZoneSpec; from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore; print('OK')"
# Expected: OK
```

---

## File Structure

**Created files** (2):
- `engine/smc_v2/triggers.py` — `generate_setup_candidates(...)` pure function
- `backend/tests/smc_v2/test_triggers.py` — comprehensive unit tests

**Modified files** (2):
- `engine/safe_orchestrator.py` — add `_emit_setup_candidates()` helper + call site in `run_cycle`
- `backend/tests/smc_v2/test_orchestrator_confirm_wiring.py` — add integration test

**No changes to**: `engine/signals.py` (v1 path), `engine/lifecycle.py`, `engine/safety/`, `exchange/`, `config.yaml`, `backend/db.py`, any migration.

---

## Chunk 1: Pure module `triggers.py`

### Task 1: `generate_setup_candidates` pure function

**Files:**
- Create: `engine/smc_v2/triggers.py`
- Create: `backend/tests/smc_v2/test_triggers.py`

- [ ] **Step 1.1: Write the failing tests**

Create `backend/tests/smc_v2/test_triggers.py`:

```python
"""Tests for engine.smc_v2.triggers — pure CHoCH → SetupCandidate generator.

Per spec §4.3 step 3 (trigger phase):
  For each new CHoCH on LTF aligned with HTF bias (recency-filtered):
    1. select_htf_swing_anchor → structural SL reference
    2. build_pullback_zones → target zone (HTF FVG priority, OTE fallback)
    3. Emit SetupCandidate(state=AWAITING_PULLBACK, bars_waited=0)

  Returns list of new candidates. Caller (orchestrator) appends to store
  with per-symbol cap enforcement.
"""
from dataclasses import dataclass
import pytest

from engine.smc import Swing, StructBreak, FVG
from engine.smc_v2.zones import ZoneSpec


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
        # LTF CHoCH BEAR at idx 25, recent (within recency window)
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=25, ts="t25", broken_level=95.0),
        ]
        htf_swings = {
            "swing_highs": [
                Swing(price=120.0, idx=10, ts="t10", is_high=True),
            ],
            "swing_lows": [],
        }
        htf_bars = [
            FakeBar(ordinal=15, high=115, low=100),  # 120 unbroken
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
            ltf_trigger_idx_min=20,  # only consider breaks at idx >= 20
        )
        assert len(candidates) == 1
        c = candidates[0]
        assert c.symbol == "BTC/USDT"
        assert c.direction == "SHORT"
        assert c.trigger_price == 100.0
        assert c.trigger_bar_ts == 25  # uses brk.idx as ordinal ts
        assert c.htf_bias == "BEAR"
        assert c.htf_swing_anchor == 120.0
        assert c.target_zone.low == 110.0    # FVG bot for SHORT
        assert c.target_zone.high == 115.0   # FVG top
        assert c.target_zone.source == "HTF_FVG"
        assert c.state == "AWAITING_PULLBACK"
        assert c.bars_waited == 0

    def test_skips_choch_misaligned_with_bias(self):
        """A BULL CHoCH when HTF bias is BEAR → ignored."""
        from engine.smc_v2.triggers import generate_setup_candidates
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BULL", price=100.0,
                        idx=25, ts="t25", broken_level=95.0),
        ]
        candidates = generate_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [], "swing_lows": []},
            htf_bars=[],
            htf_fvgs=[],
            ote_band=(0.0, 0.0),
            ltf_trigger_idx_min=20,
        )
        assert candidates == []

    def test_skips_bos_only_choch_in_pr_s3c_1(self):
        """PR #S3c-1 emits ONLY for CHoCH events. BOS is deferred to a
        follow-up (matches v1 signals.py recency-tighter BOS handling)."""
        from engine.smc_v2.triggers import generate_setup_candidates
        ltf_brks = [
            StructBreak(kind="BOS", direction="BEAR", price=100.0,
                        idx=25, ts="t25", broken_level=95.0),
        ]
        candidates = generate_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [], "swing_lows": []},
            htf_bars=[],
            htf_fvgs=[],
            ote_band=(0.0, 0.0),
            ltf_trigger_idx_min=20,
        )
        # BOS not emitted in PR #S3c-1
        assert candidates == []

    def test_skips_stale_choch_before_trigger_window(self):
        """A CHoCH older than ltf_trigger_idx_min → ignored."""
        from engine.smc_v2.triggers import generate_setup_candidates
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=10, ts="t10", broken_level=95.0),  # too old
        ]
        candidates = generate_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [Swing(120.0, 5, "t5", True)],
                        "swing_lows": []},
            htf_bars=[FakeBar(ordinal=8, high=115, low=100)],
            htf_fvgs=[FVG(top=115.0, bot=110.0, idx=4, ts="t4", direction="BULL")],
            ote_band=(105.0, 108.0),
            ltf_trigger_idx_min=20,  # idx=10 < 20 → skip
        )
        assert candidates == []

    def test_skips_when_no_unbroken_swing_anchor(self):
        """If select_htf_swing_anchor returns None, no candidate emitted
        (no structural SL anchor available)."""
        from engine.smc_v2.triggers import generate_setup_candidates
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=25, ts="t25", broken_level=95.0),
        ]
        # No swings → swing_anchor returns None
        candidates = generate_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [], "swing_lows": []},
            htf_bars=[],
            htf_fvgs=[],
            ote_band=(105.0, 108.0),
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
            FakeBar(ordinal=15, high=2440, low=2380),  # 2350 unbroken
        ]
        htf_fvgs = [
            FVG(top=2390.0, bot=2380.0, idx=12, ts="t12", direction="BEAR"),
        ]
        ote_band = (2370.0, 2375.0)

        candidates = generate_setup_candidates(
            symbol="ETH/USDT",
            htf_bias="BULL",
            ltf_structure_breaks=ltf_brks,
            htf_swings=htf_swings,
            htf_bars=htf_bars,
            htf_fvgs=htf_fvgs,
            ote_band=ote_band,
            ltf_trigger_idx_min=20,
        )
        assert len(candidates) == 1
        c = candidates[0]
        assert c.direction == "LONG"
        assert c.htf_swing_anchor == 2350.0
        assert c.target_zone.source == "HTF_FVG"  # BEAR FVG below trigger


class TestMultipleBreaks:
    """When multiple breaks are present, only aligned-and-recent ones emit."""

    def test_emits_for_each_aligned_recent_choch(self):
        from engine.smc_v2.triggers import generate_setup_candidates
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=22, ts="t22", broken_level=95.0),
            StructBreak(kind="CHoCH", direction="BULL", price=98.0,   # misaligned
                        idx=23, ts="t23", broken_level=100.0),
            StructBreak(kind="CHoCH", direction="BEAR", price=99.0,
                        idx=25, ts="t25", broken_level=94.0),
            StructBreak(kind="BOS", direction="BEAR", price=97.0,     # BOS skipped
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
        # 2 aligned + recent + CHoCH (idx 22 and 25); BULL skipped, BOS skipped
        assert len(candidates) == 2
        assert all(c.direction == "SHORT" for c in candidates)


class TestUndefinedBias:
    """HTF bias UNDEF → no candidates (no directional anchor)."""

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
```

- [ ] **Step 1.2: Run to verify fail**

```bash
python -m pytest backend/tests/smc_v2/test_triggers.py -v
# Expected: many FAIL — ModuleNotFoundError: engine.smc_v2.triggers
```

- [ ] **Step 1.3: Implement `triggers.py`**

Create `engine/smc_v2/triggers.py`:

```python
"""Trigger phase for SMC v2: CHoCH detection → SetupCandidate emission.

Per spec §4.3 step 3:
  For each new CHoCH on LTF (15m) aligned with HTF (4h) bias:
    1. select_htf_swing_anchor → structural SL reference
    2. build_pullback_zones → target zone (HTF FVG priority, OTE fallback)
    3. Emit SetupCandidate(state=AWAITING_PULLBACK, bars_waited=0)

Pure function. Returns list of new candidates. Caller (orchestrator) appends
to SetupStateStore — store.add() enforces per-symbol cap.

Scope limited to CHoCH events (BOS deferred — matches v1 signals.py
recency-tighter BOS handling, see signals.py:200-204).
"""
from typing import List, Tuple

from engine.smc import StructBreak, Swing, FVG
from engine.smc_v2.setup_state import SetupCandidate
from engine.smc_v2.swing_anchor import select_htf_swing_anchor
from engine.smc_v2.zones import build_pullback_zones


def generate_setup_candidates(
    symbol: str,
    htf_bias: str,
    ltf_structure_breaks: List[StructBreak],
    htf_swings: dict,
    htf_bars: list,
    htf_fvgs: List[FVG],
    ote_band: Tuple[float, float],
    ltf_trigger_idx_min: int,
) -> List[SetupCandidate]:
    """Emit SetupCandidate instances for new aligned CHoCH events.

    Args:
        symbol: trading pair
        htf_bias: "BULL" | "BEAR" | "UNDEF" — HTF directional bias
        ltf_structure_breaks: LTF (15m) structure breaks (CHoCH/BOS) from
            SMCEngine.structure() on df_15m
        htf_swings: {"swing_highs": [...], "swing_lows": [...]} for SL anchor
        htf_bars: HTF OHLC bars with .ordinal/.high/.low (for swing_anchor
            unbroken check). Caller enumerates df_htf to produce these.
        htf_fvgs: unmitigated HTF FVGs for build_pullback_zones priority
        ote_band: (low, high) of HTF OTE 0.618-0.786 fib region (fallback zone)
        ltf_trigger_idx_min: int — only consider breaks with idx >= this
            (recency filter; mirrors v1 signals.py:198 recency_cutoff)

    Returns:
        List of new SetupCandidate instances (state=AWAITING_PULLBACK,
        bars_waited=0). Caller must add each to SetupStateStore.add()
        which applies per-symbol cap.
    """
    if htf_bias == "UNDEF":
        return []

    out: List[SetupCandidate] = []
    for brk in ltf_structure_breaks:
        # PR #S3c-1 emits only for CHoCH (reversal). BOS (continuation)
        # deferred — v1 signals.py handles BOS with a tighter recency
        # window (signals.py:200-204).
        if brk.kind != "CHoCH":
            continue

        # Aligned with HTF bias only
        if brk.direction != htf_bias:
            continue

        # Recency filter
        if brk.idx < ltf_trigger_idx_min:
            continue

        # Map BULL → LONG, BEAR → SHORT
        direction = "LONG" if brk.direction == "BULL" else "SHORT"

        # Select structural SL anchor (most-recent-unbroken HTF swing)
        anchor = select_htf_swing_anchor(
            htf_swings=htf_swings,
            direction=direction,
            trigger_idx=brk.idx,
            htf_bars=htf_bars,
        )
        if anchor is None:
            # No valid HTF anchor → can't compute structural SL → skip
            continue

        # Build pullback zone (HTF FVG priority, OTE fallback)
        zone = build_pullback_zones(
            htf_fvgs=htf_fvgs,
            ote_band=ote_band,
            direction=direction,
            trigger_price=brk.price,
        )

        out.append(SetupCandidate(
            symbol=symbol,
            direction=direction,
            trigger_bar_ts=brk.idx,  # ordinal axis (matches swing_anchor)
            trigger_price=brk.price,
            htf_bias=htf_bias,
            target_zone=zone,
            htf_swing_anchor=anchor,
            bars_waited=0,
            state="AWAITING_PULLBACK",
            confluence_score=0,  # PR #S3c-2 may add confluence scoring
            reasons=[f"CHoCH {brk.direction} aligned with HTF {htf_bias}"],
        ))

    return out
```

- [ ] **Step 1.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_triggers.py -v
# Expected: 8 passed (5 SHORT + 1 LONG + 1 multiple + 1 undef)
```

- [ ] **Step 1.5: Regression check**

```bash
python -m pytest backend/tests/smc_v2/ -q
# Expected: 104 baseline + 8 new = 112 passed
```

- [ ] **Step 1.6: Commit**

```bash
git add engine/smc_v2/triggers.py backend/tests/smc_v2/test_triggers.py
git commit -m "feat(smc_v2): triggers.py — CHoCH → SetupCandidate generator

Pure function per spec §4.3 step 3. Detects new CHoCH events on
LTF aligned with HTF bias (within recency window), then:
- select_htf_swing_anchor for structural SL reference
- build_pullback_zones for target zone (HTF FVG > OTE)
- Emit SetupCandidate(state=AWAITING_PULLBACK)

Scope limited to CHoCH (BOS deferred — matches v1 signals.py
recency-tighter BOS handling). No order placement (PR #S3c-2).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: Orchestrator inert wiring

### Task 2: `_emit_setup_candidates()` helper + run_cycle call

**Files:**
- Modify: `engine/safe_orchestrator.py` — add helper after `_advance_setup_state_tick`
- Modify: `engine/safe_orchestrator.py:run_cycle` — call helper after advance, before save
- Modify: `backend/tests/smc_v2/test_orchestrator_confirm_wiring.py` — integration test

- [ ] **Step 2.1: Write the failing test**

Append to `test_orchestrator_confirm_wiring.py`:

```python
class TestTriggerPhaseInert:
    """PR #S3c-1: orchestrator emits SetupCandidates only when
    setup_state_store is wired. v1 path (store=None) unchanged."""

    def test_inert_when_store_none(self, tmp_path):
        """No store → no _emit_setup_candidates side effect."""
        orc = SafeOrchestrator(_minimal_config(), state_dir=str(tmp_path), persist=False)
        # Should NOT raise even without store
        orc._emit_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BEAR",
            ltf_structure_breaks=[],
            htf_swings={"swing_highs": [], "swing_lows": []},
            htf_bars=[],
            htf_fvgs=[],
            ote_band=(0.0, 0.0),
            ltf_trigger_idx_min=0,
        )

    def test_emits_to_store_when_wired(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        from engine.smc import StructBreak, Swing, FVG
        from dataclasses import dataclass

        @dataclass
        class FakeBar:
            ordinal: int
            high: float
            low: float

        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=25, ts="t25", broken_level=95.0),
        ]
        orc._emit_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [Swing(120.0, 10, "t10", True)],
                        "swing_lows": []},
            htf_bars=[FakeBar(ordinal=15, high=115, low=100)],
            htf_fvgs=[FVG(top=115.0, bot=110.0, idx=12, ts="t12", direction="BULL")],
            ote_band=(105.0, 108.0),
            ltf_trigger_idx_min=20,
        )
        assert len(store.candidates) == 1
        assert store.candidates[0].symbol == "BTC/USDT"
        assert store.candidates[0].direction == "SHORT"
        assert store.candidates[0].state == "AWAITING_PULLBACK"

    def test_per_symbol_cap_respected(self, tmp_path):
        """If store cap is reached, additional candidates are silently dropped."""
        from engine.smc_v2.setup_state import SetupStateStore, SetupCandidate
        from engine.smc import StructBreak, Swing, FVG
        from engine.smc_v2.zones import ZoneSpec
        from dataclasses import dataclass

        @dataclass
        class FakeBar:
            ordinal: int
            high: float
            low: float

        # Pre-fill store to per-symbol cap
        store = SetupStateStore(tmp_path / "state.json", max_pending_per_symbol=1)
        store.add(SetupCandidate(
            symbol="BTC/USDT", direction="SHORT", trigger_bar_ts=10,
            trigger_price=99.0, htf_bias="BEAR",
            target_zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
            htf_swing_anchor=120.0, bars_waited=0,
            state="AWAITING_PULLBACK", confluence_score=0, reasons=[],
        ))

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=25, ts="t25", broken_level=95.0),
        ]
        orc._emit_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [Swing(120.0, 10, "t10", True)],
                        "swing_lows": []},
            htf_bars=[FakeBar(ordinal=15, high=115, low=100)],
            htf_fvgs=[FVG(top=115.0, bot=110.0, idx=12, ts="t12", direction="BULL")],
            ote_band=(105.0, 108.0),
            ltf_trigger_idx_min=20,
        )
        # Cap was 1; pre-existing 1 candidate → new one dropped
        assert len(store.candidates) == 1
```

- [ ] **Step 2.2: Run to verify fail**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_confirm_wiring.py::TestTriggerPhaseInert -v
# Expected: FAIL — _emit_setup_candidates method doesn't exist
```

- [ ] **Step 2.3: Add `_emit_setup_candidates()` to SafeOrchestrator**

In `engine/safe_orchestrator.py`, find `_advance_setup_state_tick` (around line 1042). Add immediately after:

```python
    def _emit_setup_candidates(
        self,
        symbol: str,
        htf_bias: str,
        ltf_structure_breaks: list,
        htf_swings: dict,
        htf_bars: list,
        htf_fvgs: list,
        ote_band: tuple,
        ltf_trigger_idx_min: int,
    ) -> None:
        """Trigger phase: detect new CHoCH events and emit SetupCandidates.

        Per spec §4.3 step 3. Calls engine.smc_v2.triggers.generate_setup_candidates
        and appends each candidate to self.setup_state_store via store.add()
        (which enforces per-symbol cap; over-cap candidates silently dropped).

        Inert when self.setup_state_store is None — short-circuits.
        """
        if self.setup_state_store is None:
            return

        # Local import to avoid circular dep with smc_v2 package
        from engine.smc_v2.triggers import generate_setup_candidates

        new_candidates = generate_setup_candidates(
            symbol=symbol,
            htf_bias=htf_bias,
            ltf_structure_breaks=ltf_structure_breaks,
            htf_swings=htf_swings,
            htf_bars=htf_bars,
            htf_fvgs=htf_fvgs,
            ote_band=ote_band,
            ltf_trigger_idx_min=ltf_trigger_idx_min,
        )
        for cand in new_candidates:
            # add() returns False if per-symbol cap reached — silently dropped
            # (matches spec §6 setup_cap rejection counter; orchestrator
            # could log this in a future patch if operator visibility wanted)
            self.setup_state_store.add(cand)
```

- [ ] **Step 2.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_confirm_wiring.py::TestTriggerPhaseInert -v
# Expected: 3 passed
```

- [ ] **Step 2.5: V1 regression check (CRITICAL)**

```bash
python -m pytest backend/tests/test_orchestrator_order_bridge.py backend/tests/test_safe_orchestrator_client_attr.py backend/tests/test_safe_orchestrator_flags.py -q
# Expected: 12 passed (v1 untouched — _emit_setup_candidates not invoked from v1 path)
```

PR #S3c-1 does NOT call `_emit_setup_candidates` from `run_cycle` yet. That wiring is Task 3.

- [ ] **Step 2.6: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/smc_v2/test_orchestrator_confirm_wiring.py
git commit -m "feat(orchestrator): _emit_setup_candidates helper (PR #S3c-1)

Inert opt-in helper invoking engine.smc_v2.triggers.generate_setup_candidates.
When setup_state_store is None, short-circuits. Otherwise appends each
new candidate via store.add() — per-symbol cap enforced silently.

Helper exists; not yet called from run_cycle (Task 3 wires it).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Wire `_emit_setup_candidates` into `run_cycle`

The trigger phase must run AFTER `_advance_setup_state_tick` (so existing candidates advance first) but BEFORE `save()` (so new candidates persist).

**Files:**
- Modify: `engine/safe_orchestrator.py:run_cycle` — add trigger phase call after advance

- [ ] **Step 3.1: Write the failing integration test**

Append to `test_orchestrator_confirm_wiring.py`:

```python
class TestRunCycleTriggerPhase:
    """run_cycle invokes _emit_setup_candidates after advance, before save."""

    def _make_df(self, length=50, base_price=95000.0):
        import pandas as pd
        from datetime import datetime, timezone
        idx = pd.date_range(
            end=datetime.now(timezone.utc), periods=length, freq="15min", tz="UTC",
        )
        return pd.DataFrame({
            "open": [base_price] * length,
            "high": [base_price * 1.001] * length,
            "low": [base_price * 0.999] * length,
            "close": [base_price] * length,
            "volume": [1000.0] * length,
        }, index=idx)

    def test_run_cycle_calls_emit_when_store_wired(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        from unittest.mock import patch

        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store, freshness_check=False,
        )
        df = self._make_df()
        with patch.object(orc, "_emit_setup_candidates") as spy:
            orc.run_cycle(
                symbol="BTC/USDT", df_htf=df, df_mtf=df, df_entry=df,
                balance=10000.0,
            )
            assert spy.call_count == 1
            kwargs = spy.call_args.kwargs
            assert kwargs["symbol"] == "BTC/USDT"
            assert "ltf_structure_breaks" in kwargs
            assert "htf_swings" in kwargs

    def test_run_cycle_emit_not_called_when_store_none(self, tmp_path):
        """Inert: no store → _emit_setup_candidates not called."""
        from unittest.mock import patch

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            freshness_check=False,
        )
        df = self._make_df()
        with patch.object(orc, "_emit_setup_candidates") as spy:
            orc.run_cycle(
                symbol="BTC/USDT", df_htf=df, df_mtf=df, df_entry=df,
                balance=10000.0,
            )
            assert spy.call_count == 0
```

- [ ] **Step 3.2: Run to verify fail**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_confirm_wiring.py::TestRunCycleTriggerPhase -v
# Expected: FAIL — _emit_setup_candidates not called from run_cycle
```

- [ ] **Step 3.3: Wire into `run_cycle`**

In `engine/safe_orchestrator.py`, find the `_advance_setup_state_tick` call in `run_cycle` (around line 525-532). After it, add the trigger phase call:

**BEFORE:**
```python
        if self.setup_state_store is not None:
            current_bar_ts = int(df_entry.index[-1].timestamp() * 1000)
            self._advance_setup_state_tick(
                symbol=symbol,
                current_price=current_price,
                current_bar_ts=current_bar_ts,
                df_15m=df_entry,
            )
```

**AFTER:**
```python
        if self.setup_state_store is not None:
            current_bar_ts = int(df_entry.index[-1].timestamp() * 1000)
            self._advance_setup_state_tick(
                symbol=symbol,
                current_price=current_price,
                current_bar_ts=current_bar_ts,
                df_15m=df_entry,
            )

            # SMC v2 trigger phase: detect new CHoCH → emit SetupCandidates.
            # Per spec §4.3 step 3. Runs AFTER advance (existing candidates
            # progress first) and BEFORE save (new candidates persisted).
            #
            # Inputs derived from SMC engine results computed downstream.
            # For PR #S3c-1 we compute them inline here. Future PR may
            # refactor to share with the v1 signals path.
            htf_analysis = self.smc.analyze(df_htf)
            ltf_swings_h, ltf_swings_l = self.smc.swings(df_entry)
            ltf_brks = self.smc.structure(df_entry, ltf_swings_h, ltf_swings_l)

            # Build htf_bars from df_htf rows (ordinal axis for swing_anchor)
            from dataclasses import dataclass as _dc

            @_dc
            class _HtfBar:
                ordinal: int
                high: float
                low: float

            htf_bars = [
                _HtfBar(ordinal=i, high=float(row["high"]), low=float(row["low"]))
                for i, (_, row) in enumerate(df_htf.iterrows())
            ]

            # Recency cutoff: only consider LTF breaks in last N bars
            recency = self.config.get("risk", {}).get("recency_bars", 40)
            ltf_trigger_idx_min = max(0, len(df_entry) - 1 - recency)

            # OTE band: from htf_analysis if available, else degenerate
            ote_obj = htf_analysis.get("ote")
            if ote_obj is not None:
                ote_low, ote_high = min(ote_obj.bot, ote_obj.top), max(ote_obj.bot, ote_obj.top)
            else:
                ote_low, ote_high = 0.0, 0.0

            self._emit_setup_candidates(
                symbol=symbol,
                htf_bias=htf_analysis.get("trend", "UNDEF"),
                ltf_structure_breaks=ltf_brks,
                htf_swings={
                    "swing_highs": htf_analysis.get("swing_highs", []),
                    "swing_lows": htf_analysis.get("swing_lows", []),
                },
                htf_bars=htf_bars,
                htf_fvgs=htf_analysis.get("active_fvgs", []),
                ote_band=(ote_low, ote_high),
                ltf_trigger_idx_min=ltf_trigger_idx_min,
            )
```

**Note on the wiring**: We call `self.smc.analyze(df_htf)` here. This duplicates work that signals.py also does — acceptable for PR #S3c-1 (will be deduplicated in a future refactor if needed). The duplication is OPT-IN via setup_state_store, so v1 path pays no cost.

- [ ] **Step 3.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_confirm_wiring.py::TestRunCycleTriggerPhase -v
# Expected: 2 passed
```

- [ ] **Step 3.5: V1 + PR #67 + PR #S3b regression (CRITICAL)**

```bash
python -m pytest backend/tests/test_orchestrator_order_bridge.py backend/tests/test_safe_orchestrator_client_attr.py backend/tests/test_safe_orchestrator_flags.py backend/tests/smc_v2/test_orchestrator_state_tick.py backend/tests/smc_v2/test_orchestrator_confirm_wiring.py -q
# Expected: 12 + 17 + (5 + 5) = 39 passed (5 PR #S3b proxy tests + 5 PR #S3c-1 new tests across 2 classes)
```

- [ ] **Step 3.6: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/smc_v2/test_orchestrator_confirm_wiring.py
git commit -m "feat(orchestrator): wire trigger phase into run_cycle (PR #S3c-1)

Per spec §4.3 step 3. After _advance_setup_state_tick advances
existing candidates, trigger phase calls self.smc.analyze() on
HTF + ltf structure(), then _emit_setup_candidates() for any
new CHoCH events aligned with HTF bias.

Gated by setup_state_store is not None — v1 path untouched.

v1 regression: 12 v1 orchestrator tests green. PR #67 + PR #S3b
tests green. Full integration: 39 tests across orchestrator suite.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3: Final regression sweep

### Task 4: Whole-suite + py_compile

- [ ] **Step 4.1: Full smc_v2 suite**

```bash
python -m pytest backend/tests/smc_v2/ -v 2>&1 | tail -10
# Expected: 104 baseline + 8 (triggers) + 5 (orchestrator integration) = 117 passed
```

- [ ] **Step 4.2: Full backend suite (regression)**

```bash
python -m pytest backend/tests/ -q 2>&1 | tail -3
# Expected: 581 baseline + 13 (PR #S3c-1) = 594 passed
```

- [ ] **Step 4.3: py_compile**

```bash
python -m py_compile engine/smc_v2/triggers.py engine/safe_orchestrator.py && echo "compile OK"
```

- [ ] **Step 4.4: Diff inventory**

```bash
git log feat/smc-v2-trigger-phase ^master --oneline
git diff master..HEAD --stat
# Expected: 4 commits (1 plan + 3 task), only triggers.py + safe_orchestrator.py + 2 test files + plan
```

---

## Out of Scope (explicitly NOT in PR #S3c-1)

- **Feature flag dispatch** (`engine.smc_version`) — PR #S3c-2 / #S6
- **Entry order placement on CONFIRMED** — PR #S3c-2 (real exchange call, RISK-OPS CRITICAL)
- **`_calc_sl` + `_calc_tp_targets` invocation** — PR #S3c-2 alongside order placement
- **BOS trigger support** — deferred (v1 has tighter recency for BOS; rework needed)
- **Confluence scoring** for v2 triggers — deferred (PR #S3c-2 or later)
- **Logging telemetry** for emit/dropped counts — operator-visibility patch later

---

## Acceptance Criteria

1. All steps in Tasks 1-4 checked off.
2. `pytest backend/tests/smc_v2/test_triggers.py -v` → 8 passed
3. `pytest backend/tests/smc_v2/test_orchestrator_confirm_wiring.py -v` → 10 passed (5 PR #S3b proxy + 5 PR #S3c-1: 3 emit + 2 run_cycle)
4. `pytest backend/tests/smc_v2/test_orchestrator_state_tick.py -v` → 17 passed (PR #67 regression intact)
5. `pytest backend/tests/test_orchestrator_*.py -q` → 12 passed (v1 regression)
6. `pytest backend/tests/smc_v2/ -q` → 117 passed (104 + 13)
7. `pytest backend/tests/ -q` → 594 passed full suite
8. `efloud-code-reviewer` reviewed; risk-ops note: change inert under prod config (setup_state_store=None), no real orders, no exchange call — risk-ops second pass not required this PR (re-escalate at PR #S3c-2).

---

## Post-Plan Workflow

1. `verification-before-completion` (Iron Law)
2. `requesting-code-review` → efloud-code-reviewer
3. `finishing-a-development-branch` → push + PR (user-confirm shared state)
4. Hermes-mode: ratchet score → APPROVE → merge → memory update

---

## References

- Spec: `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §4.3 step 3
- Pure modules consumed: `engine.smc_v2.{swing_anchor, zones, setup_state}`
- Base orchestrator wiring: PR #67 + PR #S3b (already in master)
- Initiative tracker: `memory/smc_v2_rework_initiative.md`
