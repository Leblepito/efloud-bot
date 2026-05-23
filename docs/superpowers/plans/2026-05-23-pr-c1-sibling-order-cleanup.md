# PR #C1: Sibling Order Cleanup on Reconcile-Detected Full Close — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the reconcile loop detects a position fully closed on Binance (size → 0), cancel all sibling reduceOnly orders (SL + TP1 + TP2) so they do not orphan on the exchange's Open Orders list.

**Architecture:** Extract a DRY helper `OrderManager._cancel_position_siblings(pos, ccxt_sym, reason)` that best-effort iterates all three sibling order IDs and cancels each (CCXT `cancel_order`). Call the helper from (1) the reconcile loop full-close branch and (2) `_fallback_close` (replacing its existing inline loop). Leave `_move_sl_to_breakeven` untouched in two-target mode; in single-target mode (`pos.tp2 is None`, introduced by SMC v2 spec §4.2 — not implemented yet in this PR), the eventual TP1-fill caller will use the new helper instead — but **this PR ships only the cleanup helper + reconcile wiring + fallback_close DRY refactor**. The single-target lifecycle change is out of scope for PR #C1.

**Tech Stack:** Python 3.12, pytest, unittest.mock, ccxt. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §7 (Sibling Order Cleanup Fix). The spec lives on the `feat/smc-v2-spec` branch and is not yet merged to master; this worktree was branched from master so the spec file is not present locally. To read it, run `git show feat/smc-v2-spec:docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md`.

**Branch:** `fix/cleanup-orphan-reduceonly-orders` (worktree at `.worktrees/cleanup-orphan-orders`)

**Risk classification:** **Risk-ops sensitive** — this PR touches `exchange/__init__.py` (`OrderManager`). Per CLAUDE.md §4, `efloud-risk-ops-reviewer` agent is REQUIRED before merge.

---

## Pre-flight Checks

- [ ] **P1:** Confirm working directory is the worktree, not main repo.

```bash
git rev-parse --show-toplevel
# Expected: .../efloud-bot/.worktrees/cleanup-orphan-orders
git branch --show-current
# Expected: fix/cleanup-orphan-reduceonly-orders
```

- [ ] **P2:** Confirm baseline tests pass.

```bash
python -m pytest backend/tests/test_order_manager_v2.py -x --tb=short
# Expected: 14 passed
```

- [ ] **P3:** Confirm production code paths exist where the plan expects them.

```bash
python -m pytest --collect-only backend/tests/test_order_manager_v2.py 2>&1 | head -5
```

Quick spot-check of file:line references the plan will edit:

- `exchange/__init__.py:659-668` — reconcile full-close branch
- `exchange/__init__.py:842-848` — `_fallback_close` inline cancel loop
- `exchange/__init__.py:686-710` — `_move_sl_to_breakeven` (NOT modified by this PR)

If any of these have drifted from the spec's references, stop and re-read the file to find current line numbers before continuing.

---

## File Structure

**Created files:**
- `backend/tests/test_sibling_cleanup.py` — new test file dedicated to the helper + reconcile-cleanup behavior

**Modified files:**
- `exchange/__init__.py` — add `_cancel_position_siblings(pos, ccxt_sym, reason)` method on `OrderManager`; call from reconcile full-close branch; refactor `_fallback_close` to use the helper

**No schema changes, no config changes, no migrations.**

**File responsibility boundaries:**
- `_cancel_position_siblings` is the **only** place that knows the canonical order of attempted cancellations (SL, TP1, TP2) and the best-effort exception-swallowing policy. Every other code path that closes a position MUST call this helper instead of looping locally.

---

## Task Decomposition

### Task 1: Add the cleanup helper method (TDD red)

**Files:**
- Modify: `exchange/__init__.py` — add new method on `OrderManager` class (around `_move_sl_to_breakeven`)
- Create: `backend/tests/test_sibling_cleanup.py`

- [ ] **Step 1.1: Write the first failing test for the helper**

