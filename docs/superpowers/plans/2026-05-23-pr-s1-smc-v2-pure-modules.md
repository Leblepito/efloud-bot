# PR #S1: smc_v2 Pure Modules — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the four pure-function modules of the SMC v2 engine (`zones.py`, `sl_calc.py`, `tp_calc.py`) plus a new `liquidity_pools()` method on the existing `SMCEngine`, with 100% line + branch test coverage. No integration with orchestrator, signals, or lifecycle — those land in subsequent PRs.

**Architecture:** A new `engine/smc_v2/` package holds the pure modules. Each module is a single-responsibility unit operating on DataFrames + dataclass inputs, producing scalars or dataclass outputs. No CCXT, no file I/O, no network. The existing `engine/smc.py` gets one new method `liquidity_pools(df, eq_threshold)` that clusters equal highs/lows into `EqLevel` records (the input format `tp_calc.py` consumes).

**Tech Stack:** Python 3.12, dataclasses, pandas (already a dep for SMC), pytest. Zero new external dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §4.1 (Component design — new files) and §5 (SL/TP math formulas). The spec lives on `feat/smc-v2-spec` branch and on remote `origin/feat/smc-v2-spec` (PR #64 awaiting Hermes review). To read it from this worktree: `git show origin/feat/smc-v2-spec:docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md`.

**Branch:** `feat/smc-v2-pure-modules` (worktree at `.worktrees/smc-v2-pure-modules`)

**Risk classification:** Low risk. New files only, no modification of existing trading code paths. The new `liquidity_pools()` method on `SMCEngine` is additive (existing `equal_levels()` is untouched). No `efloud-risk-ops-reviewer` requirement (`engine/safety/`, `exchange/`, risk config untouched). General `efloud-code-reviewer` sufficient.

**Companion PR:** PR #64 (spec). If spec receives revisions from Hermes that change API signatures of these pure modules, this PR's fixup may be required. Risk: low — the signatures are derived directly from spec §4.1 which is APPROVED post-2-iter-review.

---

## Pre-flight Checks

- [ ] **P1:** Confirm working directory is the worktree, not main repo.

```bash
git rev-parse --show-toplevel
# Expected: .../efloud-bot/.worktrees/smc-v2-pure-modules
git branch --show-current
# Expected: feat/smc-v2-pure-modules
```

- [ ] **P2:** Confirm baseline tests pass.

```bash
python -m pytest backend/tests/ -q 2>&1 | tail -3
# Expected: 466 passed
```

- [ ] **P3:** Confirm existing SMC dataclasses are at expected locations (used by the new modules).

```bash
grep -n "^class \(Swing\|FVG\|OrderBlock\|RangeInfo\)\b" engine/smc.py | head -10
# Expected: classes at engine/smc.py lines 20, 38, 48, 71
grep -n "def equal_levels" engine/smc.py
# Expected: ~line 285
```

If any of these have drifted, stop and reconcile before continuing.

---

## File Structure

**Created files** (5 new):

- `engine/smc_v2/__init__.py` — package marker + public re-exports (signatures only; orchestration lives in PR #S3)
- `engine/smc_v2/zones.py` — pullback target builder (FVG priority → OTE fallback)
- `engine/smc_v2/sl_calc.py` — structural SL with ATR buffer + clamp + REJECT on too-far
- `engine/smc_v2/tp_calc.py` — liquidity-first TP1 + FVG-fill TP2 with strict TP2>TP1 invariant
- `engine/smc_v2/exceptions.py` — `SLTooFarError`, `InsufficientTPDistanceError` (shared exception module)

**Modified files** (2):

- `engine/smc.py` — add new method `SMCEngine.liquidity_pools(df, eq_threshold)` and a new `EqLevel` dataclass at module top. Existing `equal_levels()` is untouched.

**Created test files** (5):

- `backend/tests/smc_v2/__init__.py` — empty package marker
- `backend/tests/smc_v2/test_zones.py` — pullback zone builder unit tests
- `backend/tests/smc_v2/test_sl_calc.py` — SL calculation unit tests (structural, buffer, clamp, reject)
- `backend/tests/smc_v2/test_tp_calc.py` — TP1/TP2 calculation unit tests (liquidity, FVG, fallback, invariant)
- `backend/tests/smc_v2/test_liquidity_pools.py` — `SMCEngine.liquidity_pools` unit tests

**No changes to**: `engine/signals.py`, `engine/safe_orchestrator.py`, `engine/lifecycle.py`, `exchange/`, `engine/safety/`, `config.yaml`, `backend/db.py`, any migration. **No schema changes, no config changes.**

**File responsibility boundaries:**

- `zones.py` knows ONLY how to pick a pullback target from FVG list / OTE band. It does not know about signals, positions, or orders.
- `sl_calc.py` knows ONLY how to compute SL price from inputs. It raises `SLTooFarError` instead of returning None — the caller (PR #S3) decides what to do with the rejection.
- `tp_calc.py` knows ONLY how to compute TP1 + TP2 from inputs. It raises `InsufficientTPDistanceError` instead of returning None. TP2 may legitimately be None (single-target mode); that is signalled by returning `(tp1, None, source_tags)` not by raising.
- `liquidity_pools()` knows ONLY how to cluster equal highs/lows into `EqLevel` records. It does not consume `EqLevel` itself.

---

## Chunk 1: Foundation — exceptions, EqLevel, liquidity_pools

### Task 1: Create exceptions module

**Files:**
- Create: `engine/smc_v2/__init__.py`
- Create: `engine/smc_v2/exceptions.py`
- Create: `backend/tests/smc_v2/__init__.py`

- [ ] **Step 1.1: Create the package skeleton**

Write `engine/smc_v2/__init__.py`:

```python
"""SMC v2 engine — pullback-to-FVG/OTE entry with LTF confirmation.

This package holds pure-function modules for SMC v2 signal generation.
Orchestration (state machine, signal emission) lives in engine/smc_v2/__init__.py
after PR #S3. For PR #S1 this is an empty package marker.

Spec: docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md §4.1
"""
```

Write `engine/smc_v2/exceptions.py`:

```python
"""SMC v2 setup rejection exceptions.

These are raised by sl_calc.calc_sl and tp_calc.calc_tp_targets to signal
that a setup must be rejected. The caller (orchestrator in PR #S3) catches
them and counts the rejection reason (see spec §6).
"""


class SLTooFarError(ValueError):
    """Raised when structural SL distance exceeds max_sl_atr * ATR.

    Setup must be rejected — clamping to the max would invalidate the SMC
    structure (SL placed at an unrelated price level).
    """

    def __init__(self, stop_dist: float, max_dist: float):
        self.stop_dist = stop_dist
        self.max_dist = max_dist
        super().__init__(
            f"Structural SL distance {stop_dist:.6f} exceeds max {max_dist:.6f} "
            f"(max_sl_atr * ATR). Setup rejected."
        )


class InsufficientTPDistanceError(ValueError):
    """Raised when the nearest valid liquidity/FVG target is closer than min_rr * risk.

    Setup must be rejected — projecting a synthetic TP at min_rr would ignore
    the real structural target and produce unrealistic expectations.
    """

    def __init__(self, nearest: float, required: float):
        self.nearest = nearest
        self.required = required
        super().__init__(
            f"Nearest TP candidate {nearest:.6f} is within required min distance "
            f"{required:.6f}. Setup rejected."
        )
```

Write `backend/tests/smc_v2/__init__.py` (empty file — package marker):

```python
```

- [ ] **Step 1.2: Verify imports work**

```bash
python -c "from engine.smc_v2.exceptions import SLTooFarError, InsufficientTPDistanceError; print('OK')"
# Expected: OK
```

- [ ] **Step 1.3: Commit**

```bash
git add engine/smc_v2/ backend/tests/smc_v2/__init__.py
git commit -m "feat(smc_v2): scaffold package + rejection exceptions

Empty package marker + two exception types (SLTooFarError,
InsufficientTPDistanceError) used by sl_calc and tp_calc to signal
setup rejection. Per spec §6 rejection catalogue.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add `EqLevel` dataclass to engine/smc.py

`tp_calc.py` consumes `EqLevel` records. The existing `equal_levels()` returns dicts; v2 needs a typed dataclass alongside.

**Files:**
- Modify: `engine/smc.py` — add `EqLevel` dataclass near other dataclasses (top of file)

- [ ] **Step 2.1: Write the failing test (in a new test file)**

Create `backend/tests/smc_v2/test_liquidity_pools.py`:

```python
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
```

- [ ] **Step 2.2: Run to verify it fails**

```bash
python -m pytest backend/tests/smc_v2/test_liquidity_pools.py::TestEqLevelDataclass -v
# Expected: FAIL with "cannot import name 'EqLevel' from 'engine.smc'"
```

- [ ] **Step 2.3: Add `EqLevel` dataclass to engine/smc.py**

Find the existing dataclass block in `engine/smc.py` (lines 19-87). After the `OTE` dataclass at line 81-87, add:

```python
@dataclass
class EqLevel:
    """Clustered equal high / low (liquidity pool).

    Used by smc_v2.tp_calc.calc_tp_targets as the primary TP1 source.
    Created by SMCEngine.liquidity_pools() (v2) — distinct from the
    dict-based output of equal_levels() which is kept for v1 callers.
    """
    price: float
    kind: str          # "EQH" (equal highs) | "EQL" (equal lows)
    touches: int = 2   # number of swings clustered (minimum 2)
```

- [ ] **Step 2.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_liquidity_pools.py::TestEqLevelDataclass -v
# Expected: 2 passed
```

- [ ] **Step 2.5: Commit**

```bash
git add engine/smc.py backend/tests/smc_v2/test_liquidity_pools.py
git commit -m "feat(smc): add EqLevel dataclass for v2 liquidity pool records

Typed counterpart to the dict-based output of equal_levels().
Consumed by smc_v2.tp_calc as the primary TP1 source per spec §4.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Implement `SMCEngine.liquidity_pools()` method

**Files:**
- Modify: `engine/smc.py` — add `liquidity_pools()` method on `SMCEngine` class

- [ ] **Step 3.1: Write the failing test**

Append to `backend/tests/smc_v2/test_liquidity_pools.py`:

```python
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
```

- [ ] **Step 3.2: Run to verify it fails**

```bash
python -m pytest backend/tests/smc_v2/test_liquidity_pools.py::TestLiquidityPools -v
# Expected: 6 FAIL with "AttributeError: ... has no attribute 'liquidity_pools'"
```

- [ ] **Step 3.3: Implement `liquidity_pools()` on `SMCEngine`**

In `engine/smc.py`, find the existing `equal_levels()` method (around line 285). Add a new method immediately after it (keeps related cluster logic together):

```python
    def liquidity_pools(self, swings_high: list, swings_low: list) -> List["EqLevel"]:
        """Cluster equal highs / lows into typed EqLevel records (v2).

        Distinct from equal_levels() — that one returns dicts for legacy v1
        callers and only considers adjacent pairs. liquidity_pools collapses
        ALL pairwise-equal swings into single clusters with a touch count,
        which is what tp_calc needs to rank liquidity targets by strength.

        Args:
            swings_high: list of Swing with is_high=True
            swings_low:  list of Swing with is_high=False

        Returns:
            List of EqLevel sorted by price ascending. Each cluster contains
            >= 2 touches by definition (singletons are not liquidity).
        """
        def _cluster(swings: list, kind: str) -> List["EqLevel"]:
            if len(swings) < 2:
                return []
            # Group swings into clusters where every member is within eq_thr
            # of the cluster's running average. Greedy linear pass — works
            # because swings are already in time order; price-proximity is
            # the only grouping signal we need.
            sorted_swings = sorted(swings, key=lambda s: s.price)
            clusters: List[List[Swing]] = []
            for sw in sorted_swings:
                placed = False
                for cl in clusters:
                    avg = sum(x.price for x in cl) / len(cl)
                    if abs(sw.price - avg) / max(avg, 1e-10) <= self.eq_thr:
                        cl.append(sw)
                        placed = True
                        break
                if not placed:
                    clusters.append([sw])
            return [
                EqLevel(
                    price=sum(x.price for x in cl) / len(cl),
                    kind=kind,
                    touches=len(cl),
                )
                for cl in clusters
                if len(cl) >= 2
            ]

        out = _cluster(swings_high, "EQH") + _cluster(swings_low, "EQL")
        return sorted(out, key=lambda e: e.price)
```

- [ ] **Step 3.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_liquidity_pools.py -v
# Expected: 8 passed
```

- [ ] **Step 3.5: Run full backend suite for regression check**

```bash
python -m pytest backend/tests/ -q 2>&1 | tail -3
# Expected: 474 passed (466 baseline + 8 new)
```

- [ ] **Step 3.6: Commit**

```bash
git add engine/smc.py backend/tests/smc_v2/test_liquidity_pools.py
git commit -m "feat(smc): add liquidity_pools() clustering method (v2)

Greedy single-pass clusterer over Swing lists. Returns typed
EqLevel records with touch counts. Distinct from the legacy
equal_levels() dict output which is left untouched for v1 callers.

Signature note: spec §4.1 sketches the method as liquidity_pools(df,
eq_threshold). The actual implementation takes (swings_high, swings_low)
because callers (PR #S3) will already have computed swings from
SMCEngine.swings() — passing pre-computed swings avoids redundant
DataFrame iteration. eq_threshold uses self.eq_thr (engine attribute).
This deliberate drift is documented here so reviewers won't flag it.

Spec §4.1 — primary TP1 source for tp_calc.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: zones.py — pullback target builder

### Task 4: Implement `ZoneSpec` dataclass + `build_pullback_zones()` + `is_price_in_zone()`

**Files:**
- Create: `engine/smc_v2/zones.py`
- Create: `backend/tests/smc_v2/test_zones.py`

- [ ] **Step 4.1: Write the failing test**

Create `backend/tests/smc_v2/test_zones.py`:

```python
"""Tests for smc_v2.zones — pullback target builder."""
from typing import List
import pytest

from engine.smc import FVG


class TestZoneSpec:
    def test_zonespec_dataclass_has_low_high_source(self):
        from engine.smc_v2.zones import ZoneSpec
        z = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        assert z.low == 100.0
        assert z.high == 110.0
        assert z.source == "HTF_FVG"

    def test_zonespec_ote_source(self):
        from engine.smc_v2.zones import ZoneSpec
        z = ZoneSpec(low=95.0, high=98.0, source="OTE")
        assert z.source == "OTE"


class TestBuildPullbackZonesShort:
    """For a SHORT trade after a downward CHoCH, a pullback zone is a price
    range ABOVE the trigger price where price might retrace before the next
    leg down.

    Priority 1: nearest unmitigated BULL HTF FVG above trigger_price
    Priority 2 (fallback): OTE band (passed in directly)
    """

    def test_priority1_picks_nearest_bull_fvg_above(self):
        from engine.smc_v2.zones import build_pullback_zones
        # Two BULL FVGs above trigger; nearest one wins
        fvgs = [
            FVG(top=120.0, bot=115.0, idx=1, ts="t1", direction="BULL"),
            FVG(top=110.0, bot=107.0, idx=2, ts="t2", direction="BULL"),  # nearest
        ]
        ote_band = (95.0, 98.0)  # below; ignored when FVG available
        zone = build_pullback_zones(
            htf_fvgs=fvgs,
            ote_band=ote_band,
            direction="SHORT",
            trigger_price=100.0,
        )
        # Nearest by `bot` distance from trigger_price
        assert zone.low == 107.0
        assert zone.high == 110.0
        assert zone.source == "HTF_FVG"

    def test_priority2_falls_back_to_ote_when_no_fvg(self):
        from engine.smc_v2.zones import build_pullback_zones
        zone = build_pullback_zones(
            htf_fvgs=[],
            ote_band=(105.0, 108.0),
            direction="SHORT",
            trigger_price=100.0,
        )
        assert zone.low == 105.0
        assert zone.high == 108.0
        assert zone.source == "OTE"

    def test_bear_fvgs_ignored_for_short_setup(self):
        """For SHORT we look for BULL FVGs above (counter-direction gap).
        BEAR FVGs (impulse-direction) are not pullback targets."""
        from engine.smc_v2.zones import build_pullback_zones
        fvgs = [
            FVG(top=115.0, bot=110.0, idx=1, ts="t1", direction="BEAR"),
        ]
        zone = build_pullback_zones(
            htf_fvgs=fvgs,
            ote_band=(105.0, 108.0),
            direction="SHORT",
            trigger_price=100.0,
        )
        assert zone.source == "OTE"  # falls back

    def test_fvg_below_trigger_ignored_for_short(self):
        from engine.smc_v2.zones import build_pullback_zones
        # BULL FVG but below trigger — wrong side for SHORT pullback
        fvgs = [
            FVG(top=95.0, bot=92.0, idx=1, ts="t1", direction="BULL"),
        ]
        zone = build_pullback_zones(
            htf_fvgs=fvgs,
            ote_band=(105.0, 108.0),
            direction="SHORT",
            trigger_price=100.0,
        )
        assert zone.source == "OTE"


class TestBuildPullbackZonesLong:
    """Mirror of SHORT: pullback target for LONG is BELOW trigger.
    Priority 1: nearest unmitigated BEAR HTF FVG below trigger_price.
    """

    def test_priority1_picks_nearest_bear_fvg_below(self):
        from engine.smc_v2.zones import build_pullback_zones
        fvgs = [
            FVG(top=85.0, bot=80.0, idx=1, ts="t1", direction="BEAR"),
            FVG(top=92.0, bot=89.0, idx=2, ts="t2", direction="BEAR"),  # nearest
        ]
        zone = build_pullback_zones(
            htf_fvgs=fvgs,
            ote_band=(102.0, 105.0),  # above; wrong side; ignored
            direction="LONG",
            trigger_price=100.0,
        )
        assert zone.low == 89.0
        assert zone.high == 92.0
        assert zone.source == "HTF_FVG"

    def test_priority2_falls_back_to_ote_for_long(self):
        from engine.smc_v2.zones import build_pullback_zones
        zone = build_pullback_zones(
            htf_fvgs=[],
            ote_band=(92.0, 95.0),
            direction="LONG",
            trigger_price=100.0,
        )
        assert zone.source == "OTE"


class TestIsPriceInZone:
    def test_price_inside_zone(self):
        from engine.smc_v2.zones import ZoneSpec, is_price_in_zone
        z = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        assert is_price_in_zone(105.0, z) is True

    def test_price_at_low_edge_is_inside(self):
        from engine.smc_v2.zones import ZoneSpec, is_price_in_zone
        z = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        assert is_price_in_zone(100.0, z) is True

    def test_price_at_high_edge_is_inside(self):
        from engine.smc_v2.zones import ZoneSpec, is_price_in_zone
        z = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        assert is_price_in_zone(110.0, z) is True

    def test_price_below_low_is_outside(self):
        from engine.smc_v2.zones import ZoneSpec, is_price_in_zone
        z = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        assert is_price_in_zone(99.99, z) is False

    def test_price_above_high_is_outside(self):
        from engine.smc_v2.zones import ZoneSpec, is_price_in_zone
        z = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        assert is_price_in_zone(110.01, z) is False
```

- [ ] **Step 4.2: Run to verify it fails**

```bash
python -m pytest backend/tests/smc_v2/test_zones.py -v 2>&1 | tail -15
# Expected: many FAIL with ModuleNotFoundError or AttributeError
```

- [ ] **Step 4.3: Implement zones.py**

Create `engine/smc_v2/zones.py`:

```python
"""Pullback zone builder for SMC v2.

Selects the price band where a pullback entry is expected after a CHoCH
trigger. Priority order per spec §4.1:

  1. Nearest unmitigated counter-direction HTF FVG on the pullback side
     (BULL FVGs above price for SHORT; BEAR FVGs below price for LONG).
  2. Fallback: OTE band (caller passes the band).

All functions are pure — no I/O, no logging.
"""
from dataclasses import dataclass
from typing import List, Literal, Tuple

from engine.smc import FVG


@dataclass
class ZoneSpec:
    """A pullback target region."""
    low: float
    high: float
    source: Literal["HTF_FVG", "OTE"]


def build_pullback_zones(
    htf_fvgs: List[FVG],
    ote_band: Tuple[float, float],
    direction: str,
    trigger_price: float,
) -> ZoneSpec:
    """Pick the pullback target zone for a fresh setup.

    Args:
        htf_fvgs: list of FVGs from the HTF (4h/1h) — typically unmitigated only,
            but this function does not filter; pass pre-filtered list.
        ote_band: (low, high) tuple of the OTE 0.618-0.786 band; used as fallback.
        direction: "LONG" or "SHORT" — the direction of the trade being prepared.
        trigger_price: the CHoCH break price; reference for "which side is pullback".

    Returns:
        ZoneSpec with source="HTF_FVG" if a counter-direction FVG exists on the
        pullback side, else source="OTE" using the supplied band.
    """
    if direction == "SHORT":
        # SHORT pullback = price retraces UP into a BULL gap above trigger
        candidates = [
            f for f in htf_fvgs
            if f.direction == "BULL" and f.bot > trigger_price
        ]
        if candidates:
            # Nearest = smallest distance from trigger to FVG bot
            nearest = min(candidates, key=lambda f: f.bot - trigger_price)
            return ZoneSpec(low=nearest.bot, high=nearest.top, source="HTF_FVG")
    else:  # LONG
        # LONG pullback = price retraces DOWN into a BEAR gap below trigger
        candidates = [
            f for f in htf_fvgs
            if f.direction == "BEAR" and f.top < trigger_price
        ]
        if candidates:
            # Nearest = smallest distance from FVG top to trigger
            nearest = max(candidates, key=lambda f: f.top)
            return ZoneSpec(low=nearest.bot, high=nearest.top, source="HTF_FVG")
    # Fallback
    return ZoneSpec(low=ote_band[0], high=ote_band[1], source="OTE")


def is_price_in_zone(price: float, zone: ZoneSpec) -> bool:
    """Inclusive membership check."""
    return zone.low <= price <= zone.high
```

- [ ] **Step 4.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_zones.py -v 2>&1 | tail -20
# Expected: 11 passed
```

- [ ] **Step 4.5: Commit**

```bash
git add engine/smc_v2/zones.py backend/tests/smc_v2/test_zones.py
git commit -m "feat(smc_v2): zones.py — pullback target builder

ZoneSpec dataclass + build_pullback_zones (HTF_FVG priority,
OTE fallback) + is_price_in_zone membership check. Pure
functions, no I/O. Spec §4.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3: sl_calc.py — structural SL with ATR buffer + clamp

### Task 5: Implement `calc_sl()`

**Files:**
- Create: `engine/smc_v2/sl_calc.py`
- Create: `backend/tests/smc_v2/test_sl_calc.py`

- [ ] **Step 5.1: Write the failing test**

Create `backend/tests/smc_v2/test_sl_calc.py`:

```python
"""Tests for smc_v2.sl_calc — structural SL computation.

Behavior (spec §5.1):
1. Structural SL = (zone outer edge or HTF swing anchor, whichever is further)
                   ± sl_atr_buffer * ATR(15m)
2. Then clamp:
   - If stop_dist < min_sl_atr * ATR: widen to min_sl_atr (ATR floor)
   - If stop_dist > max_sl_atr * ATR: RAISE SLTooFarError (don't clamp — reject)
"""
from dataclasses import dataclass
import pytest

from engine.smc_v2.zones import ZoneSpec
from engine.smc_v2.exceptions import SLTooFarError


@dataclass
class FakeSafetyConfig:
    """Minimal config shape consumed by calc_sl."""
    sl_atr_buffer: float = 0.5
    min_sl_atr: float = 0.5
    max_sl_atr: float = 5.0


class TestCalcSLShort:
    """SHORT SL = above entry; structural side is zone.high or htf_swing_anchor."""

    def test_structural_uses_max_of_zone_and_swing_plus_buffer(self):
        from engine.smc_v2.sl_calc import calc_sl
        # zone.high = 110, swing anchor = 115 (further), buffer = 0.5 * ATR(4) = 2
        sl = calc_sl(
            direction="SHORT",
            entry_price=100.0,
            zone=ZoneSpec(low=105.0, high=110.0, source="HTF_FVG"),
            htf_swing_anchor=115.0,
            atr_15m=4.0,
            config=FakeSafetyConfig(),
        )
        # max(110, 115) + 0.5*4 = 117
        assert sl == pytest.approx(117.0, rel=1e-6)

    def test_zone_wins_when_higher_than_swing(self):
        from engine.smc_v2.sl_calc import calc_sl
        sl = calc_sl(
            direction="SHORT",
            entry_price=100.0,
            zone=ZoneSpec(low=115.0, high=120.0, source="HTF_FVG"),
            htf_swing_anchor=112.0,
            atr_15m=2.0,
            config=FakeSafetyConfig(),
        )
        # max(120, 112) + 0.5*2 = 121
        assert sl == pytest.approx(121.0, rel=1e-6)

    def test_structural_used_when_within_atr_bounds(self):
        """When structural stop is within [min_dist, max_dist], use it as-is."""
        from engine.smc_v2.sl_calc import calc_sl
        # entry=100, zone.high=100.5, swing=100.3, ATR=10, buffer=0.5*10=5
        # structural = max(100.5, 100.3) + 5 = 105.5 → stop_dist = 5.5
        # min_dist = 0.5 * 10 = 5; max_dist = 5*10 = 50
        # 5 <= 5.5 <= 50 → return structural unchanged
        sl = calc_sl(
            direction="SHORT",
            entry_price=100.0,
            zone=ZoneSpec(low=100.0, high=100.5, source="HTF_FVG"),
            htf_swing_anchor=100.3,
            atr_15m=10.0,
            config=FakeSafetyConfig(),
        )
        assert sl == pytest.approx(105.5, rel=1e-6)

    def test_atr_floor_widens_too_tight_stop(self):
        """When structural stop_dist < min_sl_atr * ATR, widen to ATR floor."""
        from engine.smc_v2.sl_calc import calc_sl
        # Force structural too tight: tiny zone offset + zero buffer.
        # zone.high=100.0001, swing=100.0, ATR=1, buffer=0
        # structural = 100.0001 + 0 = 100.0001 → stop_dist = 0.0001
        # min_dist = 0.5 * 1 = 0.5 → 0.0001 < 0.5 → floor to min_dist
        # SL = entry + min_dist = 100 + 0.5 = 100.5
        cfg_no_buf = FakeSafetyConfig(sl_atr_buffer=0.0, min_sl_atr=0.5, max_sl_atr=5.0)
        sl = calc_sl(
            direction="SHORT",
            entry_price=100.0,
            zone=ZoneSpec(low=99.9, high=100.0001, source="HTF_FVG"),
            htf_swing_anchor=100.0,
            atr_15m=1.0,
            config=cfg_no_buf,
        )
        assert sl == pytest.approx(100.5, rel=1e-6)

    def test_max_clamp_raises_sl_too_far_error(self):
        from engine.smc_v2.sl_calc import calc_sl
        # entry=100, zone.high=200, swing=200, ATR=10
        # structural = 200 + 5 = 205 → stop_dist = 105
        # max_dist = 5 * 10 = 50 → 105 > 50 → REJECT
        with pytest.raises(SLTooFarError) as exc:
            calc_sl(
                direction="SHORT",
                entry_price=100.0,
                zone=ZoneSpec(low=150.0, high=200.0, source="HTF_FVG"),
                htf_swing_anchor=200.0,
                atr_15m=10.0,
                config=FakeSafetyConfig(),
            )
        assert exc.value.stop_dist == pytest.approx(105.0, rel=1e-6)
        assert exc.value.max_dist == pytest.approx(50.0, rel=1e-6)


class TestCalcSLLong:
    """LONG SL = below entry; structural side is zone.low or htf_swing_anchor (min)."""

    def test_structural_uses_min_of_zone_and_swing_minus_buffer(self):
        from engine.smc_v2.sl_calc import calc_sl
        # zone.low = 90, swing = 85 (lower = further from LONG entry)
        sl = calc_sl(
            direction="LONG",
            entry_price=100.0,
            zone=ZoneSpec(low=90.0, high=95.0, source="HTF_FVG"),
            htf_swing_anchor=85.0,
            atr_15m=4.0,
            config=FakeSafetyConfig(),
        )
        # min(90, 85) - 0.5*4 = 83
        assert sl == pytest.approx(83.0, rel=1e-6)

    def test_long_max_clamp_raises(self):
        from engine.smc_v2.sl_calc import calc_sl
        with pytest.raises(SLTooFarError):
            calc_sl(
                direction="LONG",
                entry_price=100.0,
                zone=ZoneSpec(low=10.0, high=15.0, source="HTF_FVG"),
                htf_swing_anchor=5.0,
                atr_15m=10.0,
                config=FakeSafetyConfig(),
            )
```

- [ ] **Step 5.2: Run to verify it fails**

```bash
python -m pytest backend/tests/smc_v2/test_sl_calc.py -v 2>&1 | tail -10
# Expected: all FAIL with ModuleNotFoundError
```

- [ ] **Step 5.3: Implement sl_calc.py**

Create `engine/smc_v2/sl_calc.py`:

```python
"""Structural SL computation with ATR buffer + clamp.

Spec §5.1:
  structural_sl_SHORT = max(zone.high, htf_swing_anchor) + sl_atr_buffer * ATR
  structural_sl_LONG  = min(zone.low,  htf_swing_anchor) - sl_atr_buffer * ATR
  stop_dist = |entry - structural_sl|
  if stop_dist < min_sl_atr * ATR: widen to min_dist
  if stop_dist > max_sl_atr * ATR: raise SLTooFarError (reject setup)
"""
from typing import Protocol

from engine.smc_v2.exceptions import SLTooFarError
from engine.smc_v2.zones import ZoneSpec


class SafetyConfigLike(Protocol):
    """Structural shape consumed by calc_sl. Matches engine.safety config attrs."""
    sl_atr_buffer: float
    min_sl_atr: float
    max_sl_atr: float


def calc_sl(
    direction: str,
    entry_price: float,
    zone: ZoneSpec,
    htf_swing_anchor: float,
    atr_15m: float,
    config: SafetyConfigLike,
) -> float:
    """Compute structural SL price with ATR buffer and clamp bounds.

    Args:
        direction: "LONG" or "SHORT".
        entry_price: confirmed entry price (from confirmation.py).
        zone: the pullback zone the entry happened inside.
        htf_swing_anchor: HTF swing price on the "wrong side" of the trade
            (i.e. above for SHORT, below for LONG). Selected by
            select_htf_swing_anchor in PR #S3.
        atr_15m: current 15m ATR(14) — drives both buffer and clamp.
        config: must have sl_atr_buffer, min_sl_atr, max_sl_atr (floats).

    Returns:
        SL price (float).

    Raises:
        SLTooFarError: when structural stop distance exceeds max_sl_atr * ATR.
    """
    buffer = config.sl_atr_buffer * atr_15m
    if direction == "LONG":
        structural_sl = min(zone.low, htf_swing_anchor) - buffer
    else:  # SHORT
        structural_sl = max(zone.high, htf_swing_anchor) + buffer

    stop_dist = abs(entry_price - structural_sl)
    min_dist = config.min_sl_atr * atr_15m
    max_dist = config.max_sl_atr * atr_15m

    if stop_dist > max_dist:
        raise SLTooFarError(stop_dist=stop_dist, max_dist=max_dist)
    if stop_dist < min_dist:
        # Widen to ATR floor — same direction as structural
        return (entry_price - min_dist) if direction == "LONG" else (entry_price + min_dist)
    return structural_sl
```

- [ ] **Step 5.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_sl_calc.py -v 2>&1 | tail -10
# Expected: 7 passed
```

- [ ] **Step 5.5: Commit**

```bash
git add engine/smc_v2/sl_calc.py backend/tests/smc_v2/test_sl_calc.py
git commit -m "feat(smc_v2): sl_calc.py — structural SL + ATR buffer + clamp

Pure function: structural anchor + buffer, with ATR floor for tight
stops and SLTooFarError for too-far stops (per spec §5.1).
Activates currently-dead config keys sl_atr_buffer, min_sl_atr,
max_sl_atr (signals.py v1 never read them).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 4: tp_calc.py — liquidity-first TP1 + FVG-fill TP2

### Task 6: Implement `calc_tp_targets()`

**Files:**
- Create: `engine/smc_v2/tp_calc.py`
- Create: `backend/tests/smc_v2/test_tp_calc.py`

- [ ] **Step 6.1: Write the failing test**

Create `backend/tests/smc_v2/test_tp_calc.py`:

```python
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
        # TP1 forced low so fib_ext > TP1
        # risk=10, min_rr=1.8, eq at 118 (dist 18 ✓)
        # fib_ext = 100 + 1.618*10 = 116.18 < 118; still not beyond
        # Force higher entry-risk gap: entry=100, sl=80 → risk=20, fib_ext=132.36
        # min_rr*risk = 36; need EQ candidate >= 136
        eq_levels = [EqLevel(price=136, kind="EQH", touches=2)]
        tp1, tp2, tags = calc_tp_targets(
            direction="LONG", entry_price=100, sl_price=80,
            htf_swings=htf_swings_dict(),
            htf_fvgs=[], eq_levels=eq_levels, config=FakeRiskConfig(),
        )
        # tp1 = 136; fib_ext = 100 + 1.618*20 = 132.36 < 136 → tp2=None still
        assert tp1 == 136
        assert tp2 is None
        # To get FIB_EXT as TP2 source, TP1 must be very close to entry
        # Configure with very low min_rr
        cfg_low = FakeRiskConfig(min_rr=0.5)
        eq2 = [EqLevel(price=110, kind="EQH", touches=2)]  # within min_rr*risk
        tp1b, tp2b, tagsb = calc_tp_targets(
            direction="LONG", entry_price=100, sl_price=90,
            htf_swings=htf_swings_dict(),
            htf_fvgs=[], eq_levels=eq2, config=cfg_low,
        )
        # min_dist = 0.5 * 10 = 5; eq at 110 (dist 10 ✓) → tp1=110
        # fib_ext = 100 + 1.618 * 10 = 116.18 > 110 → tp2=116.18 FIB_EXT
        assert tp1b == 110
        assert tp2b == pytest.approx(116.18, rel=1e-4)
        assert tagsb["tp2_source"] == "FIB_EXT"


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
```

- [ ] **Step 6.2: Run to verify it fails**

```bash
python -m pytest backend/tests/smc_v2/test_tp_calc.py -v 2>&1 | tail -10
# Expected: all FAIL with ModuleNotFoundError
```

- [ ] **Step 6.3: Implement tp_calc.py**

Create `engine/smc_v2/tp_calc.py`:

```python
"""TP1 / TP2 target computation for SMC v2.

Spec §5.2:
  TP1 candidates (priority chain, with explicit source precedence on ties):
    1. Liquidity: EQH/EQL clusters + HTF swing extrema on the correct side
    2. FVG_NEAR: counter-direction HTF FVG near-edge on the correct side
    Pick the nearest candidate whose distance from entry >= min_rr * risk.
    If candidates exist but none qualify → InsufficientTPDistanceError.
    If no candidates at all → RR_PROJECTION (entry ± min_rr * risk).

  TP2:
    1. HTF FVG far-edge beyond TP1
    2. Fallback: fib_ext * risk projection, but only if it lies beyond TP1
    Else → None (single-target mode; lifecycle in PR #S5 handles TP1 = full close).

  Precedence on price ties (LIQUIDITY > FVG_NEAR) is explicit via a priority
  dict so a future refactor reordering list-comp blocks cannot silently flip it.
"""
from typing import Protocol, Tuple, Optional

from engine.smc import FVG, EqLevel
from engine.smc_v2.exceptions import InsufficientTPDistanceError


class RiskConfigLike(Protocol):
    min_rr: float
    fib_ext: float


# Explicit source precedence — guards against float-equality misattribution.
# Lower number = higher priority on a tie.
_SOURCE_PRIORITY = {"LIQUIDITY": 0, "FVG_NEAR": 1}


def calc_tp_targets(
    direction: str,
    entry_price: float,
    sl_price: float,
    htf_swings: dict,            # {"swing_highs": [...], "swing_lows": [...]}
    htf_fvgs: list,              # List[FVG]
    eq_levels: list,             # List[EqLevel]
    config: RiskConfigLike,
) -> Tuple[float, Optional[float], dict]:
    """Compute TP1 + TP2 + source tags."""
    risk = abs(entry_price - sl_price)
    min_rr = config.min_rr
    min_dist = min_rr * risk

    if direction == "LONG":
        # Liquidity ABOVE entry
        labeled = [(e.price, "LIQUIDITY") for e in eq_levels
                   if e.kind == "EQH" and e.price > entry_price]
        labeled += [(s.price, "LIQUIDITY") for s in htf_swings["swing_highs"]
                    if s.price > entry_price]
        labeled += [(f.bot, "FVG_NEAR") for f in htf_fvgs
                    if f.direction == "BEAR" and f.bot > entry_price]
        # Dedup by price with explicit precedence
        seen = {}
        for p, src in labeled:
            if p not in seen or _SOURCE_PRIORITY[src] < _SOURCE_PRIORITY[seen[p]]:
                seen[p] = src
        candidates = sorted(seen.items(), key=lambda x: x[0])  # ascending

        tp1_pair = next(((p, s) for p, s in candidates
                         if (p - entry_price) >= min_dist), None)
        if tp1_pair is None and candidates:
            raise InsufficientTPDistanceError(
                nearest=candidates[0][0], required=min_dist,
            )
        if tp1_pair is None:
            tp1, tp1_source = entry_price + min_dist, "RR_PROJECTION"
        else:
            tp1, tp1_source = tp1_pair

        # TP2: HTF FVG far edge beyond TP1, fallback fib_ext (strict > TP1)
        fvg_far = [f.top for f in htf_fvgs if f.direction == "BEAR" and f.top > tp1]
        if fvg_far:
            tp2, tp2_source = min(fvg_far), "FVG_FAR"
        else:
            fib_tp2 = entry_price + config.fib_ext * risk
            if fib_tp2 > tp1:
                tp2, tp2_source = fib_tp2, "FIB_EXT"
            else:
                tp2, tp2_source = None, "NONE"

    else:  # SHORT — mirror
        labeled = [(e.price, "LIQUIDITY") for e in eq_levels
                   if e.kind == "EQL" and e.price < entry_price]
        labeled += [(s.price, "LIQUIDITY") for s in htf_swings["swing_lows"]
                    if s.price < entry_price]
        labeled += [(f.top, "FVG_NEAR") for f in htf_fvgs
                    if f.direction == "BULL" and f.top < entry_price]
        seen = {}
        for p, src in labeled:
            if p not in seen or _SOURCE_PRIORITY[src] < _SOURCE_PRIORITY[seen[p]]:
                seen[p] = src
        candidates = sorted(seen.items(), key=lambda x: x[0], reverse=True)  # descending

        tp1_pair = next(((p, s) for p, s in candidates
                         if (entry_price - p) >= min_dist), None)
        if tp1_pair is None and candidates:
            raise InsufficientTPDistanceError(
                nearest=candidates[0][0], required=min_dist,
            )
        if tp1_pair is None:
            tp1, tp1_source = entry_price - min_dist, "RR_PROJECTION"
        else:
            tp1, tp1_source = tp1_pair

        fvg_far = [f.bot for f in htf_fvgs if f.direction == "BULL" and f.bot < tp1]
        if fvg_far:
            tp2, tp2_source = max(fvg_far), "FVG_FAR"
        else:
            fib_tp2 = entry_price - config.fib_ext * risk
            if fib_tp2 < tp1:
                tp2, tp2_source = fib_tp2, "FIB_EXT"
            else:
                tp2, tp2_source = None, "NONE"

    return tp1, tp2, {"tp1_source": tp1_source, "tp2_source": tp2_source}
```

- [ ] **Step 6.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_tp_calc.py -v 2>&1 | tail -15
# Expected: 10 passed
```

- [ ] **Step 6.5: Commit**

```bash
git add engine/smc_v2/tp_calc.py backend/tests/smc_v2/test_tp_calc.py
git commit -m "feat(smc_v2): tp_calc.py — liquidity-first TP1 + FVG-fill TP2

Per spec §5.2: LIQUIDITY > FVG_NEAR priority with explicit precedence
dict (no insertion-order dependency). InsufficientTPDistanceError when
candidates exist but none satisfy min_rr * risk. TP2 strict-beyond-TP1
invariant; returns None to signal single-target mode (lifecycle in PR
#S5 handles the full-close branch).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 5: Final regression sweep

### Task 7: Whole-suite regression + py_compile smoke

- [ ] **Step 7.1: Full backend suite**

```bash
python -m pytest backend/tests/ -q 2>&1 | tail -3
# Expected: 466 baseline + 8 (Task 3) + 11 (Task 4) + 7 (Task 5) + 10 (Task 6) = 502 passed
```

- [ ] **Step 7.2: py_compile all new modules**

```bash
python -m py_compile engine/smc_v2/__init__.py engine/smc_v2/exceptions.py engine/smc_v2/zones.py engine/smc_v2/sl_calc.py engine/smc_v2/tp_calc.py && echo "compile OK"
# Expected: compile OK
```

- [ ] **Step 7.3: Lint smoke (best-effort)**

```bash
python -m py_compile engine/smc.py
# Expected: clean
```

- [ ] **Step 7.4: Diff inventory**

```bash
git log feat/smc-v2-pure-modules ^master --oneline
git diff master..HEAD --stat
# Expected: 6 commits, only engine/smc_v2/* + engine/smc.py + backend/tests/smc_v2/*
```

No commit at step 7 unless step 7.1-7.3 produced changes (they shouldn't).

---

## Out of Scope (explicitly NOT in PR #S1)

- `engine/smc_v2/setup_state.py` (SetupCandidate, persistence) — PR #S2a
- Orchestrator wiring of pending candidates — PR #S2b
- `engine/smc_v2/confirmation.py` (LTF entry confirmation) — PR #S3
- `engine/smc_v2/__init__.py` orchestration function (`generate_signals_v2`) — PR #S3
- Feature flag (`engine.smc_version`) dispatch — PR #S3
- `select_htf_swing_anchor()` algorithm — PR #S3 (uses HTF bars, not in PR #S1 scope)
- Backtest v2 path + v1 baseline — PR #S4
- `lifecycle.Position` + db.py telemetry fields — PR #S5
- Config block — PR #S6
- Production rollout — PR #S7

---

## Acceptance Criteria

PR #S1 is complete and ready for review when:

1. All steps in Tasks 1-7 are checked off.
2. `python -m pytest backend/tests/smc_v2/ -v` shows **36 tests passing** (2 EqLevel + 6 liquidity_pools + 11 zones + 7 sl_calc + 10 tp_calc).
3. `python -m pytest backend/tests/ -q` shows the full suite still green (~501 passed, depending on baseline).
4. `git log feat/smc-v2-pure-modules ^master --oneline` shows 6 atomic commits.
5. `git diff master feat/smc-v2-pure-modules --stat` shows **only** the new files + `engine/smc.py` additions (EqLevel + liquidity_pools method) + plan doc — no other changes to existing modules.
6. `efloud-code-reviewer` agent reviewed the diff. No risk-ops agent needed (no `engine/safety/`, `exchange/`, or risk config touched).

---

## Post-Plan Workflow

1. After implementation: invoke `superpowers:verification-before-completion` (Iron Law).
2. Invoke `superpowers:requesting-code-review` → `efloud-code-reviewer` agent.
3. Apply review feedback if any.
4. Invoke `superpowers:finishing-a-development-branch` → push + PR (user-confirm shared-state action).
5. Update `memory/smc_v2_rework_initiative.md` PR Status: mark PR #S1 done with PR # link.

---

## References

- Spec: `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §4.1, §5
- Existing SMC indicators: `engine/smc.py` (Swing, FVG, OrderBlock, OTE, equal_levels at line 285)
- Initiative tracker: `memory/smc_v2_rework_initiative.md`
- CLAUDE.md §4 (atomic PR discipline)
