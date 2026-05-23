# PR #S3b: Real confirm_entry Wiring — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `SafeOrchestrator.confirm_entry` placeholder (returns `(False, None)`) with a proxy that delegates to the real `engine.smc_v2.confirmation.confirm_entry` (LTF engulfing detection inside the zone). Plumb `df_15m` from `run_cycle` through `_advance_setup_state_tick` so confirmation has live LTF data.

**Architecture:** `SafeOrchestrator.confirm_entry` becomes a thin proxy. Add `df_15m: pd.DataFrame` parameter to `_advance_setup_state_tick`. `run_cycle` passes `df_entry` as `df_15m`. Inert invariant preserved: when `setup_state_store is None`, nothing changes.

**Tech Stack:** Python 3.12, pandas, pytest. Zero new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §4.1 + §4.3 (orchestrator data flow).

**Branch:** `feat/smc-v2-trigger-integration` (off master, includes PR #65/#66/#67/#68).

**Risk classification:** **RISK-OPS SENSITIVE** — `engine/safe_orchestrator.py` modified. But the change is **inert by feature-flag**: `setup_state_store=None` (current production default) → no behavior change. Existing 12 v1 orchestrator tests must stay green.

**Scope discipline**: PR #S3b is ONLY the confirm_entry wiring. **Out of scope** (deferred to PR #S3c): trigger phase (new CHoCH → SetupCandidate emission), feature flag dispatch, entry order placement.

---

## Pre-flight Checks

- [ ] **P1:** Confirm worktree + branch.

```bash
git rev-parse --show-toplevel  # Expected: .../efloud-bot/.worktrees/smc-v2-trigger-integration
git branch --show-current      # Expected: feat/smc-v2-trigger-integration
git log --oneline -3           # Expected: PR #67 squash-merge at top (5094827)
```

- [ ] **P2:** Confirm baseline tests.

```bash
python -m pytest backend/tests/smc_v2/ -q
# Expected: 99 passed (41 + 24 + 17 + 17)
```

- [ ] **P3:** Confirm placeholder exists.

```bash
grep -n "def confirm_entry\|return (False, None)" engine/safe_orchestrator.py | head -3
# Expected: confirm_entry at ~1008, returns (False, None) stub
```

---

## File Structure

**Modified files** (1):
- `engine/safe_orchestrator.py` — replace `confirm_entry` body to delegate; add `df_15m` parameter to `_advance_setup_state_tick`; pass `df_entry` from `run_cycle`

**Created files** (1):
- `backend/tests/smc_v2/test_orchestrator_confirm_wiring.py` — integration tests proving real confirm_entry path triggers CONFIRMED state when engulfing pattern present in df_15m

**No changes to**: `engine/smc_v2/*`, `engine/safety/`, `exchange/`, `engine/lifecycle.py`, `config.yaml`, `backend/db.py`, any migration, `main.py`, `bot_runner.py`.

---

## Chunk 1: Proxy confirm_entry to real impl

### Task 1: Replace placeholder body with delegation

**Files:**
- Modify: `engine/safe_orchestrator.py:1008-1025` (`confirm_entry` method)
- Create: `backend/tests/smc_v2/test_orchestrator_confirm_wiring.py`

- [ ] **Step 1.1: Write the failing test**

Create `backend/tests/smc_v2/test_orchestrator_confirm_wiring.py`:

```python
"""Tests for SMC v2 confirm_entry real wiring in SafeOrchestrator.

PR #S3b replaces the (False, None) placeholder with a proxy to
engine.smc_v2.confirmation.confirm_entry. Verifies:
- Proxy returns same value as direct call
- df_15m flows through _advance_setup_state_tick correctly
- IN_ZONE candidate transitions to CONFIRMED when engulfing pattern present
"""
import pandas as pd
import pytest

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.zones import ZoneSpec


def _engulf_df():
    """DataFrame with a bearish engulfing pattern at ts=5000."""
    rows = [
        (1_000, 95.0, 96.0, 94.0, 95.5),
        (2_000, 96.0, 97.0, 95.0, 96.5),
        (3_000, 97.0, 105.0, 96.5, 104.0),
        (4_000, 104.0, 106.0, 102.5, 105.5),  # prior bullish
        (5_000, 106.0, 106.5, 101.0, 102.0),  # bearish engulfing (close=102 in zone)
    ]
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.set_index("ts", inplace=True)
    return df


def _minimal_config():
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


class TestConfirmEntryProxy:
    """SafeOrchestrator.confirm_entry is no longer a stub.
    It delegates to engine.smc_v2.confirmation.confirm_entry."""

    def test_proxy_returns_true_for_engulfing(self, tmp_path):
        orc = SafeOrchestrator(_minimal_config(), state_dir=str(tmp_path), persist=False)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = orc.confirm_entry(
            df_15m=_engulf_df(), zone=zone, direction="SHORT", since_ts=2_500,
        )
        assert confirmed is True
        assert entry_price == 102.0

    def test_proxy_returns_false_when_no_engulfing(self, tmp_path):
        orc = SafeOrchestrator(_minimal_config(), state_dir=str(tmp_path), persist=False)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        # Use a DataFrame with no engulfing — all bullish
        df = pd.DataFrame(
            {"open": [100.0, 101.0], "high": [102.0, 103.0],
             "low": [99.0, 100.0], "close": [101.0, 102.0]},
            index=pd.to_datetime([1_000, 2_000], unit="ms", utc=True),
        )
        confirmed, entry_price = orc.confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=500,
        )
        assert confirmed is False
        assert entry_price is None

    def test_proxy_matches_direct_call(self, tmp_path):
        """Proxy result must match calling engine.smc_v2.confirmation.confirm_entry directly."""
        from engine.smc_v2.confirmation import confirm_entry as direct
        orc = SafeOrchestrator(_minimal_config(), state_dir=str(tmp_path), persist=False)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        df = _engulf_df()
        direct_result = direct(df_15m=df, zone=zone, direction="SHORT", since_ts=2_500)
        proxy_result = orc.confirm_entry(df_15m=df, zone=zone, direction="SHORT", since_ts=2_500)
        assert direct_result == proxy_result
```

- [ ] **Step 1.2: Run to verify (stub still returns False, all tests fail)**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_confirm_wiring.py::TestConfirmEntryProxy -v
# Expected: 3 FAIL (stub returns (False, None) for engulfing case; matches False=False but expected True)
```

Actually the stub returns `(False, None)` for ALL cases — so:
- `test_proxy_returns_true_for_engulfing`: FAIL (assert confirmed is True, got False)
- `test_proxy_returns_false_when_no_engulfing`: PASS (stub happens to return False, matches)
- `test_proxy_matches_direct_call`: FAIL (direct=True, proxy=False)

Expected: 2 FAIL, 1 PASS.

- [ ] **Step 1.3: Replace placeholder body**

In `engine/safe_orchestrator.py`, find `def confirm_entry` (around line 1008). Replace the body:

**BEFORE:**
```python
    def confirm_entry(
        self,
        df_15m,
        zone: "ZoneSpec",
        direction: str,
        since_ts: int,
    ) -> tuple:
        """LTF entry confirmation for SMC v2 setups — placeholder.

        Spec §4.1 confirmation.py: ...

        **PR #S2b ships the stub returning (False, None).**
        Real implementation lands in PR #S3 (`engine/smc_v2/confirmation.py`).
        The stub exists so `_advance_setup_state_tick` can call it without
        AttributeError in tests.
        """
        return (False, None)
```

**AFTER:**
```python
    def confirm_entry(
        self,
        df_15m,
        zone: "ZoneSpec",
        direction: str,
        since_ts: int,
    ) -> tuple:
        """LTF entry confirmation for SMC v2 setups.

        Thin proxy to `engine.smc_v2.confirmation.confirm_entry` (spec §4.1).
        Detects bearish engulfing (SHORT) or bullish engulfing (LONG) inside
        the pullback zone, with close inside the zone, after `since_ts`.

        Returns: (True, entry_price) on first confirmation; (False, None) else.

        Wired in PR #S3b. Previously a placeholder returning (False, None)
        from PR #S2b — the real implementation now lives in
        engine/smc_v2/confirmation.py (PR #68 / #S3a).
        """
        # Local import to keep the orchestrator module import-light when
        # v2 is not active. Matches the existing pattern in
        # _advance_setup_state_tick.
        from engine.smc_v2.confirmation import confirm_entry as _confirm
        return _confirm(
            df_15m=df_15m, zone=zone, direction=direction, since_ts=since_ts,
        )
```

- [ ] **Step 1.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_confirm_wiring.py::TestConfirmEntryProxy -v
# Expected: 3 passed
```

- [ ] **Step 1.5: Critical v1 regression check**

```bash
python -m pytest backend/tests/test_orchestrator_order_bridge.py backend/tests/test_safe_orchestrator_client_attr.py backend/tests/test_safe_orchestrator_flags.py -q
# Expected: 12 passed (v1 path untouched, confirm_entry only invoked from v2 path)
```

PR #67 state tick wiring test:

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py -q
# Expected: 17 passed (PR #67 tests use patch.object(orc, "confirm_entry") so they still pass)
```

- [ ] **Step 1.6: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/smc_v2/test_orchestrator_confirm_wiring.py
git commit -m "feat(orchestrator): wire real confirm_entry (PR #S3b)

Replace PR #S2b placeholder with thin proxy to
engine.smc_v2.confirmation.confirm_entry (PR #S3a /  #68).

Inert invariant preserved: confirm_entry is only invoked from
_advance_setup_state_tick which short-circuits when
setup_state_store is None (current production default).

v1 regression: 12 v1 orchestrator tests green; 17 PR #67
state-tick tests green (they patch.object the method).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: Plumb df_15m through _advance_setup_state_tick

### Task 2: Add `df_15m` parameter + pass from run_cycle

**Files:**
- Modify: `engine/safe_orchestrator.py:1028+` (`_advance_setup_state_tick` signature)
- Modify: `engine/safe_orchestrator.py:519-531` (`run_cycle` call site)
- Modify: `backend/tests/smc_v2/test_orchestrator_confirm_wiring.py` (add integration test)

- [ ] **Step 2.1: Write the failing test (real IN_ZONE → CONFIRMED transition)**

Append to `test_orchestrator_confirm_wiring.py`:

```python
class TestAdvanceWithRealConfirmation:
    """When _advance_setup_state_tick is called with a real df_15m that
    contains an engulfing pattern, an IN_ZONE candidate should transition
    to CONFIRMED."""

    def _make_in_zone_candidate(self):
        from engine.smc_v2.setup_state import SetupCandidate
        return SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=2_500,           # bars at ts=3000+ count as confirmations
            trigger_price=100.0, htf_bias="BEAR",
            target_zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
            htf_swing_anchor=115.0, bars_waited=2,
            state="IN_ZONE",                 # already in zone; confirm should fire
            confluence_score=75, reasons=[],
        )

    def test_in_zone_transitions_to_confirmed_with_engulfing_df(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(self._make_in_zone_candidate())

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )

        # Engulf at ts=5000 → confirmed
        orc._advance_setup_state_tick(
            symbol="BTC/USDT",
            current_price=102.0,
            current_bar_ts=5_000,
            df_15m=_engulf_df(),
        )
        cand = store.candidates[0]
        assert cand.state == "CONFIRMED"

    def test_in_zone_stays_in_zone_without_engulfing(self, tmp_path):
        """No engulfing pattern → IN_ZONE stays."""
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(self._make_in_zone_candidate())

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )

        # All-bullish DataFrame, no engulfing
        df = pd.DataFrame(
            {"open": [100.0, 101.0, 102.0], "high": [102.0, 103.0, 104.0],
             "low": [99.0, 100.0, 101.0], "close": [101.0, 102.0, 103.0]},
            index=pd.to_datetime([3_000, 4_000, 5_000], unit="ms", utc=True),
        )
        orc._advance_setup_state_tick(
            symbol="BTC/USDT",
            current_price=103.0,
            current_bar_ts=5_000,
            df_15m=df,
        )
        cand = store.candidates[0]
        assert cand.state == "IN_ZONE"  # stays, no confirmation
