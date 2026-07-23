"""Task 2 (Y2 fix): reconcile() exchange-side closes must flow into the
CircuitBreaker EXACTLY ONCE — no cross-path double count.

Background
----------
`BotRunner._run_loop` calls `order_mgr.reconcile()` (BEFORE `_scan_universe` /
STEP5) which detects exchange-side TP/SL fills and returns closed exchange-side
`Position` objects. `_persist_close` then calls
`_sync_reconciled_close_to_logical(pos)`.

The breaker is fed from TWO paths:
  * reconcile (this helper), and
  * safe_orchestrator STEP5 (engine/safe_orchestrator.py:741-746), which closes
    the LOGICAL position and sets `_reported_to_breaker` on the LOGICAL object.

Double-count bug (fixed here)
-----------------------------
The first version flagged the EXCHANGE object and called `breaker.record_trade`
UNCONDITIONALLY. STEP5 flags the LOGICAL object. Different objects → once STEP5
had already closed the logical pos, `same_direction_open` (open-only) returns
None, the helper skipped the logical close but STILL recorded the pnl → the same
economic close counted twice → breaker trips too early.

Fix: record + flag live INSIDE the `if logical is not None and not
logical._reported_to_breaker` block, keyed on the LOGICAL object's flag — the
SAME source of truth STEP5 uses. No open logical match → do NOT record.

Loop ordering makes this correct and lossless:
  * reconcile runs FIRST → logical still OPEN → record once + flag logical →
    STEP5 later sees the flag and skips. Single count, Y2 fixed.
  * STEP5 already closed+flagged (edge ordering) → same_direction_open returns
    None → helper skips record. No double count.
  * orphan/manual close (never a bot trade) → no logical → skipped (matches
    pre-Task-2 behavior).

Test approach
-------------
`BotRunner()` instantiates cleanly (no heavy deps; `orch` defaults to None), so
we bind the REAL method to a real `BotRunner` instance and drive it with a
mocked `orch`. Genuine regression protection on the production code path. The
"STEP5 already closed it" case is modeled by `same_direction_open` returning
None (what it does for a non-open logical pos).
"""
from dataclasses import dataclass, field
from unittest.mock import MagicMock

from backend.bot_runner import BotRunner


@dataclass
class FakeExchangePos:
    """Mirrors the exchange-side `exchange.Position` fields the helper reads."""
    symbol: str = "BTC/USDT"
    direction: str = "LONG"
    entry: float = 100.0
    exit_price: float = 95.0
    exit_reason: str = "SL"
    pnl_usdt: float = -12.5
    _reported_to_breaker: bool = field(default=False)


def _make_runner_with_orch(logical=None):
    """Real BotRunner + a mocked orch wired with breaker/lifecycle."""
    runner = BotRunner()
    orch = MagicMock()
    orch.lifecycle.same_direction_open.return_value = logical
    runner.orch = orch
    return runner, orch


def test_reconciled_close_records_pnl_when_logical_open():
    """An OPEN logical match (flag False) → close_position + journal + breaker
    recorded ONCE with the exchange-truth pnl, and the LOGICAL flag is set."""
    logical = MagicMock()
    logical._reported_to_breaker = False
    runner, orch = _make_runner_with_orch(logical=logical)
    pos = FakeExchangePos(symbol="ETH/USDT", direction="SHORT",
                          exit_price=2000.0, exit_reason="TP1", pnl_usdt=33.3)

    runner._sync_reconciled_close_to_logical(pos)

    orch.lifecycle.close_position.assert_called_once_with(logical, 2000.0, "TP1")
    orch._journal_record_exit.assert_called_once_with(logical, 2000.0, "TP1")
    orch.breaker.record_trade.assert_called_once_with(33.3)
    assert logical._reported_to_breaker is True


def test_no_record_when_no_logical_match():
    """No open logical match (None) → breaker.record_trade NOT called.

    CRITICAL: this is the orphan / already-closed-by-STEP5 case. Recording here
    would double-count the close (the original bug)."""
    runner, orch = _make_runner_with_orch(logical=None)
    pos = FakeExchangePos(pnl_usdt=-12.5)

    runner._sync_reconciled_close_to_logical(pos)

    orch.breaker.record_trade.assert_not_called()
    orch.lifecycle.close_position.assert_not_called()
    orch._journal_record_exit.assert_not_called()


def test_no_record_when_logical_already_reported():
    """Logical match exists but already flagged (STEP5 in same cycle) → neither
    close_position NOR record_trade called."""
    logical = MagicMock()
    logical._reported_to_breaker = True
    runner, orch = _make_runner_with_orch(logical=logical)
    pos = FakeExchangePos(pnl_usdt=-4.0)

    runner._sync_reconciled_close_to_logical(pos)

    orch.lifecycle.close_position.assert_not_called()
    orch._journal_record_exit.assert_not_called()
    orch.breaker.record_trade.assert_not_called()


def test_sync_noop_when_orch_none():
    """orch is None (early startup / stopped) → no crash, nothing recorded."""
    runner = BotRunner()
    assert runner.orch is None
    pos = FakeExchangePos()

    runner._sync_reconciled_close_to_logical(pos)  # must not raise


def test_sync_swallows_exceptions():
    """If close_position raises, the helper logs a warning and does NOT
    propagate — a sync failure must never kill the reconcile loop. The breaker
    is not recorded (record happens after close in the same block)."""
    logical = MagicMock()
    logical._reported_to_breaker = False
    runner, orch = _make_runner_with_orch(logical=logical)
    orch.lifecycle.close_position.side_effect = RuntimeError("close boom")
    pos = FakeExchangePos()

    runner._sync_reconciled_close_to_logical(pos)  # must not raise

    orch.breaker.record_trade.assert_not_called()


def test_cross_path_no_double_count():
    """Regression for the cross-path double-count bug.

    Scenario: STEP5 already closed the logical position earlier (so it is no
    longer OPEN). `same_direction_open` returns None for a non-open pos. The
    helper must NOT call breaker.record_trade — otherwise the same economic
    close is counted twice (once by STEP5, once by reconcile)."""
    runner, orch = _make_runner_with_orch(logical=None)  # closed → not open
    pos = FakeExchangePos(symbol="OP/USDT", direction="LONG",
                          exit_reason="SL", pnl_usdt=-9.0)

    runner._sync_reconciled_close_to_logical(pos)

    orch.breaker.record_trade.assert_not_called()
