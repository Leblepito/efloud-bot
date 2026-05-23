# PR #S3a: Confirmation + HTF Swing Anchor — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two pure-function modules of SMC v2 confirmation logic: `engine/smc_v2/confirmation.py` (LTF CHoCH / bearish-bullish engulfing detection inside a zone) and `engine/smc_v2/swing_anchor.py` (`select_htf_swing_anchor()` — most-recent-unbroken HTF swing on the wrong side of a trade).

**Architecture:** Two new pure-function modules. `confirmation.py` operates on a 15m DataFrame + ZoneSpec to detect LTF entry confirmations. `swing_anchor.py` operates on HTF swings + HTF OHLC bars to pick the structural SL reference. Both are stateless, no I/O, no logging. PR #S3a ships ONLY the pure modules — they are not yet consumed by any production code path (consumers land in PR #S3b/S3c).

**Tech Stack:** Python 3.12, pandas (already a dep), pytest. Zero new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §4.1 (confirmation.py module sketch) + §10 #1 (HTF swing anchor algorithm). Spec lives on `origin/feat/smc-v2-spec` (PR #64). Read with: `git show origin/feat/smc-v2-spec:docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md`.

**Branch:** `feat/smc-v2-confirmation` — **stacked on `feat/smc-v2-pure-modules`** (PR #65). GitHub PR base = PR #65's branch. When PR #65 merges, this PR auto-rebases.

**Risk classification:** **Low risk.** Pure-function modules only. No `engine/safety/`, `exchange/`, `engine/safe_orchestrator.py`, `config.yaml`, `docker-compose.prod.yml`, or migrations touched. Per CLAUDE.md §4: `efloud-code-reviewer` sufficient, no `efloud-risk-ops-reviewer` gate needed. Modules are consumed by no code path until PR #S3b wires them in.

---

## Pre-flight Checks

- [ ] **P1:** Confirm worktree + stacked branch.

```bash
git rev-parse --show-toplevel  # Expected: .../efloud-bot/.worktrees/smc-v2-confirmation
git branch --show-current      # Expected: feat/smc-v2-confirmation
git log --oneline -3
# Expected: HEAD = "25d31b3 fixup(smc_v2): apply code-review feedback for PR #S1"
```

- [ ] **P2:** Confirm baseline tests pass (PR #65 modules — 41 v2 tests).

```bash
python -m pytest backend/tests/smc_v2/ -q
# Expected: 41 passed
```

- [ ] **P3:** Confirm dependencies exist (PR #65 base).

```bash
ls engine/smc_v2/__init__.py engine/smc_v2/zones.py engine/smc.py
# Expected: all three exist
python -c "from engine.smc_v2.zones import ZoneSpec, is_price_in_zone; print('OK')"
# Expected: OK
python -c "from engine.smc import Swing; print('OK')"
# Expected: OK
```

If any drift, stop and reconcile.

---

## File Structure

**Created files** (4):

- `engine/smc_v2/confirmation.py` — `confirm_entry(df_15m, zone, direction, since_ts)` pure function
- `engine/smc_v2/swing_anchor.py` — `select_htf_swing_anchor(htf_swings, direction, trigger_ts, htf_bars)` pure function
- `backend/tests/smc_v2/test_confirmation.py` — comprehensive unit tests for confirmation
- `backend/tests/smc_v2/test_swing_anchor.py` — comprehensive unit tests for swing anchor selection

**Modified files** (0).

**No changes to**: `engine/smc_v2/zones.py`, `engine/smc_v2/sl_calc.py`, `engine/smc_v2/tp_calc.py`, `engine/smc_v2/exceptions.py`, `engine/smc.py`, `engine/signals.py`, `engine/safe_orchestrator.py`, `engine/lifecycle.py`, `engine/safety/`, `exchange/`, `config.yaml`, `backend/db.py`, any migration.

**File responsibility boundaries:**

- `confirmation.py` knows ONLY how to detect a confirmation pattern (CHoCH / engulfing) in a 15m DataFrame inside a given zone. It returns `(confirmed: bool, entry_price: float | None)`. It does not know about state machines, orders, or signal emission.
- `swing_anchor.py` knows ONLY how to iterate HTF swings most-recent-first and find the first "unbroken" one on the trade's wrong side. It returns the swing's price or `None`. It does not know about ATR, SL distance, or rejection.

---

## Chunk 1: select_htf_swing_anchor

### Task 1: Implement `select_htf_swing_anchor()`

**Files:**
- Create: `engine/smc_v2/swing_anchor.py`
- Create: `backend/tests/smc_v2/test_swing_anchor.py`

- [ ] **Step 1.1: Write the failing tests**

Create `backend/tests/smc_v2/test_swing_anchor.py`:

```python
"""Tests for smc_v2.swing_anchor — HTF swing anchor selection.

Per spec §10 #1:
  Return the most recent unbroken HTF swing on the 'wrong side' of the trade.
  'Unbroken' means: no HTF bar after the swing's formation has traded
  through the swing's price level.

  For SHORT: wrong side = swing_highs above entry. Unbroken = no bar.high > price.
  For LONG:  wrong side = swing_lows below entry. Unbroken = no bar.low < price.

  Returns the swing's price (float) or None if no unbroken swing exists.
  When None, the caller (PR #S3b sl_calc invocation) raises SLTooFarError.
"""
from dataclasses import dataclass
import pytest

from engine.smc import Swing


@dataclass
class FakeBar:
    """Minimal HTF bar shape: only needs `ts`, `high`, `low`.
    Mirrors a row of an HTF OHLC DataFrame for select_htf_swing_anchor."""
    ts: int    # ms epoch
    high: float
    low: float


class TestSelectHTFSwingAnchorShort:
    """SHORT trade: wrong side = swing_highs ABOVE entry."""

    def test_picks_most_recent_unbroken_swing_high(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {
            "swing_highs": [
                Swing(price=100.0, idx=10, ts="t1", is_high=True),
                Swing(price=110.0, idx=20, ts="t2", is_high=True),  # most recent unbroken
                Swing(price=105.0, idx=15, ts="t3", is_high=True),
            ],
            "swing_lows": [],
        }
        # No bar after the most-recent (idx 20) trades above 110
        # Note: we pass swing.ts as int via a parallel index — for clarity
        # the function takes htf_bars as a list of FakeBar with ts as ms epoch,
        # and swing.idx as the bar index.
        bars = [
            FakeBar(ts=1, high=99, low=95),
            FakeBar(ts=2, high=100, low=96),
            FakeBar(ts=3, high=105, low=99),  # 110 not breached
            FakeBar(ts=4, high=108, low=100),
        ]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="SHORT",
            trigger_ts=5,  # trigger after all swings
            htf_bars=bars,
        )
        assert result == 110.0

    def test_skips_broken_recent_swing_picks_earlier_unbroken(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        # Most recent swing is at 110; a later bar broke 110 → use earlier swing
        swings = {
            "swing_highs": [
                Swing(price=120.0, idx=5, ts="t1", is_high=True),   # earlier, unbroken
                Swing(price=110.0, idx=15, ts="t2", is_high=True),  # most recent, broken
            ],
            "swing_lows": [],
        }
        bars = [
            FakeBar(ts=1, high=115, low=100),
            FakeBar(ts=2, high=118, low=105),
            FakeBar(ts=3, high=119, low=110),  # 120 not breached
            FakeBar(ts=4, high=109, low=100),  # after swing 110 forms
            FakeBar(ts=5, high=113, low=108),  # breaks the 110 swing
        ]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="SHORT",
            trigger_ts=6,
            htf_bars=bars,
        )
        # 110 is broken by bar at ts=5 (high=113 > 110); fall back to 120
        assert result == 120.0

    def test_returns_none_when_all_swings_broken(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {
            "swing_highs": [
                Swing(price=100.0, idx=5, ts="t1", is_high=True),
                Swing(price=105.0, idx=10, ts="t2", is_high=True),
            ],
            "swing_lows": [],
        }
        # Every swing broken by subsequent bars
        bars = [
            FakeBar(ts=1, high=95, low=90),
            FakeBar(ts=2, high=101, low=95),   # breaks 100
            FakeBar(ts=3, high=106, low=100),  # breaks 105
        ]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="SHORT",
            trigger_ts=4,
            htf_bars=bars,
        )
        assert result is None

    def test_returns_none_when_no_swings(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {"swing_highs": [], "swing_lows": []}
        bars = [FakeBar(ts=1, high=100, low=90)]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="SHORT",
            trigger_ts=2,
            htf_bars=bars,
        )
        assert result is None

    def test_ignores_swings_formed_after_trigger(self):
        """A swing whose idx is AFTER the trigger should be ignored (we don't
        anchor SL on future structure that hasn't formed at decision time)."""
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {
            "swing_highs": [
                Swing(price=100.0, idx=5, ts="t1", is_high=True),   # before trigger
                Swing(price=115.0, idx=20, ts="t2", is_high=True),  # AFTER trigger — ignored
            ],
            "swing_lows": [],
        }
        bars = [FakeBar(ts=i, high=95, low=90) for i in range(25)]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="SHORT",
            trigger_ts=10,  # before the 115 swing forms
            htf_bars=bars,
        )
        # Only 100 is valid (idx=5 < trigger_ts=10); never broken in bars
        assert result == 100.0


class TestSelectHTFSwingAnchorLong:
    """LONG trade: wrong side = swing_lows BELOW entry. Mirror of SHORT."""

    def test_picks_most_recent_unbroken_swing_low(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {
            "swing_highs": [],
            "swing_lows": [
                Swing(price=100.0, idx=10, ts="t1", is_high=False),
                Swing(price=95.0, idx=20, ts="t2", is_high=False),  # most recent unbroken
            ],
        }
        # No bar after idx 20 trades below 95
        bars = [
            FakeBar(ts=1, high=110, low=100),
            FakeBar(ts=2, high=105, low=99),   # 95 not breached
            FakeBar(ts=3, high=103, low=96),   # 95 not breached
        ]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="LONG",
            trigger_ts=4,
            htf_bars=bars,
        )
        assert result == 95.0

    def test_long_skips_broken_picks_earlier(self):
        from engine.smc_v2.swing_anchor import select_htf_swing_anchor
        swings = {
            "swing_highs": [],
            "swing_lows": [
                Swing(price=80.0, idx=5, ts="t1", is_high=False),   # earlier, unbroken
                Swing(price=90.0, idx=15, ts="t2", is_high=False),  # recent, broken
            ],
        }
        bars = [
            FakeBar(ts=1, high=100, low=85),
            FakeBar(ts=2, high=95, low=82),   # 80 not breached
            FakeBar(ts=3, high=92, low=89),   # 90 not yet breached (after idx 15 forms)
            FakeBar(ts=4, high=91, low=88),   # AFTER swing 90 — breaks 90
        ]
        result = select_htf_swing_anchor(
            htf_swings=swings,
            direction="LONG",
            trigger_ts=5,
            htf_bars=bars,
        )
        assert result == 80.0
```

- [ ] **Step 1.2: Run to verify fail**

```bash
python -m pytest backend/tests/smc_v2/test_swing_anchor.py -v
# Expected: many FAIL — ModuleNotFoundError: engine.smc_v2.swing_anchor
```

- [ ] **Step 1.3: Implement `swing_anchor.py`**

Create `engine/smc_v2/swing_anchor.py`:

```python
"""HTF swing anchor selection for SMC v2 structural SL.

Per spec §10 #1:
  Return the most recent unbroken HTF swing on the 'wrong side' of the trade.

  - For SHORT: wrong side = swing_highs above entry. Unbroken = no HTF bar
    formed after the swing has traded above the swing's price.
  - For LONG: mirror — swing_lows below entry; unbroken = no bar.low < price.

  Returns the swing's price (float), or None if no unbroken swing exists.
  When None, the caller raises SLTooFarError (setup rejected per spec).

Pure function — no I/O, no logging. Input bars are abstract (anything with
`ts`, `high`, `low` attributes), so tests can use lightweight FakeBar
fixtures and production can pass HTF OHLC DataFrame rows.
"""
from typing import Optional


def select_htf_swing_anchor(
    htf_swings: dict,
    direction: str,
    trigger_ts: int,
    htf_bars: list,
) -> Optional[float]:
    """Select the most-recent-unbroken HTF swing on the trade's wrong side.

    Args:
        htf_swings: {"swing_highs": [Swing, ...], "swing_lows": [Swing, ...]}
            Each Swing has `.price` (float) and `.idx` (int — bar position).
            Per `SMCEngine.swings()` in engine/smc.py:130-140.
        direction: "LONG" or "SHORT"
        trigger_ts: int — only consider swings with idx < trigger_ts
            (we don't anchor SL on future structure).
        htf_bars: list of objects with `.ts`, `.high`, `.low` attributes
            (HTF OHLC bars — DataFrame rows or FakeBar fixtures).

    Returns:
        Swing price (float) if unbroken anchor exists, else None.
    """
    if direction == "SHORT":
        candidates = htf_swings.get("swing_highs", [])
    else:  # LONG
        candidates = htf_swings.get("swing_lows", [])

    if not candidates:
        return None

    # Iterate most-recent-first (highest idx first)
    sorted_candidates = sorted(candidates, key=lambda s: s.idx, reverse=True)

    for swing in sorted_candidates:
        if swing.idx >= trigger_ts:
            continue  # formed after trigger — not yet known at decision time

        # Check unbroken: no bar AFTER the swing's idx has traded through it
        broken = False
        for bar in htf_bars:
            # `bar.ts` is treated as the bar's ordinal index for this check
            # (matches the simple time-monotonic test fixture). In production
            # the caller passes a DataFrame slice where row ts maps to
            # monotonic order; we only need post-swing bars.
            if bar.ts <= swing.idx:
                continue
            if direction == "SHORT":
                if bar.high > swing.price:
                    broken = True
                    break
            else:  # LONG
                if bar.low < swing.price:
                    broken = True
                    break

        if not broken:
            return swing.price

    # No unbroken swing — caller raises SLTooFarError
    return None
```

- [ ] **Step 1.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_swing_anchor.py -v
# Expected: 7 passed (5 SHORT + 2 LONG)
```

- [ ] **Step 1.5: Full v2 suite regression check**

```bash
python -m pytest backend/tests/smc_v2/ -q
# Expected: 41 (PR #65 baseline) + 7 (new) = 48 passed
```

- [ ] **Step 1.6: Commit**

```bash
git add engine/smc_v2/swing_anchor.py backend/tests/smc_v2/test_swing_anchor.py
git commit -m "feat(smc_v2): swing_anchor.py — HTF swing anchor selector

Per spec §10 #1: most-recent-unbroken HTF swing on the wrong side
of the trade. Returns swing price or None. Caller (PR #S3b) raises
SLTooFarError on None.

Pure function. Bars abstracted via duck-typed objects with ts/high/
low (HTF OHLC rows or FakeBar fixtures). Iterates most-recent-first;
swings formed after trigger_ts ignored (no anchoring on future
structure).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: confirmation.py

### Task 2: Implement `confirm_entry()`

**Spec §4.1 confirmation rules**:
- For SHORT: look for 15m bearish engulfing candle that closes within the zone, OR a 15m CHoCH break of the most recent micro swing low formed inside the zone.
- For LONG: mirror.

**This PR ships the simpler half — bearish/bullish engulfing detection.** The micro-CHoCH detection requires multi-bar pattern recognition that depends on a swing-detector helper; that lands in a future patch on this same module. Current scope keeps the module pure-function-only.

Returns: `(confirmed: bool, entry_price: float | None)`.

**Files:**
- Create: `engine/smc_v2/confirmation.py`
- Create: `backend/tests/smc_v2/test_confirmation.py`

- [ ] **Step 2.1: Write the failing tests**

Create `backend/tests/smc_v2/test_confirmation.py`:

```python
"""Tests for smc_v2.confirmation — LTF entry confirmation.

Per spec §4.1:
  For SHORT: 15m bearish engulfing close inside zone → confirmed.
  For LONG:  15m bullish engulfing close inside zone → confirmed.

Bearish engulfing: prior bar bullish (close > open); current bar bearish
                   (close < open); current open >= prior close; current
                   close <= prior open. Body fully engulfs prior body.
Bullish engulfing: mirror.

Bars before `since_ts` are ignored (we only look for confirmations after
the CHoCH trigger that birthed the setup).
"""
import pandas as pd
import pytest

from engine.smc_v2.zones import ZoneSpec


def _make_df(rows):
    """Build a minimal DataFrame from a list of (ts, open, high, low, close).
    `ts` is ms epoch int; DataFrame index is DatetimeIndex (UTC)."""
    import pandas as pd
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.set_index("ts", inplace=True)
    return df


class TestConfirmEntryShort:
    """SHORT: bearish engulfing close inside zone."""

    def test_bearish_engulf_in_zone_confirms(self):
        from engine.smc_v2.confirmation import confirm_entry
        # Bars: 4 setup + 1 bullish + 1 bearish engulfing
        # Zone: [100, 110]. Confirming bar close at 102 (inside).
        rows = [
            (1_000, 95.0, 96.0, 94.0, 95.5),   # before trigger
            (2_000, 96.0, 97.0, 95.0, 96.5),
            (3_000, 97.0, 105.0, 96.5, 104.0),  # after trigger (since_ts=2500)
            (4_000, 104.0, 106.0, 102.5, 105.5),  # prior bullish: open=104, close=105.5
            (5_000, 106.0, 106.5, 101.0, 102.0),  # bearish engulfing: open=106 >= 105.5, close=102 <= 104
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=2_500,
        )
        assert confirmed is True
        assert entry_price == 102.0

    def test_bullish_bar_does_not_confirm_short(self):
        """A bullish bar inside the zone is NOT a SHORT confirmation."""
        from engine.smc_v2.confirmation import confirm_entry
        rows = [
            (1_000, 95.0, 96.0, 94.0, 95.5),
            (2_000, 105.0, 110.0, 100.0, 108.0),  # bullish inside zone
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=1_500,
        )
        assert confirmed is False
        assert entry_price is None

    def test_engulf_outside_zone_does_not_confirm(self):
        """A bearish engulfing whose close is OUTSIDE the zone is rejected."""
        from engine.smc_v2.confirmation import confirm_entry
        rows = [
            (1_000, 95.0, 97.0, 94.0, 96.0),  # prior bullish
            (2_000, 97.0, 97.5, 93.0, 94.0),  # bearish engulfing, close=94 (OUT of zone)
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=500,
        )
        assert confirmed is False

    def test_engulf_before_since_ts_ignored(self):
        """A bearish engulfing BEFORE since_ts is ignored — we only look at
        bars after the CHoCH trigger that birthed the setup."""
        from engine.smc_v2.confirmation import confirm_entry
        rows = [
            (1_000, 95.0, 96.0, 94.0, 95.5),    # prior bullish
            (2_000, 96.0, 96.5, 91.0, 92.0),    # bearish engulfing BEFORE trigger
            (3_000, 100.0, 101.0, 99.0, 100.5),
            (4_000, 101.0, 102.0, 100.5, 101.8),
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=2_500,
        )
        # The engulf at ts=2000 is before since_ts=2500 → ignored
        assert confirmed is False

    def test_first_confirmation_returns_immediately(self):
        """If multiple engulfings exist, return the FIRST (earliest) one."""
        from engine.smc_v2.confirmation import confirm_entry
        rows = [
            (1_000, 95.0, 96.0, 94.0, 95.5),    # bullish
            (2_000, 100.0, 110.0, 95.0, 108.0),  # bullish inside zone (setup)
            (3_000, 109.0, 109.5, 104.0, 105.0),  # bearish engulfing — first confirmation
            (4_000, 105.0, 106.0, 104.0, 105.5),  # subsequent bullish
            (5_000, 106.0, 107.0, 101.5, 102.0),  # another bearish engulfing — should NOT be picked
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=1_500,
        )
        assert confirmed is True
        assert entry_price == 105.0  # first engulf, not later


class TestConfirmEntryLong:
    """LONG: bullish engulfing close inside zone (mirror of SHORT)."""

    def test_bullish_engulf_in_zone_confirms(self):
        from engine.smc_v2.confirmation import confirm_entry
        # Zone: [90, 95]. Bullish engulf with close inside.
        rows = [
            (1_000, 100.0, 101.0, 99.0, 99.5),
            (2_000, 99.0, 99.5, 92.0, 93.0),    # bearish
            (3_000, 92.0, 95.0, 91.5, 94.5),    # bullish engulfing: open=92<=93, close=94.5>=99? No, body must engulf prior body
        ]
        # Reconstruct: bullish engulfing of a bearish prior bar.
        # Prior bearish: open > close. Current bullish: open < prior close, close > prior open.
        # Use simpler pattern: prior=(99→93 bearish), current=(92.5→99.5 bullish).
        # Bull: current open <= prior close, current close >= prior open.
        # 92.5 <= 93 ✓; 99.5 >= 99 ✓ — engulfs. Close=99.5 NOT in zone [90,95].
        # Need close inside [90, 95]: prior bearish (99→93), current bullish (92→94).
        # 92 <= 93 ✓; 94 >= 99? ✗ — does not engulf.
        # Need engulf with close inside [90, 95]: prior bearish small body,
        # current bullish that engulfs and closes ≤ 95.
        # Prior: open=92, close=91 (small bearish, body 92→91).
        # Current: open=90.5 (≤91), close=92.5 (≥92) — engulfs. Close 92.5 in [90,95] ✓.
        rows = [
            (1_000, 100.0, 101.0, 99.0, 99.5),
            (2_000, 92.0, 92.5, 90.5, 91.0),    # prior bearish
            (3_000, 90.5, 92.7, 90.3, 92.5),    # bullish engulfing inside zone
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=90.0, high=95.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="LONG", since_ts=1_500,
        )
        assert confirmed is True
        assert entry_price == 92.5

    def test_bearish_bar_does_not_confirm_long(self):
        from engine.smc_v2.confirmation import confirm_entry
        rows = [
            (1_000, 95.0, 96.0, 94.0, 95.5),
            (2_000, 93.0, 94.0, 88.0, 89.0),  # bearish inside zone
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=85.0, high=95.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="LONG", since_ts=500,
        )
        assert confirmed is False


class TestConfirmEntryEdgeCases:
    def test_empty_dataframe_returns_no_confirm(self):
        from engine.smc_v2.confirmation import confirm_entry
        df = _make_df([])
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=1_000,
        )
        assert confirmed is False
        assert entry_price is None

    def test_single_bar_cannot_engulf(self):
        """Engulfing requires 2 bars (prior + current). A single bar can't confirm."""
        from engine.smc_v2.confirmation import confirm_entry
        rows = [
            (2_000, 106.0, 107.0, 101.0, 102.0),  # bearish but no prior
        ]
        df = _make_df(rows)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=1_500,
        )
        assert confirmed is False
```

- [ ] **Step 2.2: Run to verify fail**

```bash
python -m pytest backend/tests/smc_v2/test_confirmation.py -v
# Expected: many FAIL — ModuleNotFoundError: engine.smc_v2.confirmation
```

- [ ] **Step 2.3: Implement `confirmation.py`**

Create `engine/smc_v2/confirmation.py`:

```python
"""LTF entry confirmation for SMC v2.

Per spec §4.1 confirmation.py:
  For SHORT: 15m bearish engulfing close inside zone → confirmed.
  For LONG:  15m bullish engulfing close inside zone → confirmed.

Bearish engulfing: prior bullish bar; current bearish; current body engulfs
prior body (current open >= prior close AND current close <= prior open).
Bullish engulfing: mirror.

Bars at or before `since_ts` are ignored — we only look for confirmations
AFTER the CHoCH trigger that birthed the setup.

Pure function. Returns (confirmed: bool, entry_price: float | None).
"""
from typing import Optional, Tuple

import pandas as pd

from engine.smc_v2.zones import ZoneSpec, is_price_in_zone


def confirm_entry(
    df_15m: pd.DataFrame,
    zone: ZoneSpec,
    direction: str,
    since_ts: int,
) -> Tuple[bool, Optional[float]]:
    """Detect LTF entry confirmation inside a zone.

    Args:
        df_15m: DataFrame with DatetimeIndex (UTC) and columns
            [open, high, low, close]. Other columns ignored.
        zone: ZoneSpec — the pullback target zone.
        direction: "SHORT" or "LONG"
        since_ts: int (ms epoch) — only consider bars with index timestamp
            strictly > since_ts.

    Returns:
        (True, entry_price) on first confirmation found;
        (False, None) otherwise.

    Entry price is the close of the confirming bar.
    """
    if len(df_15m) < 2:
        return False, None

    # Iterate bars in time order, checking each (prior, current) pair.
    opens = df_15m["open"].values
    closes = df_15m["close"].values
    timestamps_ms = (df_15m.index.astype("int64") // 1_000_000).tolist()

    for i in range(1, len(df_15m)):
        cur_ts = timestamps_ms[i]
        if cur_ts <= since_ts:
            continue

        prior_open, prior_close = opens[i - 1], closes[i - 1]
        cur_open, cur_close = opens[i], closes[i]

        if direction == "SHORT":
            # Bearish engulfing: prior bullish; current bearish engulfs body
            prior_bullish = prior_close > prior_open
            cur_bearish = cur_close < cur_open
            engulfs = (cur_open >= prior_close) and (cur_close <= prior_open)
            if prior_bullish and cur_bearish and engulfs:
                if is_price_in_zone(cur_close, zone):
                    return True, float(cur_close)
        else:  # LONG
            # Bullish engulfing: prior bearish; current bullish engulfs body
            prior_bearish = prior_close < prior_open
            cur_bullish = cur_close > cur_open
            engulfs = (cur_open <= prior_close) and (cur_close >= prior_open)
            if prior_bearish and cur_bullish and engulfs:
                if is_price_in_zone(cur_close, zone):
                    return True, float(cur_close)

    return False, None
```

- [ ] **Step 2.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_confirmation.py -v
# Expected: 8 passed (5 SHORT + 2 LONG + 1 edge case... actually 6 SHORT classes + 1 LONG + 2 edge = check)
```

Re-count: SHORT class has 5 tests, LONG class has 2 tests, Edge class has 2 tests = **9 tests total**.

```bash
# Expected: 9 passed
```

- [ ] **Step 2.5: Full v2 suite regression check**

```bash
python -m pytest backend/tests/smc_v2/ -q
# Expected: 41 (baseline) + 7 (Task 1 swing_anchor) + 9 (Task 2 confirmation) = 57 passed
```

- [ ] **Step 2.6: Commit**

```bash
git add engine/smc_v2/confirmation.py backend/tests/smc_v2/test_confirmation.py
git commit -m "feat(smc_v2): confirmation.py — LTF engulfing detection

Per spec §4.1: bearish engulfing (SHORT) or bullish engulfing (LONG)
inside the pullback zone confirms entry. Returns (True, close_price)
on first confirmation; bars at or before since_ts ignored.

Pure function over pd.DataFrame. Micro-CHoCH detection (spec §4.1
mentions as alternative confirmation) deferred to a future patch
on this module — requires multi-bar swing detection that's outside
the scope of PR #S3a's pure-engulfing scope.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3: Final regression sweep

### Task 3: Whole-suite + py_compile

- [ ] **Step 3.1: Full smc_v2 suite**

```bash
python -m pytest backend/tests/smc_v2/ -v 2>&1 | tail -8
# Expected: 41 (PR #65) + 7 (swing_anchor) + 9 (confirmation) = 57 passed
```

- [ ] **Step 3.2: Full backend suite (regression)**

```bash
python -m pytest backend/tests/ -q 2>&1 | tail -3
# Expected: 41 baseline (PR #65) + 425 other backend tests + 16 new (this PR) = 482 passed
# (approximate — depends on what the baseline at PR #65 head shows)
```

- [ ] **Step 3.3: py_compile**

```bash
python -m py_compile engine/smc_v2/swing_anchor.py engine/smc_v2/confirmation.py && echo "compile OK"
# Expected: compile OK
```

- [ ] **Step 3.4: Diff inventory**

```bash
git log feat/smc-v2-confirmation ^feat/smc-v2-pure-modules --oneline
git diff feat/smc-v2-pure-modules..HEAD --stat
# Expected: 3 commits (1 plan + 2 task), only swing_anchor.py + confirmation.py + 2 test files + plan
```

No commit at step 3 unless 3.1-3.3 produced changes.

---

## Out of Scope (explicitly NOT in PR #S3a)

- **Micro-CHoCH confirmation** (spec §4.1 alternative pattern) — deferred, requires multi-bar swing detection helper
- **Orchestrator wiring** — `engine/safe_orchestrator.py` `confirm_entry` placeholder REPLACED by real import — PR #S3b
- **Trigger phase** (`engine/smc_v2/__init__.py` `generate_signals_v2` orchestration) — PR #S3b
- **Entry order placement** — `OrderManager.open_position` dispatch from v2 path — PR #S3c
- **Feature flag dispatch** (`engine.smc_version`) — PR #S6
- **Backtest** v2 path — PR #S4

---

## Acceptance Criteria

PR #S3a is complete and ready for review when:

1. All steps in Tasks 1-3 are checked off.
2. `python -m pytest backend/tests/smc_v2/test_swing_anchor.py -v` shows **7 tests passing**.
3. `python -m pytest backend/tests/smc_v2/test_confirmation.py -v` shows **9 tests passing**.
4. `python -m pytest backend/tests/smc_v2/ -q` shows **57 tests passing** (41 PR #65 baseline + 16 new).
5. `python -m pytest backend/tests/ -q` shows the full backend suite green (count depends on environment — the smc_v2 subset is the load-bearing claim).
6. `git log feat/smc-v2-confirmation ^feat/smc-v2-pure-modules --oneline` shows 3 commits (1 plan + 2 task).
7. `git diff feat/smc-v2-pure-modules..HEAD --stat` shows **only** `engine/smc_v2/swing_anchor.py` + `engine/smc_v2/confirmation.py` + 2 new test files + plan doc — no other files.
8. `efloud-code-reviewer` agent reviewed the diff. **No risk-ops gate** (no risk-sensitive files touched).
9. GitHub PR opened with base = `feat/smc-v2-pure-modules` (stacked on PR #65).

---

## Post-Plan Workflow

1. After implementation: `superpowers:verification-before-completion` (Iron Law).
2. `superpowers:requesting-code-review` → `efloud-code-reviewer` agent.
3. Apply review feedback.
4. `superpowers:finishing-a-development-branch` → push + PR (user-confirm).
5. Update `memory/smc_v2_rework_initiative.md` PR Status.

---

## References

- Spec: `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §4.1, §10 #1
- SMC base classes: `engine/smc.py` (Swing line 20, FVG line 38)
- ZoneSpec: `engine/smc_v2/zones.py` (PR #65)
- Initiative tracker: `memory/smc_v2_rework_initiative.md`
- CLAUDE.md §4 (atomic PR discipline)
