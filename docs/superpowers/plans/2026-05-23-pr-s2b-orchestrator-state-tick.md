# PR #S2b: Orchestrator State Tick Wiring — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the SMC v2 SetupStateStore into `SafeOrchestrator` as an opt-in dependency. Implement the **advance phase** of the state tick (bars_waited++, expire on timeout, AWAITING_PULLBACK → IN_ZONE transition on price entry). **Trigger phase** (new CHoCH detection) and **confirmation+entry** (`confirm_entry` real impl) land in PR #S3 — this PR ships only the safe scaffolding.

**Architecture:** Add an optional `setup_state_store: SetupStateStore | None = None` parameter to `SafeOrchestrator.__init__` (default `None` → fully inert — current v1 behavior unchanged). Add new helper method `_advance_setup_state_tick(symbol, current_price, current_bar_ts)` that operates ONLY when `self.setup_state_store is not None`. Add `confirm_entry` as a method placeholder that always returns `(False, None)` (real impl in PR #S3). Call `_advance_setup_state_tick` near the top of `run_cycle` behind a null guard. Save state at end of `run_cycle` if any candidates advanced.

**Tech Stack:** Python 3.12, pytest, unittest.mock. Zero new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §4.3 (data flow steps 2, 4, 5). Spec lives on `origin/feat/smc-v2-spec` (PR #64). Read with: `git show origin/feat/smc-v2-spec:docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md`.

**Branch:** `feat/smc-v2-orchestrator-wiring` — **stacked on `feat/smc-v2-setup-state`** (PR #66). GitHub PR base = PR #66's branch.

**Risk classification:** **RISK-OPS SENSITIVE.** `engine/safe_orchestrator.py` is the central trading orchestrator. Even though the new code is gated behind `setup_state_store is None` (default-inert), CLAUDE.md §4 explicitly requires `efloud-risk-ops-reviewer` for any change to `engine/safety/`, `exchange/`, `config.yaml` risk/safety, or by extension the orchestrator (`safe_orchestrator.py` coordinates safety layers and trading decisions). **Risk-ops review is mandatory before merge.**

**Inert invariant** (load-bearing for v1 safety):
- When `setup_state_store is None` (default), no method on the orchestrator changes behavior.
- The new method `_advance_setup_state_tick` short-circuits on `is None` at the first line.
- The `confirm_entry` placeholder is unreachable from v1 code paths.
- All existing tests must pass unchanged.

---

## Pre-flight Checks

- [ ] **P1:** Confirm worktree + stacked branch.

```bash
git rev-parse --show-toplevel  # Expected: .../efloud-bot/.worktrees/smc-v2-orchestrator-wiring
git branch --show-current      # Expected: feat/smc-v2-orchestrator-wiring
git log --oneline -3
# Expected: HEAD includes "45623d7 fixup(smc_v2): apply code-review feedback for PR #S2a"
```

- [ ] **P2:** Confirm baseline tests pass.

```bash
python -m pytest backend/tests/smc_v2/ -q
# Expected: 65 passed (41 PR #S1 + 24 PR #S2a)
python -m pytest backend/tests/ -q
# Expected: 531 passed (full suite — adjust if baseline drifted)
```

- [ ] **P3:** Confirm SafeOrchestrator entry points.

```bash
grep -n "class SafeOrchestrator\|def __init__\|def run_cycle" engine/safe_orchestrator.py | head -5
# Expected: class at line 120, __init__ at 128, run_cycle at 470
```

If lines drifted, find current locations before editing.

- [ ] **P4:** Confirm `engine/smc_v2/setup_state.py` exists (PR #66 base).

```bash
ls engine/smc_v2/setup_state.py
# Expected: file exists
python -c "from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore; print('OK')"
# Expected: OK
```

---

## File Structure

**Created files** (1):

- `backend/tests/smc_v2/test_orchestrator_state_tick.py` — comprehensive unit tests for the new orchestrator path

**Modified files** (1):

- `engine/safe_orchestrator.py` — add `setup_state_store` parameter, `_advance_setup_state_tick` method, `confirm_entry` placeholder, opt-in call site in `run_cycle`

**No changes to**: `engine/smc_v2/setup_state.py`, `engine/smc_v2/zones.py`, `engine/smc_v2/sl_calc.py`, `engine/smc_v2/tp_calc.py`, `engine/smc_v2/exceptions.py`, `engine/signals.py`, `engine/lifecycle.py`, `engine/safety/`, `exchange/`, `config.yaml`, `backend/db.py`, any migration. No `main.py` changes (operator wires the store in PR #S6 when feature flag lands).

**File responsibility boundaries:**

- `SafeOrchestrator` gains TWO new methods (`_advance_setup_state_tick`, `confirm_entry`) and ONE new attribute (`setup_state_store`). All v1 behavior preserved when attribute is `None`.
- `_advance_setup_state_tick` knows ONLY how to advance pending candidates one tick (increment, expire, IN_ZONE check). It does not detect new triggers (PR #S3) and does not place orders (PR #S3).
- `confirm_entry` is a stub that always returns `(False, None)` in this PR. Its real implementation lands in PR #S3. The method exists in this PR so `_advance_setup_state_tick` can call it without an AttributeError in tests.

---

## Chunk 1: Constructor parameter + inert invariant

### Task 1: Add `setup_state_store` parameter (default None → fully inert)

**Files:**
- Modify: `engine/safe_orchestrator.py:128-145` (`__init__` signature + docstring)
- Modify: `engine/safe_orchestrator.py:146-150` (attribute assignment block)
- Create: `backend/tests/smc_v2/test_orchestrator_state_tick.py`

- [ ] **Step 1.1: Write the failing test (inert default)**

Create `backend/tests/smc_v2/test_orchestrator_state_tick.py`:

```python
"""Tests for SMC v2 SetupStateStore wiring in SafeOrchestrator.

PR #S2b ships ONLY the inert opt-in scaffold:
- `setup_state_store` parameter (default None → no behavior change)
- `_advance_setup_state_tick` method (no-op when store is None)
- `confirm_entry` placeholder (always False)

Trigger phase and real confirmation land in PR #S3.
"""
from unittest.mock import MagicMock, patch
import pytest

from engine.safe_orchestrator import SafeOrchestrator


@pytest.fixture
def minimal_config():
    """Smallest config dict that lets SafeOrchestrator construct.

    Mirrors the shape used by existing safe_orchestrator tests in this repo.
    """
    return {
        "structure": {
            "swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
            "eq_threshold_pct": 0.1, "range_lookback": 50,
        },
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {"max_open_positions": 7, "min_rr": 1.8, "min_confluence": 55,
                 "risk_per_trade_pct": 0.75, "recency_bars": 40},
        "safety": {
            "daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
            "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
            "starting_balance": 10000, "max_position_notional_pct": 20,
            "max_total_exposure": 5.0, "max_holding_hours": 48,
            "max_pyramid_adds": 2, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
            "adx_trend_threshold": 25, "adx_range_threshold": 20,
            "volatile_atr_mult": 2.5, "reverse_min_profit_pct": 0.2,
        },
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "operation": {"check_interval_sec": 30, "log_level": "INFO"},
    }


class TestSetupStateStoreParameter:
    """The new `setup_state_store` parameter is optional and defaults to None.
    When None (default), no behavior changes vs v1."""

    def test_default_none_when_not_passed(self, minimal_config, tmp_path):
        orc = SafeOrchestrator(minimal_config, state_dir=str(tmp_path), persist=False)
        assert orc.setup_state_store is None

    def test_store_attribute_set_when_passed(self, minimal_config, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "setup_candidates.json")
        orc = SafeOrchestrator(
            minimal_config,
            state_dir=str(tmp_path),
            persist=False,
            setup_state_store=store,
        )
        assert orc.setup_state_store is store
```

- [ ] **Step 1.2: Run to verify it fails**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py::TestSetupStateStoreParameter -v
# Expected: FAIL — either AttributeError (no setup_state_store attribute) or
#           TypeError (constructor doesn't accept setup_state_store kwarg)
```

- [ ] **Step 1.3: Modify `SafeOrchestrator.__init__` signature**

In `engine/safe_orchestrator.py`, find the `__init__` signature around line 128. Add the new keyword-only parameter:

**BEFORE:**
```python
    def __init__(self, config: dict, state_dir: str = "./state",
                  permission_mgr=None, notification_mgr=None,
                  order_manager=None,
                  *,
                  freshness_check: bool = True,
                  persist: bool = True,
                  trade_journal: Optional[TradeJournal] = None):
```

**AFTER:**
```python
    def __init__(self, config: dict, state_dir: str = "./state",
                  permission_mgr=None, notification_mgr=None,
                  order_manager=None,
                  *,
                  freshness_check: bool = True,
                  persist: bool = True,
                  trade_journal: Optional[TradeJournal] = None,
                  setup_state_store: Optional["SetupStateStore"] = None):
        """
        ...existing docstring above...

        setup_state_store: SMC v2 SetupStateStore instance for pullback-setup
                           state tracking. **Default None → fully inert** (v1
                           behavior unchanged). When passed, the orchestrator
                           advances pending candidates each tick. Used by the
                           PR #S6 feature flag dispatch to opt into v2.
        """
```

Add the attribute assignment after the existing `self.trade_journal = trade_journal` line (around line 150):

```python
        self.trade_journal = trade_journal
        # SMC v2 SetupStateStore — None when v1 flag is active (inert default).
        # See PR #S2b + spec §4.3 for the advance/trigger/save data flow.
        self.setup_state_store = setup_state_store
```

Also add the forward-reference type import at the top of the file (if not already present). Check the existing imports:

```bash
grep "from engine.smc_v2" engine/safe_orchestrator.py
```

If no import exists, add a `TYPE_CHECKING` block to avoid a hard import (keeps v1 callers from paying the import cost):

```python
# Near the top of the file, after the existing TYPE_CHECKING block if any:
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from engine.smc_v2.setup_state import SetupStateStore
```

If a `TYPE_CHECKING` block already exists, just append the line inside it.

- [ ] **Step 1.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py::TestSetupStateStoreParameter -v
# Expected: 2 passed
```

- [ ] **Step 1.5: Run the FULL existing orchestrator test suite to verify no regression**

```bash
python -m pytest backend/tests/test_safe_orchestrator.py backend/tests/test_safe_orchestrator_v2.py backend/tests/test_orchestrator_dispatch.py -q
# Expected: all green (the inert default ensures v1 behavior is unchanged)
```

If any orchestrator test fails, **stop** and investigate before continuing. The inert invariant is non-negotiable.

- [ ] **Step 1.6: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/smc_v2/test_orchestrator_state_tick.py
git commit -m "feat(orchestrator): add inert setup_state_store parameter

Keyword-only parameter on SafeOrchestrator.__init__. Default None
→ v1 behavior unchanged (verified against existing orchestrator
test suite). When passed, the orchestrator advances pending
SMC v2 setup candidates each tick (next commit wires the method).

TYPE_CHECKING import avoids hard dependency on smc_v2 for v1
callers (paper-trade, backtest, unit tests that don't use v2).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: confirm_entry placeholder (so advance can call it)

### Task 2: `confirm_entry` stub returns `(False, None)`

**Files:**
- Modify: `engine/safe_orchestrator.py` (add new method on `SafeOrchestrator`)
- Modify: `backend/tests/smc_v2/test_orchestrator_state_tick.py`

- [ ] **Step 2.1: Write the failing test**

Append to `test_orchestrator_state_tick.py`:

```python
class TestConfirmEntryPlaceholder:
    """confirm_entry is a stub in PR #S2b — always returns (False, None).
    Real LTF CHoCH/engulfing detection lands in PR #S3.

    The stub MUST exist so _advance_setup_state_tick can call it without
    AttributeError. Tests pin the contract: signature, return type, no
    side effects.
    """

    def test_returns_false_none_tuple(self, minimal_config, tmp_path):
        from engine.smc_v2.zones import ZoneSpec
        orc = SafeOrchestrator(minimal_config, state_dir=str(tmp_path), persist=False)
        result = orc.confirm_entry(
            df_15m=MagicMock(),
            zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
            direction="SHORT",
            since_ts=1700000000000,
        )
        assert result == (False, None)

    def test_does_not_mutate_inputs(self, minimal_config, tmp_path):
        from engine.smc_v2.zones import ZoneSpec
        orc = SafeOrchestrator(minimal_config, state_dir=str(tmp_path), persist=False)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        orig_low, orig_high = zone.low, zone.high
        orc.confirm_entry(df_15m=MagicMock(), zone=zone, direction="LONG",
                          since_ts=1700000000000)
        assert zone.low == orig_low
        assert zone.high == orig_high
```

- [ ] **Step 2.2: Run to verify it fails**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py::TestConfirmEntryPlaceholder -v
# Expected: FAIL with AttributeError ('SafeOrchestrator' has no attribute 'confirm_entry')
```

- [ ] **Step 2.3: Add `confirm_entry` method to `SafeOrchestrator`**

In `engine/safe_orchestrator.py`, find a sensible location for a new method (after `run_cycle` is a good place — keeps trading code at top, scaffolding below). Add:

```python
    def confirm_entry(
        self,
        df_15m,
        zone: "ZoneSpec",
        direction: str,
        since_ts: int,
    ) -> tuple:
        """LTF entry confirmation for SMC v2 setups — placeholder.

        Spec §4.1 confirmation.py: look at 15m bars since `since_ts` that are
        inside `zone`; return (True, entry_price) when a counter-direction
        CHoCH or engulfing close confirms; else (False, None).

        **PR #S2b ships the stub returning (False, None).**
        Real implementation lands in PR #S3 (`engine/smc_v2/confirmation.py`).
        The stub exists so `_advance_setup_state_tick` can call it without
        AttributeError in tests.
        """
        return (False, None)
```

Also add `ZoneSpec` to the TYPE_CHECKING block if not already there:

```python
if TYPE_CHECKING:
    from engine.smc_v2.setup_state import SetupStateStore
    from engine.smc_v2.zones import ZoneSpec
```

- [ ] **Step 2.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py::TestConfirmEntryPlaceholder -v
# Expected: 2 passed
```

- [ ] **Step 2.5: Full orchestrator suite regression check**

```bash
python -m pytest backend/tests/test_safe_orchestrator.py backend/tests/test_safe_orchestrator_v2.py backend/tests/test_orchestrator_dispatch.py -q
# Expected: all green
```

- [ ] **Step 2.6: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/smc_v2/test_orchestrator_state_tick.py
git commit -m "feat(orchestrator): confirm_entry placeholder (PR #S3 real impl)

Stub returns (False, None) — needed by _advance_setup_state_tick
so tests can exercise the advance phase without an AttributeError.
Real LTF CHoCH/engulfing detection lands in PR #S3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3: `_advance_setup_state_tick` — the heart of PR #S2b

### Task 3: Advance phase — bars_waited++, expire, IN_ZONE transition

This is the load-bearing logic for PR #S2b. Per spec §4.3 step 2 (only the **advance** half; trigger half is PR #S3):

```
For each pending candidate:
    bars_waited += 1
    if bars_waited > pullback_timeout_bars: state = EXPIRED
    elif state == AWAITING_PULLBACK and price ∈ zone: state = IN_ZONE
    (if state == IN_ZONE: try confirm_entry → stub returns False in PR #S2b)
```

**Files:**
- Modify: `engine/safe_orchestrator.py` (add `_advance_setup_state_tick` method)
- Modify: `backend/tests/smc_v2/test_orchestrator_state_tick.py`

- [ ] **Step 3.1: Write the failing tests**

Append to `test_orchestrator_state_tick.py`:

```python
class TestAdvanceSetupStateTick:
    """_advance_setup_state_tick(symbol, current_price, current_bar_ts) operates
    on candidates in self.setup_state_store. Per-tick semantics:

    - bars_waited += 1 (incremented BEFORE timeout check)
    - if bars_waited > timeout: state = EXPIRED, dropped at next save
    - elif AWAITING_PULLBACK and price ∈ zone: state = IN_ZONE
    - if IN_ZONE: call self.confirm_entry; if True, state = CONFIRMED
                  (stub returns False in PR #S2b → nothing happens)

    All operations are scoped to candidates matching `symbol`. Other-symbol
    candidates are untouched in this tick.
    """

    @pytest.fixture
    def store_with_pending(self, tmp_path):
        from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
        from engine.smc_v2.zones import ZoneSpec
        store = SetupStateStore(tmp_path / "state.json")
        store.add(SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=1700000000000, trigger_price=95000.0,
            htf_bias="BEAR",
            target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
            htf_swing_anchor=98000.0, bars_waited=0,
            state="AWAITING_PULLBACK", confluence_score=75, reasons=[],
        ))
        return store

    def test_inert_when_store_is_none(self, minimal_config, tmp_path):
        """Default-inert: with no store, the method short-circuits with no error."""
        orc = SafeOrchestrator(minimal_config, state_dir=str(tmp_path), persist=False)
        # Should NOT raise even though setup_state_store is None
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=96500.0, current_bar_ts=1700000060000,
        )
        # No state to inspect — just verify no exception

    def test_bars_waited_increments(self, minimal_config, tmp_path, store_with_pending):
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store_with_pending,
        )
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=95500.0,  # outside zone, no transition
            current_bar_ts=1700000060000,
        )
        cand = store_with_pending.candidates[0]
        assert cand.bars_waited == 1
        assert cand.state == "AWAITING_PULLBACK"  # still pending, no zone entry

    def test_price_in_zone_transitions_to_in_zone(
        self, minimal_config, tmp_path, store_with_pending
    ):
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store_with_pending,
        )
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=96500.0,  # inside [96000, 97000]
            current_bar_ts=1700000060000,
        )
        cand = store_with_pending.candidates[0]
        assert cand.bars_waited == 1
        assert cand.state == "IN_ZONE"

    def test_other_symbol_untouched(
        self, minimal_config, tmp_path, store_with_pending
    ):
        """Ticking BTC must not increment ETH/USDT candidates."""
        from engine.smc_v2.setup_state import SetupCandidate
        from engine.smc_v2.zones import ZoneSpec
        store_with_pending.add(SetupCandidate(
            symbol="ETH/USDT", direction="LONG",
            trigger_bar_ts=1700000000000, trigger_price=2400.0,
            htf_bias="BULL",
            target_zone=ZoneSpec(low=2380.0, high=2390.0, source="OTE"),
            htf_swing_anchor=2350.0, bars_waited=0,
            state="AWAITING_PULLBACK", confluence_score=60, reasons=[],
        ))
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store_with_pending,
        )
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=96500.0,
            current_bar_ts=1700000060000,
        )
        btc = next(c for c in store_with_pending.candidates if c.symbol == "BTC/USDT")
        eth = next(c for c in store_with_pending.candidates if c.symbol == "ETH/USDT")
        assert btc.bars_waited == 1
        assert eth.bars_waited == 0  # untouched

    def test_expire_on_timeout(self, minimal_config, tmp_path):
        """bars_waited > 8 (default timeout) → state = EXPIRED."""
        from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
        from engine.smc_v2.zones import ZoneSpec
        store = SetupStateStore(tmp_path / "state.json")
        # Already at bars_waited=8, next tick will push it to 9 > 8 → EXPIRE
        store.add(SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=1700000000000, trigger_price=95000.0,
            htf_bias="BEAR",
            target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
            htf_swing_anchor=98000.0, bars_waited=8,
            state="AWAITING_PULLBACK", confluence_score=75, reasons=[],
        ))
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=95500.0,
            current_bar_ts=1700000540000,
        )
        cand = store.candidates[0]
        assert cand.state == "EXPIRED"

    def test_in_zone_calls_confirm_entry(
        self, minimal_config, tmp_path, store_with_pending
    ):
        """When state advances to IN_ZONE, confirm_entry is called.
        The stub returns (False, None) so state stays IN_ZONE."""
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store_with_pending,
        )
        # Patch confirm_entry to spy on the call
        with patch.object(orc, "confirm_entry", return_value=(False, None)) as spy:
            orc._advance_setup_state_tick(
                symbol="BTC/USDT", current_price=96500.0,
                current_bar_ts=1700000060000,
            )
            assert spy.call_count == 1
            call_kwargs = spy.call_args.kwargs
            # confirm_entry should be called with the zone, direction, trigger_ts
            assert call_kwargs["direction"] == "SHORT"
            assert call_kwargs["since_ts"] == 1700000000000
        # state remains IN_ZONE (confirm returned False)
        assert store_with_pending.candidates[0].state == "IN_ZONE"

    def test_already_in_zone_stays_in_zone(
        self, minimal_config, tmp_path
    ):
        """A candidate already in IN_ZONE state stays IN_ZONE; only bars_waited
        increments (IN_ZONE is sticky per spec §3 state diagram)."""
        from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
        from engine.smc_v2.zones import ZoneSpec
        store = SetupStateStore(tmp_path / "state.json")
        store.add(SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=1700000000000, trigger_price=95000.0,
            htf_bias="BEAR",
            target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
            htf_swing_anchor=98000.0, bars_waited=3,
            state="IN_ZONE", confluence_score=75, reasons=[],
        ))
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )
        # Price now OUTSIDE the zone — IN_ZONE must stay (sticky)
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=95500.0,
            current_bar_ts=1700000240000,
        )
        cand = store.candidates[0]
        assert cand.state == "IN_ZONE"
        assert cand.bars_waited == 4

    def test_confirmed_setup_not_re_processed(self, minimal_config, tmp_path):
        """CONFIRMED state is terminal — advance must not touch it."""
        from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
        from engine.smc_v2.zones import ZoneSpec
        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=1700000000000, trigger_price=95000.0,
            htf_bias="BEAR",
            target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
            htf_swing_anchor=98000.0, bars_waited=5,
            state="CONFIRMED", confluence_score=75, reasons=[],
        ))
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=96500.0,
            current_bar_ts=1700000060000,
        )
        cand = store.candidates[0]
        assert cand.bars_waited == 5  # untouched
        assert cand.state == "CONFIRMED"
```

- [ ] **Step 3.2: Run to verify they fail**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py::TestAdvanceSetupStateTick -v
# Expected: many FAIL — _advance_setup_state_tick doesn't exist yet
```

- [ ] **Step 3.3: Implement `_advance_setup_state_tick`**

In `engine/safe_orchestrator.py`, add the new method near the `confirm_entry` placeholder. Default timeout uses spec §4.3 default of 8 bars:

```python
    def _advance_setup_state_tick(
        self,
        symbol: str,
        current_price: float,
        current_bar_ts: int,
        pullback_timeout_bars: int = 8,
    ) -> None:
        """Advance pending SMC v2 setup candidates for `symbol` by one tick.

        Per spec §4.3 step 2 (advance phase only — trigger phase is PR #S3):
          For each pending candidate matching symbol:
            1. bars_waited += 1
            2. If bars_waited > pullback_timeout_bars → state = EXPIRED
            3. Elif state == AWAITING_PULLBACK and price ∈ zone → state = IN_ZONE
            4. If state == IN_ZONE → call confirm_entry; if True → state = CONFIRMED
               (PR #S2b stub returns False; real impl in PR #S3)

        Inert when `self.setup_state_store is None` — short-circuits with no
        side effects. This is the load-bearing invariant for v1 safety.

        Other-symbol candidates are untouched (operation is scoped to `symbol`).
        Terminal states (CONFIRMED, EXPIRED) are skipped — they wait for the
        next save() call to be pruned.
        """
        # Inert default — no v1 behavior change
        if self.setup_state_store is None:
            return

        # Local import to avoid module-level circular dependency on smc_v2
        from engine.smc_v2.zones import is_price_in_zone
        from engine.smc_v2.setup_state import PERSISTED_STATES

        for cand in self.setup_state_store.candidates:
            if cand.symbol != symbol:
                continue
            if cand.state not in PERSISTED_STATES:
                # CONFIRMED or EXPIRED — terminal, skip
                continue

            cand.bars_waited += 1

            if cand.bars_waited > pullback_timeout_bars:
                cand.state = "EXPIRED"
                continue

            if cand.state == "AWAITING_PULLBACK" and is_price_in_zone(
                current_price, cand.target_zone
            ):
                cand.state = "IN_ZONE"

            if cand.state == "IN_ZONE":
                # confirm_entry stub returns (False, None) in PR #S2b
                # Real impl in PR #S3 uses df_15m to detect LTF CHoCH/engulfing
                confirmed, entry_px = self.confirm_entry(
                    df_15m=None,  # PR #S3 will pass the real DataFrame
                    zone=cand.target_zone,
                    direction=cand.direction,
                    since_ts=cand.trigger_bar_ts,
                )
                if confirmed:
                    cand.state = "CONFIRMED"
                    # Entry order placement also lands in PR #S3
                    # (signals.py → OrderManager.open_position dispatch)
```

- [ ] **Step 3.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py::TestAdvanceSetupStateTick -v
# Expected: 8 passed
```

- [ ] **Step 3.5: Full orchestrator regression check**

```bash
python -m pytest backend/tests/test_safe_orchestrator.py backend/tests/test_safe_orchestrator_v2.py backend/tests/test_orchestrator_dispatch.py -q
# Expected: all green — inert invariant holds
```

- [ ] **Step 3.6: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/smc_v2/test_orchestrator_state_tick.py
git commit -m "feat(orchestrator): _advance_setup_state_tick (PR #S2b core)

Per spec §4.3 step 2 — advance phase only:
- bars_waited++ each tick
- EXPIRE on timeout (default 8 bars per spec §4.3)
- AWAITING_PULLBACK → IN_ZONE on price entry into zone
- IN_ZONE → confirm_entry call (stub returns False in PR #S2b)

Inert when setup_state_store is None — v1 path untouched.
Trigger phase (new CHoCH → emit SetupCandidate) lands in PR #S3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 4: Opt-in run_cycle wiring + save at end

### Task 4: Call `_advance_setup_state_tick` from `run_cycle` (gated)

**Files:**
- Modify: `engine/safe_orchestrator.py:run_cycle` around line 505 (after `current_price` extraction)
- Modify: `engine/safe_orchestrator.py:run_cycle` near the end (save state if store is wired)
- Modify: `backend/tests/smc_v2/test_orchestrator_state_tick.py`

- [ ] **Step 4.1: Write the failing test**

Append to `test_orchestrator_state_tick.py`:

```python
class TestRunCycleAdvanceCall:
    """run_cycle calls _advance_setup_state_tick when store is wired.
    When store is None (default), the method is NOT called (inert path
    must remain truly inert — no overhead even from spying)."""

    def _make_df(self, length=50, base_price=95000.0):
        """Construct a minimal valid OHLCV DataFrame for run_cycle.
        Real shape: DatetimeIndex (UTC), columns [open,high,low,close,volume]."""
        import pandas as pd
        from datetime import datetime, timezone, timedelta
        idx = pd.date_range(
            end=datetime.now(timezone.utc), periods=length, freq="15min", tz="UTC",
        )
        df = pd.DataFrame({
            "open": [base_price] * length,
            "high": [base_price * 1.001] * length,
            "low": [base_price * 0.999] * length,
            "close": [base_price] * length,
            "volume": [1000.0] * length,
        }, index=idx)
        return df

    def test_advance_called_when_store_wired(self, minimal_config, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store, freshness_check=False,
        )
        df = self._make_df()
        with patch.object(orc, "_advance_setup_state_tick") as spy:
            orc.run_cycle(
                symbol="BTC/USDT", df_htf=df, df_mtf=df, df_entry=df,
                balance=10000.0,
            )
            assert spy.call_count == 1
            # Called with current price (last close of df_entry)
            assert spy.call_args.kwargs["symbol"] == "BTC/USDT"
            assert spy.call_args.kwargs["current_price"] == 95000.0

    def test_advance_not_called_when_store_none(self, minimal_config, tmp_path):
        """Inert default: no spy call, no overhead, no v1 behavior change."""
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            freshness_check=False,
        )
        df = self._make_df()
        with patch.object(orc, "_advance_setup_state_tick") as spy:
            orc.run_cycle(
                symbol="BTC/USDT", df_htf=df, df_mtf=df, df_entry=df,
                balance=10000.0,
            )
            # When store is None, run_cycle must NOT call the advance method
            assert spy.call_count == 0
```

- [ ] **Step 4.2: Run to verify it fails**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py::TestRunCycleAdvanceCall -v
# Expected: FAIL (spy.call_count == 0 in first test)
```

- [ ] **Step 4.3: Wire the call into `run_cycle`**

In `engine/safe_orchestrator.py`, find `run_cycle` (~line 470). After `current_price` is extracted (around line 505) and BEFORE STEP 0 MAE/MFE tracking, add the gated call:

```python
        current_price = float(df_entry["close"].iloc[-1])
        bar_high = float(df_entry["high"].iloc[-1])
        bar_low = float(df_entry["low"].iloc[-1])

        # SMC v2 setup state advance — opt-in, inert when store is None.
        # Must run BEFORE breaker check so EXPIRE transitions get recorded
        # even on no-trade ticks (operator observability).
        if self.setup_state_store is not None:
            current_bar_ts = int(df_entry.index[-1].timestamp() * 1000)
            self._advance_setup_state_tick(
                symbol=symbol,
                current_price=current_price,
                current_bar_ts=current_bar_ts,
            )

        # ═══ STEP 0: Per-bar MAE/MFE tracking ═══
        ...
```

- [ ] **Step 4.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py::TestRunCycleAdvanceCall -v
# Expected: 2 passed
```

- [ ] **Step 4.5: Full orchestrator regression check (CRITICAL)**

```bash
python -m pytest backend/tests/test_safe_orchestrator.py backend/tests/test_safe_orchestrator_v2.py backend/tests/test_orchestrator_dispatch.py -q
# Expected: all green — inert invariant holds
```

If any test fails, the wiring broke v1. Stop, investigate, revert if needed.

- [ ] **Step 4.6: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/smc_v2/test_orchestrator_state_tick.py
git commit -m "feat(orchestrator): wire _advance_setup_state_tick into run_cycle

Gated by 'if self.setup_state_store is not None' — when store is
None (default), the call is skipped entirely (verified: spy
call_count == 0). v1 path untouched.

Placed BEFORE breaker check so EXPIRE transitions are recorded
even on halted-breaker ticks (operator observability).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Save state at end of `run_cycle` when wired

The state must be persisted so EXPIRE / IN_ZONE transitions survive bot restart. Without save(), the in-memory list updates but `setup_candidates.json` stays stale.

**Files:**
- Modify: `engine/safe_orchestrator.py:run_cycle` (add save at end, gated)
- Modify: `backend/tests/smc_v2/test_orchestrator_state_tick.py`

- [ ] **Step 5.1: Write the failing test**

Append:

```python
class TestRunCycleSaveState:
    """After run_cycle advances candidates, the orchestrator MUST call
    store.save() so state survives restart. Inert when store is None."""

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

    def test_save_called_when_store_wired(self, minimal_config, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store, freshness_check=False,
        )
        df = self._make_df()
        with patch.object(store, "save") as spy:
            orc.run_cycle(
                symbol="BTC/USDT", df_htf=df, df_mtf=df, df_entry=df,
                balance=10000.0,
            )
            assert spy.call_count == 1

    def test_save_not_called_when_store_none(self, minimal_config, tmp_path):
        """Inert default: no save attempt (no AttributeError, no overhead)."""
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            freshness_check=False,
        )
        df = self._make_df()
        # Should complete without AttributeError (no store.save attempt)
        orc.run_cycle(
            symbol="BTC/USDT", df_htf=df, df_mtf=df, df_entry=df,
            balance=10000.0,
        )

    def test_save_called_even_on_no_candidates(self, minimal_config, tmp_path):
        """Empty store still saves (writes empty file) — operator can confirm
        the orchestrator is actively persisting."""
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        # No candidates added
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store, freshness_check=False,
        )
        df = self._make_df()
        with patch.object(store, "save") as spy:
            orc.run_cycle(
                symbol="BTC/USDT", df_htf=df, df_mtf=df, df_entry=df,
                balance=10000.0,
            )
            assert spy.call_count == 1
```

- [ ] **Step 5.2: Run to verify fail (1st + 3rd, 2nd may already pass)**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py::TestRunCycleSaveState -v
# Expected: 2 FAIL (save not called when wired), 1 PASS (inert no-error)
```

- [ ] **Step 5.3: Add save call at end of run_cycle**

In `engine/safe_orchestrator.py`, find the END of `run_cycle` (the return statement). Add a gated save call right before the final return:

```python
        # SMC v2 — persist state if wired (gated, inert when None)
        if self.setup_state_store is not None:
            try:
                self.setup_state_store.save()
            except Exception as e:
                # Save errors must not abort the cycle — log and continue
                log.error(f"setup_state save failed (continuing cycle): {e}")

        return result  # or whatever the existing return is
```

To find the exact location, search for the return:

```bash
grep -n "return result\|return SafeCycleResult\|return.*Result(" engine/safe_orchestrator.py | head -5
```

Place the save **before** the return, **after** all other STEP logic (so transitions made during the cycle are persisted).

- [ ] **Step 5.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py::TestRunCycleSaveState -v
# Expected: 3 passed
```

- [ ] **Step 5.5: Full orchestrator regression check (CRITICAL)**

```bash
python -m pytest backend/tests/test_safe_orchestrator.py backend/tests/test_safe_orchestrator_v2.py backend/tests/test_orchestrator_dispatch.py -q
# Expected: all green
```

- [ ] **Step 5.6: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/smc_v2/test_orchestrator_state_tick.py
git commit -m "feat(orchestrator): persist setup_state at end of run_cycle

Gated save call (only when store wired). Save errors logged but
do NOT abort the cycle — persistence failure must not break trading.

Empty store still saves (writes empty file) — operator can confirm
the orchestrator is actively persisting via mtime on
state/setup_candidates.json.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 5: Final regression sweep

### Task 6: Whole-suite regression + py_compile

- [ ] **Step 6.1: Full smc_v2 suite**

```bash
python -m pytest backend/tests/smc_v2/ -v 2>&1 | tail -10
# Expected: 65 (PR #S1+S2a) + new tests:
#   TestSetupStateStoreParameter (2) + TestConfirmEntryPlaceholder (2)
#   + TestAdvanceSetupStateTick (8) + TestRunCycleAdvanceCall (2)
#   + TestRunCycleSaveState (3) = 17 new = 82 total
```

- [ ] **Step 6.2: Full backend suite (regression)**

```bash
python -m pytest backend/tests/ -q 2>&1 | tail -3
# Expected: 531 (S1+S2a baseline) + 17 (PR #S2b) = 548 passed
```

- [ ] **Step 6.3: py_compile**

```bash
python -m py_compile engine/safe_orchestrator.py && echo "compile OK"
# Expected: compile OK
```

- [ ] **Step 6.4: Diff inventory**

```bash
git log feat/smc-v2-orchestrator-wiring ^feat/smc-v2-setup-state --oneline
git diff feat/smc-v2-setup-state..HEAD --stat
# Expected: 6 commits (1 plan + 5 task), only safe_orchestrator.py + test file + plan
```

No new commit unless 6.1-6.3 surface changes.

---

## Out of Scope (explicitly NOT in PR #S2b)

- **Trigger phase** — detecting new CHoCH/BoS and emitting new `SetupCandidate` instances (lands in PR #S3 alongside the dispatch logic)
- **Real `confirm_entry`** — LTF CHoCH/engulfing detection inside the zone (PR #S3, `engine/smc_v2/confirmation.py`)
- **Real entry placement** — when `confirm_entry` returns True, the signal goes through `OrderManager.open_position` (PR #S3, signals.py wiring)
- **`select_htf_swing_anchor`** algorithm — PR #S3
- **Feature flag config (`engine.smc_version: v2`)** — PR #S6
- **`main.py` wiring of `setup_state_store`** — PR #S6 (config-flag driven)
- **Backtest path** — PR #S4 (in-memory state container)
- **Lifecycle / db telemetry** — PR #S5

---

## Acceptance Criteria

PR #S2b is complete and ready for review when:

1. All steps in Tasks 1-6 are checked off.
2. `python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py -v` shows **17 tests passing** (2 param + 2 confirm_entry + 8 advance + 2 run_cycle_call + 3 run_cycle_save).
3. `python -m pytest backend/tests/smc_v2/ -v` shows **82 tests passing** (65 PR #S1+S2a + 17 PR #S2b).
4. `python -m pytest backend/tests/ -q` shows the full suite still green (~548 passed).
5. **CRITICAL: Existing orchestrator tests unchanged.** `pytest backend/tests/test_safe_orchestrator*.py backend/tests/test_orchestrator_dispatch.py -q` returns the same pass count as on the base branch (no regression). This is the inert invariant.
6. `git log feat/smc-v2-orchestrator-wiring ^feat/smc-v2-setup-state --oneline` shows 6 commits (1 plan + 5 task).
7. `git diff feat/smc-v2-setup-state..HEAD --stat` shows **only** `engine/safe_orchestrator.py` (modified) + `backend/tests/smc_v2/test_orchestrator_state_tick.py` (created) + plan doc — no other files.
8. `efloud-code-reviewer` reviewed the diff.
9. **`efloud-risk-ops-reviewer` (or equivalent risk-ops focused review) reviewed and APPROVED.** Per CLAUDE.md §4, `safe_orchestrator.py` changes require risk-ops sign-off.
10. GitHub PR opened with base = `feat/smc-v2-setup-state` (stacked on PR #66).

---

## Post-Plan Workflow

1. After implementation: `superpowers:verification-before-completion` (Iron Law).
2. `superpowers:requesting-code-review` → `efloud-code-reviewer` FIRST PASS.
3. Risk-ops SECOND PASS via general-purpose agent with risk-ops focused brief (same pattern used on PR #C1 — see memory `smc_v2_rework_initiative.md`).
4. Apply review feedback if any.
5. `superpowers:finishing-a-development-branch` → push + PR (user-confirm shared-state).
6. Update `memory/smc_v2_rework_initiative.md` PR Status.

---

## References

- Spec: `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §4.3
- Initiative tracker: `memory/smc_v2_rework_initiative.md`
- CLAUDE.md §3 (Live Ops), §4 (PR & Review), §7 (custom agents)
- Reference for opt-in scaffolding: `OrderManager`'s `state_dir` parameter (similarly inert when None)