```

- [ ] **Step 2.2: Run to verify it fails**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_confirm_wiring.py::TestAdvanceWithRealConfirmation -v
# Expected: FAIL — _advance_setup_state_tick doesn't accept df_15m kwarg yet
```

Actually the existing signature has no `df_15m` parameter — call will fail with `TypeError`.

- [ ] **Step 2.3: Add `df_15m` parameter to `_advance_setup_state_tick`**

In `engine/safe_orchestrator.py`, find `_advance_setup_state_tick` (around line 1028). Modify the signature and the `confirm_entry` call:

**BEFORE:**
```python
    def _advance_setup_state_tick(
        self,
        symbol: str,
        current_price: float,
        current_bar_ts: int,
        pullback_timeout_bars: int = 8,
    ) -> None:
        """Advance pending SMC v2 setup candidates for `symbol` by one tick.
        ...
        """
        if self.setup_state_store is None:
            return

        from engine.smc_v2.zones import is_price_in_zone
        from engine.smc_v2.setup_state import PERSISTED_STATES

        for cand in self.setup_state_store.candidates:
            ...
            if cand.state == "IN_ZONE":
                confirmed, entry_px = self.confirm_entry(
                    df_15m=None,  # PR #S3 will pass the real DataFrame
                    zone=cand.target_zone,
                    direction=cand.direction,
                    since_ts=cand.trigger_bar_ts,
                )
                ...
```