Create `backend/tests/test_sibling_cleanup.py` with:

```python
"""Unit tests for OrderManager._cancel_position_siblings — orphan order cleanup helper."""
from unittest.mock import MagicMock
import ccxt
import pytest

from exchange import BinanceClient, OrderManager, Position


@pytest.fixture
def mock_client():
    """Mock BinanceClient with stubbed exchange + helpers.

    Mirrors test_order_manager_v2.py fixture to keep test infrastructure consistent.
    """
    client = MagicMock(spec=BinanceClient)
    client.exchange = MagicMock()
    client.market_type = "futures"
    client.testnet = True
    client.to_ccxt_symbol.side_effect = lambda s: (
        s if ":" in s or client.market_type != "futures" else f"{s}:USDT"
    )
    return client


@pytest.fixture
def mgr(mock_client):
    return OrderManager(mock_client, dry_run=False)


@pytest.fixture
def position_with_all_orders():
    """A typical Position with all three sibling order IDs populated."""
    return Position(
        symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
        tp1=96000, tp2=97000, size=1.0,
        sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
    )


class TestCancelPositionSiblings:
    """The helper must best-effort cancel SL + TP1 + TP2 reduceOnly orders.

    Behavior contract (spec §7.1):
    - Iterate [SL, TP1, TP2] in order; cancel each via ccxt cancel_order
    - Swallow ccxt.OrderNotFound (order already gone); count as 'missing'
    - Log + count other exceptions as 'failed'; never propagate
    - Return summary dict {cancelled: [...], failed: [...], missing: [...]}
    - Always log a single info line summarizing the result
    """

    def test_cancels_all_three_orders_when_present(
        self, mgr, mock_client, position_with_all_orders
    ):
        result = mgr._cancel_position_siblings(
            position_with_all_orders, "BTC/USDT:USDT", reason="TEST"
        )

        # All three cancel_order calls with the futures notation symbol
        assert mock_client.exchange.cancel_order.call_count == 3
        calls = mock_client.exchange.cancel_order.call_args_list
        assert calls[0].args == ("SL-1", "BTC/USDT:USDT")
        assert calls[1].args == ("TP1-1", "BTC/USDT:USDT")
        assert calls[2].args == ("TP2-1", "BTC/USDT:USDT")

        assert sorted(result["cancelled"]) == ["SL", "TP1", "TP2"]
        assert result["failed"] == []
        assert result["missing"] == []
```

- [ ] **Step 1.2: Run the test to verify it fails**

```bash
python -m pytest backend/tests/test_sibling_cleanup.py::TestCancelPositionSiblings::test_cancels_all_three_orders_when_present -v
```

Expected: FAIL with `AttributeError: 'OrderManager' object has no attribute '_cancel_position_siblings'`

- [ ] **Step 1.3: Implement the minimal helper**

In `exchange/__init__.py`, find `_move_sl_to_breakeven` (around line 686). Add the new method **immediately before** it (so closely-related cleanup logic lives together):

```python
def _cancel_position_siblings(
    self,
    pos: "Position",
    ccxt_sym: str,
    reason: str,
) -> dict:
    """Best-effort cancel SL + TP1 + TP2 reduceOnly orders for a position.

    Called from every full-close path (reconcile, fallback, kill switch).
    Each cancel is independent: failure of one does not block the others.

    Args:
        pos: the Position whose sibling orders should be cancelled
        ccxt_sym: CCXT futures symbol form (e.g. 'BTC/USDT:USDT')
        reason: short tag for the log line (e.g. 'RECONCILED', 'FALLBACK_CLOSE')

    Returns:
        dict with keys 'cancelled', 'failed', 'missing' — each a list of
        labels ('SL', 'TP1', 'TP2'). Useful for assertions and telemetry.
    """
    # `ccxt` is already imported at module scope (exchange/__init__.py:3)
    result = {"cancelled": [], "failed": [], "missing": []}
    for label, oid in [
        ("SL", pos.sl_order_id),
        ("TP1", pos.tp1_order_id),
        ("TP2", pos.tp2_order_id),
    ]:
        if not oid:
            result["missing"].append(label)
            continue
        try:
            self.client.exchange.cancel_order(oid, ccxt_sym)
            result["cancelled"].append(label)
        except ccxt.OrderNotFound:
            result["missing"].append(label)
        except Exception as e:
            log.warning(
                f"[cleanup] {pos.symbol}: failed to cancel {label} ({oid}): {e}"
            )
            result["failed"].append(label)
    cancelled_str = "+".join(result["cancelled"]) or "none"
    log.info(
        f"[cleanup] {pos.symbol}: cancelled {cancelled_str} (reason={reason})"
    )
    return result
```

