"""Task 6 — CLI (main.py) reconcile→breaker parity with the FastAPI daemon.

Background
----------
The FastAPI daemon (`backend/bot_runner.py::_run_loop`) calls
`order_mgr.reconcile()` BEFORE the scan/STEP5 pass, then flows each exchange-side
close into the CircuitBreaker via `_sync_reconciled_close_to_logical(pos)`
(single-count, deduped on the LOGICAL position's `_reported_to_breaker` flag —
the SAME source of truth STEP5 uses in engine/safe_orchestrator.py).

The CLI entrypoint (`main.py`) historically did NOT reconcile at all, so
exchange-side TP/SL closes never reached the breaker, orphan detection, or
TP1→BE in CLI mode (CLAUDE.md §5, 2026-05-28 wiring divergence).

This test exercises the extracted module-level helper
`main._cli_reconcile_sync(orch, order_mgr, cfg, log)` directly — genuine
regression protection on the production CLI code path. The dedup contract is
byte-equivalent to bot_runner's helper: record + flag live INSIDE the
`if logical is not None and not logical._reported_to_breaker` block.
"""
from dataclasses import dataclass, field
import logging
from unittest.mock import MagicMock


@dataclass
class FakeExchangePos:
    """Mirrors the exchange-side `exchange.Position` fields the helper reads."""
    symbol: str = "BTC/USDT"
    direction: str = "LONG"
    entry: float = 100.0
    exit_price: float = 95.0
    exit_reason: str = "SL"
    pnl_usdt: float = -5.0
    _reported_to_breaker: bool = field(default=False)


def _make_cfg(dry_run=False):
    return {"operation": {"dry_run": dry_run}}


def _make_orch(logical=None):
    orch = MagicMock()
    orch.lifecycle.same_direction_open.return_value = logical
    return orch


def test_main_run_cycle_reconciles_and_syncs_breaker():
    """One closed exchange Position + an OPEN logical match (flag False) →
    close_position + journal + breaker.record_trade called ONCE with the
    exchange-truth pnl, and the LOGICAL flag is set."""
    from main import _cli_reconcile_sync

    logical = MagicMock()
    logical._reported_to_breaker = False
    orch = _make_orch(logical=logical)
    pos = FakeExchangePos(symbol="ETH/USDT", direction="SHORT",
                          exit_price=2000.0, exit_reason="TP1", pnl_usdt=-5.0)
    order_mgr = MagicMock()
    order_mgr.reconcile.return_value = [pos]
    log = logging.getLogger("test.cli")

    _cli_reconcile_sync(orch, order_mgr, _make_cfg(dry_run=False), log)

    order_mgr.reconcile.assert_called_once()
    orch.lifecycle.close_position.assert_called_once_with(logical, 2000.0, "TP1")
    orch._journal_record_exit.assert_called_once_with(logical, 2000.0, "TP1")
    orch.breaker.record_trade.assert_called_once_with(-5.0)
    assert logical._reported_to_breaker is True


def test_main_run_cycle_no_double_count():
    """No open logical match (None — orphan / already closed by STEP5) →
    breaker.record_trade NOT called. Prevents cross-path double count."""
    from main import _cli_reconcile_sync

    orch = _make_orch(logical=None)
    pos = FakeExchangePos(pnl_usdt=-5.0)
    order_mgr = MagicMock()
    order_mgr.reconcile.return_value = [pos]
    log = logging.getLogger("test.cli")

    _cli_reconcile_sync(orch, order_mgr, _make_cfg(dry_run=False), log)

    order_mgr.reconcile.assert_called_once()
    orch.breaker.record_trade.assert_not_called()
    orch.lifecycle.close_position.assert_not_called()
    orch._journal_record_exit.assert_not_called()


def test_main_run_cycle_dry_run_skips_reconcile():
    """dry_run=True → reconcile() must NOT be called at all."""
    from main import _cli_reconcile_sync

    orch = _make_orch(logical=MagicMock())
    order_mgr = MagicMock()
    log = logging.getLogger("test.cli")

    _cli_reconcile_sync(orch, order_mgr, _make_cfg(dry_run=True), log)

    order_mgr.reconcile.assert_not_called()
    orch.breaker.record_trade.assert_not_called()


def test_main_run_cycle_no_order_mgr_skips():
    """order_mgr is None → no crash, reconcile path skipped entirely."""
    from main import _cli_reconcile_sync

    orch = _make_orch(logical=MagicMock())
    log = logging.getLogger("test.cli")

    _cli_reconcile_sync(orch, None, _make_cfg(dry_run=False), log)  # must not raise

    orch.breaker.record_trade.assert_not_called()


def test_main_run_cycle_already_reported_skips():
    """Logical match exists but already flagged (STEP5 same cycle) → neither
    close_position NOR record_trade called."""
    from main import _cli_reconcile_sync

    logical = MagicMock()
    logical._reported_to_breaker = True
    orch = _make_orch(logical=logical)
    pos = FakeExchangePos(pnl_usdt=-4.0)
    order_mgr = MagicMock()
    order_mgr.reconcile.return_value = [pos]
    log = logging.getLogger("test.cli")

    _cli_reconcile_sync(orch, order_mgr, _make_cfg(dry_run=False), log)

    orch.lifecycle.close_position.assert_not_called()
    orch._journal_record_exit.assert_not_called()
    orch.breaker.record_trade.assert_not_called()


def test_main_run_cycle_swallows_exceptions():
    """reconcile/close raising must NOT propagate — a sync failure must never
    kill the CLI cycle. Breaker not recorded (record is after close)."""
    from main import _cli_reconcile_sync

    logical = MagicMock()
    logical._reported_to_breaker = False
    orch = _make_orch(logical=logical)
    orch.lifecycle.close_position.side_effect = RuntimeError("close boom")
    pos = FakeExchangePos()
    order_mgr = MagicMock()
    order_mgr.reconcile.return_value = [pos]
    log = logging.getLogger("test.cli")

    _cli_reconcile_sync(orch, order_mgr, _make_cfg(dry_run=False), log)  # must not raise

    orch.breaker.record_trade.assert_not_called()