**AFTER:**
```python
    def _advance_setup_state_tick(
        self,
        symbol: str,
        current_price: float,
        current_bar_ts: int,
        pullback_timeout_bars: int = 8,
        df_15m=None,
    ) -> None:
        """Advance pending SMC v2 setup candidates for `symbol` by one tick.

        Args:
            symbol: trading pair
            current_price: latest LTF (15m) close
            current_bar_ts: latest LTF bar's ms-epoch timestamp
            pullback_timeout_bars: max bars to wait for pullback (default 8 per spec §4.3)
            df_15m: optional LTF DataFrame for confirmation lookup. Required
                for IN_ZONE → CONFIRMED transition; if None, confirm_entry
                returns (False, None) (no transition). PR #S3b passes
                df_entry from run_cycle; tests may omit it.
        """
        if self.setup_state_store is None:
            return

        from engine.smc_v2.zones import is_price_in_zone
        from engine.smc_v2.setup_state import PERSISTED_STATES

        for cand in self.setup_state_store.candidates:
            if cand.symbol != symbol:
                continue
            if cand.state not in PERSISTED_STATES:
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
                # Skip confirmation when df_15m not provided (test paths
                # that only exercise the state machine, not the real
                # confirmation logic). Real run_cycle always passes df_entry.
                if df_15m is None:
                    continue
                confirmed, entry_px = self.confirm_entry(
                    df_15m=df_15m,
                    zone=cand.target_zone,
                    direction=cand.direction,
                    since_ts=cand.trigger_bar_ts,
                )
                if confirmed:
                    cand.state = "CONFIRMED"
                    # Entry order placement lands in PR #S3c
                    # (signals.py → OrderManager.open_position dispatch)
```