- [ ] **Step 1.4: Run the test to verify it passes**

```bash
python -m pytest backend/tests/test_sibling_cleanup.py::TestCancelPositionSiblings::test_cancels_all_three_orders_when_present -v
```

Expected: PASS

- [ ] **Step 1.5: Commit**

```bash
git add backend/tests/test_sibling_cleanup.py exchange/__init__.py
git commit -m "feat(exchange): add _cancel_position_siblings cleanup helper

Best-effort cancellation of SL + TP1 + TP2 reduceOnly orders.
Used by every full-close path. Swallows OrderNotFound (already
gone) and logs other failures without propagating.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Helper handles missing order IDs

**Files:**
- Modify: `backend/tests/test_sibling_cleanup.py` (extend `TestCancelPositionSiblings`)

- [ ] **Step 2.1: Write the failing test**

Append to `TestCancelPositionSiblings` class:

```python
    def test_skips_empty_order_ids(self, mgr, mock_client):
        """A Position with only SL+TP1 (no TP2) should only attempt 2 cancels."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="",
        )

        result = mgr._cancel_position_siblings(pos, "BTC/USDT:USDT", reason="TEST")

        # Only 2 cancel_order calls
        assert mock_client.exchange.cancel_order.call_count == 2
        assert sorted(result["cancelled"]) == ["SL", "TP1"]
        assert result["missing"] == ["TP2"]
        assert result["failed"] == []

    def test_all_missing_when_no_order_ids(self, mgr, mock_client):
        """A bare Position with no order IDs results in 0 cancel calls."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
        )

        result = mgr._cancel_position_siblings(pos, "BTC/USDT:USDT", reason="TEST")

        assert mock_client.exchange.cancel_order.call_count == 0
        assert result["cancelled"] == []
        assert result["failed"] == []
        assert sorted(result["missing"]) == ["SL", "TP1", "TP2"]
```

- [ ] **Step 2.2: Run tests — should already pass (helper handles this)**

```bash
python -m pytest backend/tests/test_sibling_cleanup.py::TestCancelPositionSiblings -v
```

Expected: 3 passed (existing + 2 new)

- [ ] **Step 2.3: Commit**

```bash
git add backend/tests/test_sibling_cleanup.py
git commit -m "test(exchange): cover empty order ID paths in _cancel_position_siblings

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Helper handles `OrderNotFound` (already-cancelled order)

**Files:**
- Modify: `backend/tests/test_sibling_cleanup.py`

- [ ] **Step 3.1: Write the failing test**

```python
    def test_swallows_order_not_found(
        self, mgr, mock_client, position_with_all_orders
    ):
        """If an order was already cancelled or filled, OrderNotFound must be silent."""
        # SL cancel succeeds; TP1 raises OrderNotFound; TP2 succeeds
        mock_client.exchange.cancel_order.side_effect = [
            None,
            ccxt.OrderNotFound("Order does not exist"),
            None,
        ]

        result = mgr._cancel_position_siblings(
            position_with_all_orders, "BTC/USDT:USDT", reason="TEST"
        )

        assert mock_client.exchange.cancel_order.call_count == 3
        assert sorted(result["cancelled"]) == ["SL", "TP2"]
        assert result["missing"] == ["TP1"]
        assert result["failed"] == []
```