- [ ] **Step 2.4: Update PR #67's run_cycle call to pass df_entry**

In `engine/safe_orchestrator.py`, find the `_advance_setup_state_tick` call in `run_cycle` (around line 522-530):

**BEFORE:**
```python
        if self.setup_state_store is not None:
            current_bar_ts = int(df_entry.index[-1].timestamp() * 1000)
            self._advance_setup_state_tick(
                symbol=symbol,
                current_price=current_price,
                current_bar_ts=current_bar_ts,
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
```

- [ ] **Step 2.5: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_confirm_wiring.py::TestAdvanceWithRealConfirmation -v
# Expected: 2 passed
```

- [ ] **Step 2.6: Critical regression — PR #67 state-tick tests must still pass**

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py -v
# Expected: 17 passed
```

PR #67's `_advance_setup_state_tick` tests don't pass `df_15m` → the new `df_15m is None: continue` branch handles this gracefully (IN_ZONE candidates stay IN_ZONE without confirmation). The PR #67 test `test_in_zone_calls_confirm_entry` uses `patch.object(orc, "confirm_entry")` so it's still tested directly.

Wait — that test asserts `spy.call_count == 1`. But with `df_15m=None` we now SKIP the call. **This test will break.**

Let me re-check Step 2.3. The new `if df_15m is None: continue` clause means PR #67's spy test won't see the confirm_entry call. **This is a regression.**

**Fix**: PR #67's test was designed assuming confirm_entry would always be called. Now that we have df_15m gating, the test needs to either:
- (a) Pass a real df_15m, or
- (b) Be updated to expect the skip behavior

Option (b) is correct because the test was for the placeholder; now that the real impl needs df_15m, the test's contract changes.

**Updated Step 2.6:**

The PR #67 test `test_in_zone_calls_confirm_entry` (in `test_orchestrator_state_tick.py`) needs updating. Inspect it:

```bash
grep -n "test_in_zone_calls_confirm_entry" backend/tests/smc_v2/test_orchestrator_state_tick.py
```

Find the test and update it to pass `df_15m`:

```python
    def test_in_zone_calls_confirm_entry(
        self, minimal_config, tmp_path, store_with_pending
    ):
        """When state advances to IN_ZONE, confirm_entry is called.
        The stub returns (False, None) so state stays IN_ZONE."""
        import pandas as pd
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store_with_pending,
        )
        # Patch confirm_entry to spy on the call
        with patch.object(orc, "confirm_entry", return_value=(False, None)) as spy:
            # Provide a non-None df_15m so the new df_15m-None skip doesn't trigger
            fake_df = pd.DataFrame(
                {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]},
                index=pd.to_datetime([1_700_000_060_000], unit="ms", utc=True),
            )
            orc._advance_setup_state_tick(
                symbol="BTC/USDT", current_price=96500.0,
                current_bar_ts=1700000060000, df_15m=fake_df,
            )
            assert spy.call_count == 1
            call_kwargs = spy.call_args.kwargs
            assert call_kwargs["direction"] == "SHORT"
            assert call_kwargs["since_ts"] == 1700000000000
        assert store_with_pending.candidates[0].state == "IN_ZONE"
```

Run to verify:

```bash
python -m pytest backend/tests/smc_v2/test_orchestrator_state_tick.py::TestAdvanceSetupStateTick -v
# Expected: 8 passed (test_in_zone_calls_confirm_entry updated to pass df_15m)
```

- [ ] **Step 2.7: Full smc_v2 + v1 orchestrator regression**

```bash
python -m pytest backend/tests/smc_v2/ -q
# Expected: 99 (baseline) + 5 (new test_orchestrator_confirm_wiring tests) = 104 passed

python -m pytest backend/tests/test_orchestrator_order_bridge.py backend/tests/test_safe_orchestrator_client_attr.py backend/tests/test_safe_orchestrator_flags.py -q
# Expected: 12 passed (v1 path untouched)
```

- [ ] **Step 2.8: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/smc_v2/test_orchestrator_state_tick.py backend/tests/smc_v2/test_orchestrator_confirm_wiring.py
git commit -m "feat(orchestrator): plumb df_15m through advance_setup_state_tick

Add df_15m parameter (default None) to _advance_setup_state_tick.
run_cycle now passes df_entry as df_15m. When df_15m is None, the
IN_ZONE → confirm_entry call is SKIPPED (test paths that exercise
only the state machine remain valid).

PR #67 test_in_zone_calls_confirm_entry updated to pass a fake
df_15m so the spy assertion still holds.

v1 regression: 12 v1 orchestrator tests green. PR #67 state-tick
tests still 17 green (one test updated to pass df_15m).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3: Final regression sweep

### Task 3: Whole-suite + py_compile

- [ ] **Step 3.1: Full smc_v2 suite**

```bash
python -m pytest backend/tests/smc_v2/ -v 2>&1 | tail -8
# Expected: 99 baseline + 5 new = 104 passed
```

- [ ] **Step 3.2: Full backend suite**

```bash
python -m pytest backend/tests/ -q 2>&1 | tail -3
# Expected: previous baseline + 5 new
```

- [ ] **Step 3.3: py_compile**

```bash
python -m py_compile engine/safe_orchestrator.py && echo "compile OK"
```

- [ ] **Step 3.4: Diff inventory**

```bash
git log feat/smc-v2-trigger-integration ^master --oneline
git diff master..HEAD --stat
# Expected: 3 commits (1 plan + 2 task), only engine/safe_orchestrator.py + 2 test files + plan
```

---

## Out of Scope (explicitly NOT in PR #S3b)

- **Trigger phase** (new CHoCH → SetupCandidate emission) — PR #S3c
- **Feature flag dispatch** (`engine.smc_version`) — PR #S6
- **Entry order placement** when CONFIRMED — PR #S3c
- **select_htf_swing_anchor wiring** in trigger phase — PR #S3c
- **build_pullback_zones wiring** in trigger phase — PR #S3c

---

## Acceptance Criteria

1. All steps in Tasks 1-3 checked off.
2. `pytest backend/tests/smc_v2/test_orchestrator_confirm_wiring.py -v` → 5 passed
3. `pytest backend/tests/smc_v2/test_orchestrator_state_tick.py -v` → 17 passed (PR #67 regression intact)
4. `pytest backend/tests/test_orchestrator_*.py -q` → 12 passed (v1 regression)
5. `pytest backend/tests/smc_v2/ -q` → 104 passed (99 + 5)
6. `git diff master..HEAD --stat` → only `engine/safe_orchestrator.py` + 2 test files + plan
7. `efloud-code-reviewer` + risk-ops second pass APPROVED (CLAUDE.md §4 — safe_orchestrator.py is risk-sensitive)

---

## References

- Spec: `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §4.1, §4.3
- Real confirm_entry: `engine/smc_v2/confirmation.py` (PR #68)
- PR #67 base: `_advance_setup_state_tick` and `confirm_entry` placeholder
- Initiative tracker: `memory/smc_v2_rework_initiative.md`