- [ ] **Step 3.2: Run — should pass (helper already handles OrderNotFound)**

```bash
python -m pytest backend/tests/test_sibling_cleanup.py::TestCancelPositionSiblings -v
```

Expected: 4 passed

- [ ] **Step 3.3: Commit**

```bash
git add backend/tests/test_sibling_cleanup.py
git commit -m "test(exchange): assert OrderNotFound counted as missing not failed

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Helper handles generic exceptions (network errors, exchange errors)

**Files:**
- Modify: `backend/tests/test_sibling_cleanup.py`

- [ ] **Step 4.1: Write the failing test**

```python
    def test_logs_and_continues_on_generic_exception(
        self, mgr, mock_client, position_with_all_orders, caplog
    ):
        """Network/exchange errors on one cancel must not block the others."""
        import logging
        # SL succeeds; TP1 raises NetworkError; TP2 succeeds
        mock_client.exchange.cancel_order.side_effect = [
            None,
            ccxt.NetworkError("Connection reset"),
            None,
        ]

        with caplog.at_level(logging.WARNING):
            result = mgr._cancel_position_siblings(
                position_with_all_orders, "BTC/USDT:USDT", reason="TEST"
            )

        assert mock_client.exchange.cancel_order.call_count == 3
        assert sorted(result["cancelled"]) == ["SL", "TP2"]
        assert result["failed"] == ["TP1"]
        # Warning logged for the failed cancel
        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("failed to cancel TP1" in m for m in warning_msgs)
```

- [ ] **Step 4.2: Run — should pass**

```bash
python -m pytest backend/tests/test_sibling_cleanup.py::TestCancelPositionSiblings -v
```

Expected: 5 passed

- [ ] **Step 4.3: Commit**

```bash
git add backend/tests/test_sibling_cleanup.py
git commit -m "test(exchange): assert generic exceptions logged and counted as failed

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Wire helper into the reconcile loop full-close branch

This is the **load-bearing behavioral change** that fixes the orphan-orders bug.

**Files:**
- Modify: `exchange/__init__.py:659-668` — reconcile full-close branch
- Modify: `backend/tests/test_sibling_cleanup.py` — new `TestReconcileFullClose` class

- [ ] **Step 5.1: Write the failing integration test**

Append to `backend/tests/test_sibling_cleanup.py`:

```python
class TestReconcileFullClose:
    """When reconcile detects a position closed on Binance (size==0),
    it MUST cancel the sibling SL/TP orders before removing the
    local Position from state.

    Before this PR, reconcile silently removed the Position and left
    orphan reduceOnly orders on Binance Open Orders.
    """

    def test_full_close_cancels_all_siblings(self, mgr, mock_client):
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        # Exchange returns no open positions (fully closed)
        mock_client.get_open_positions.return_value = []
        # Open orders list also reflects the close (TP2 was the trigger)
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "SL-1"},
            {"id": "TP1-1"},
        ]

        closed = mgr.reconcile()

        # Position recorded closed
        assert len(closed) == 1
        assert closed[0].symbol == "BTC/USDT"
        assert pos not in mgr.positions

        # All 3 sibling cancels attempted
        cancel_calls = mock_client.exchange.cancel_order.call_args_list
        cancelled_ids = [c.args[0] for c in cancel_calls]
        assert "SL-1" in cancelled_ids
        assert "TP1-1" in cancelled_ids
        assert "TP2-1" in cancelled_ids
        # Symbol is in CCXT futures notation
        for c in cancel_calls:
            assert c.args[1] == "BTC/USDT:USDT"

    def test_partial_close_does_not_trigger_cleanup(self, mgr, mock_client):
        """If position is still open on Binance (size > 0), no sibling cancels."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        # Still open with original size
        mock_client.get_open_positions.return_value = [
            {"symbol": "BTC/USDT", "contracts": 1.0}
        ]
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "SL-1"}, {"id": "TP1-1"}, {"id": "TP2-1"},
        ]

        closed = mgr.reconcile()

        assert closed == []
        # No cancel_order calls
        assert mock_client.exchange.cancel_order.call_count == 0

    def test_full_close_with_already_cancelled_orders_does_not_propagate(
        self, mgr, mock_client
    ):
        """Even if every sibling cancel raises OrderNotFound, reconcile completes."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        mock_client.get_open_positions.return_value = []
        mock_client.exchange.fetch_open_orders.return_value = []
        # Every cancel raises OrderNotFound (already gone)
        mock_client.exchange.cancel_order.side_effect = ccxt.OrderNotFound(
            "Order does not exist"
        )

        closed = mgr.reconcile()  # MUST NOT raise

        assert len(closed) == 1
        assert pos not in mgr.positions
        # Attempted to cancel all 3
        assert mock_client.exchange.cancel_order.call_count == 3

    def test_full_close_in_dry_run_does_not_cancel_orders(self, mock_client):
        """Dry-run mode must not place any cancel_order calls — paper trading
        invariant. Mirrors existing _fallback_close and _move_sl_to_breakeven
        dry-run guards.
        """
        mgr_dry = OrderManager(mock_client, dry_run=True)
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr_dry.positions = [pos]
        mock_client.get_open_positions.return_value = []
        mock_client.exchange.fetch_open_orders.return_value = []

        closed = mgr_dry.reconcile()

        assert len(closed) == 1
        assert pos not in mgr_dry.positions
        # Zero cancel calls in dry-run
        assert mock_client.exchange.cancel_order.call_count == 0
```

- [ ] **Step 5.2: Run the test to verify it fails**

```bash
python -m pytest backend/tests/test_sibling_cleanup.py::TestReconcileFullClose -v
```

Expected: 3 FAIL — `cancel_order` not called (the bug).

- [ ] **Step 5.3: Wire the helper into the reconcile loop**

In `exchange/__init__.py`, find the reconcile full-close branch at lines 659-668. Modify the inner block:

**BEFORE:**

```python
for pos in self.positions[:]:
    if pos.symbol not in bn_open_symbols:
        # Pozisyon Binance'de kapanmış — TP2 / SL / manual close
        exit_price = self._estimate_exit_price(pos, bn_orders_raw)
        self._record_close(pos, exit_price, reason="RECONCILED")
        closed_now.append(pos)
        self.positions.remove(pos)
        continue
```

**AFTER:**

```python
for pos in self.positions[:]:
    if pos.symbol not in bn_open_symbols:
        # Pozisyon Binance'de kapanmış — TP2 / SL / manual close
        # IMPORTANT: _estimate_exit_price MUST run before _cancel_position_siblings.
        # The exit price inference relies on which order ID is missing from
        # bn_orders_raw to attribute the trigger (TP1/TP2/SL). Cancelling first
        # would invalidate that signal.
        exit_price = self._estimate_exit_price(pos, bn_orders_raw)
        # Cancel orphan sibling reduceOnly orders before dropping local state
        if not self.dry_run:
            ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)
            self._cancel_position_siblings(pos, ccxt_sym, reason="RECONCILED")
        self._record_close(pos, exit_price, reason="RECONCILED")
        closed_now.append(pos)
        self.positions.remove(pos)
        continue
```

The `if not self.dry_run` guard matches the existing `_move_sl_to_breakeven` and `_fallback_close` patterns (no exchange calls in dry mode).

- [ ] **Step 5.4: Run the test to verify it passes**

```bash
python -m pytest backend/tests/test_sibling_cleanup.py::TestReconcileFullClose -v
```

Expected: 3 PASS

- [ ] **Step 5.5: Run the full existing test file to verify no regression**

```bash
python -m pytest backend/tests/test_order_manager_v2.py -v
```

Expected: 14 passed (unchanged baseline)

- [ ] **Step 5.6: Commit**

```bash
git add exchange/__init__.py backend/tests/test_sibling_cleanup.py
git commit -m "fix(exchange): cancel sibling reduceOnly orders on reconcile-detected close

Before this commit, when the reconcile loop detected a position
had closed on Binance (TP1/TP2/SL filled or manual close),
it removed the local Position but left the remaining SL/TP
reduceOnly orders open on the exchange forever.

Now reconcile calls _cancel_position_siblings before dropping
the position from local state, matching the pattern already used
by _fallback_close.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: DRY refactor — `_fallback_close` uses the helper

`_fallback_close` already does the right cleanup with an inline loop. After this refactor, the helper becomes the **single source of truth** for sibling cancellation logic.

**Files:**
- Modify: `exchange/__init__.py:842-848` — `_fallback_close` inline cancel loop

- [ ] **Step 6.1: Add a regression test for `_fallback_close` cleanup behavior**

This guards the refactor — current behavior must remain identical.

Append to `backend/tests/test_sibling_cleanup.py`:

```python
class TestFallbackCloseRefactor:
    """_fallback_close must continue to cancel all siblings after the
    refactor that replaces its inline loop with the new helper.

    This test pins the behavior so the refactor cannot silently change it.
    """

    def test_fallback_close_cancels_all_siblings(self, mgr, mock_client):
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        # Market close succeeds
        mock_client.exchange.create_order.return_value = {"id": "CLOSE-1"}

        mgr._fallback_close(pos, price=94500, reason="SL_POLL")

        # Position removed
        assert pos not in mgr.positions

        # Market close was placed
        market_calls = [
            c for c in mock_client.exchange.create_order.call_args_list
            if c.args[1] == "market"
        ]
        assert len(market_calls) == 1

        # All 3 sibling cancels attempted
        cancel_calls = mock_client.exchange.cancel_order.call_args_list
        cancelled_ids = [c.args[0] for c in cancel_calls]
        assert sorted(cancelled_ids) == ["SL-1", "TP1-1", "TP2-1"]
```

- [ ] **Step 6.2: Run — should pass (current inline loop already does this)**

```bash
python -m pytest backend/tests/test_sibling_cleanup.py::TestFallbackCloseRefactor -v
```

Expected: 1 PASS

- [ ] **Step 6.3: Refactor `_fallback_close` to use the helper**

In `exchange/__init__.py`, find `_fallback_close` (line 830 area). Modify the cleanup block:

**BEFORE (lines 842-848):**

```python
        # Pending order cleanup
        for oid in [pos.sl_order_id, pos.tp1_order_id, pos.tp2_order_id]:
            if oid:
                try:
                    self.client.exchange.cancel_order(oid, ccxt_sym)
                except Exception:
                    pass
```

**AFTER:**

```python
        # Pending order cleanup — DRY via shared helper
        self._cancel_position_siblings(pos, ccxt_sym, reason=f"FALLBACK_{reason}")
```

The `reason` parameter now combines the fallback context with the original trigger reason ("FALLBACK_SL_POLL", "FALLBACK_TP2_POLL", "FALLBACK_KILL_SWITCH") for log clarity.

- [ ] **Step 6.4: Run the regression test — must still pass**

```bash
python -m pytest backend/tests/test_sibling_cleanup.py::TestFallbackCloseRefactor -v
```

Expected: 1 PASS (same assertions, different implementation under the hood)

- [ ] **Step 6.5: Run all tests to verify no regression**

```bash
python -m pytest backend/tests/test_order_manager_v2.py backend/tests/test_sibling_cleanup.py -v
```

Expected: 14 + 10 = 24 passed

- [ ] **Step 6.6: Commit**

```bash
git add exchange/__init__.py backend/tests/test_sibling_cleanup.py
git commit -m "refactor(exchange): _fallback_close uses _cancel_position_siblings helper

DRY — single source of truth for sibling order cancellation logic.
Reason tag combines fallback context with trigger reason
(e.g. 'FALLBACK_SL_POLL', 'FALLBACK_TP2_POLL', 'FALLBACK_KILL_SWITCH').

Observable log change: the new [cleanup] info line uses the combined
reason format. The existing _record_close log line still uses the bare
reason ('SL_POLL', etc.), so downstream greps that key off the bare
reason are unaffected. Log consumers that scan cancel_order activity
by reason should be updated to recognize the FALLBACK_ prefix.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Whole-suite regression sweep

- [ ] **Step 7.1: Run the entire backend test suite**

```bash
python -m pytest backend/tests/ -q --tb=short 2>&1 | tail -40
```

Expected: all green. If anything is red that was green before this PR started, stop and investigate before continuing.

- [ ] **Step 7.2: Run any orphan-related test files to confirm we did not break neighboring concerns**

```bash
python -m pytest backend/tests/test_orphan_protection.py backend/tests/test_order_manager_atomicity.py -v --tb=short
```

Expected: all green (these tests pre-exist; they should not be affected).

- [ ] **Step 7.3: Type-check / lint smoke (if configured)**

```bash
python -m py_compile exchange/__init__.py backend/tests/test_sibling_cleanup.py
```

Expected: no output (clean compile).

- [ ] **Step 7.4: Final commit if any uncommitted work**

If steps 7.1-7.3 produced no changes, skip. Otherwise, fix and commit.

---

## Out of Scope (explicitly NOT in PR #C1)

- **Single-target lifecycle change** (`pos.tp2 is None` → TP1 = full close): introduced by spec §4.2 for SMC v2. Requires `engine/lifecycle.py` and downstream changes. **Ships in PR #S5** along with the lifecycle telemetry fields.
- **`_move_sl_to_breakeven` refactor**: by design it only cancels SL (not TP2) in two-target mode. Single-target mode handling is part of PR #S5.
- **Telegram notification enrichment** (e.g. "cancelled X+Y+Z" in close notifications): spec §4.2 marks this as optional/preferred. Defer to PR #S5 alongside other telemetry.
- **Live testnet verification**: spec §7.4 says "Pre-deploy: testnet verification — open position, manually trigger SL, watch reconcile detect close, assert open-orders list is empty". This is a manual operator step (Hermes/Utku), not part of this code PR.

---

## Acceptance Criteria

PR #C1 is complete and ready for review when:

1. All steps in Tasks 1-7 are checked off.
2. `python -m pytest backend/tests/test_sibling_cleanup.py backend/tests/test_order_manager_v2.py -v` shows **all tests passing** (10 new + 14 existing = 24).
3. `python -m pytest backend/tests/ -q` shows the rest of the suite still green.
4. `git log fix/cleanup-orphan-reduceonly-orders ^master --oneline` shows 6 atomic commits (one per task that produced changes).
5. `git diff master fix/cleanup-orphan-reduceonly-orders -- exchange/__init__.py` shows **only** the new helper method + the reconcile-loop wiring + the `_fallback_close` refactor — no unrelated changes.
6. `efloud-risk-ops-reviewer` agent reviewed the diff (CLAUDE.md §4 requirement — `exchange/` is in the risk-sensitive set) and either APPROVED or its blocking concerns are resolved.

---

## Post-Plan Workflow

1. After implementation: invoke `superpowers:verification-before-completion` skill to gate the success claim.
2. Invoke `superpowers:requesting-code-review` skill → dispatch `efloud-risk-ops-reviewer` agent.
3. After review passes: invoke `superpowers:finishing-a-development-branch` skill to decide merge vs PR vs hold.
4. Update `memory/smc_v2_rework_initiative.md`'s "PR Status" section to mark PR #C1 done with the merge SHA.

---

## References

- Spec: `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §7
- Code map: `exchange/__init__.py` (`OrderManager` class lines 200-870)
- Test patterns: `backend/tests/test_order_manager_v2.py` (mock fixture, reconcile assertion style)
- CLAUDE.md §4 (atomic PR discipline), §7 (custom agents)
