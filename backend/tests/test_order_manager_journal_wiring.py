"""OrderManager ↔ TradeJournal wiring tests.

PR #51 wired the orchestrator side (engine.lifecycle.Position close hook),
which only fires on manual force-close — the rare path. The common path
(TP1/TP2/SL/RECONCILED) closes via OrderManager._record_close in
exchange/__init__.py. This PR adds journal wiring there so production
journal_rows > 0 includes the bulk of real closes.

OrderManager and SafeOrchestrator hold parallel Position state with
different trade_id surfaces; therefore the OrderManager hook writes a
FULL snapshot atomically (entry+exit in one go) instead of trying to
match an orchestrator-side trade_id.
"""
from unittest.mock import MagicMock
import pytest

from exchange import OrderManager, Position as ExchangePosition
from engine.journal import TradeJournal, TradeSnapshot


@pytest.fixture
def mock_client():
    """Lightweight stand-in for BinanceClient — OrderManager only touches
    `.exchange` and a few helpers in non-dry_run paths. _record_close
    itself doesn't touch the client at all, so a MagicMock is enough."""
    return MagicMock()


@pytest.fixture
def sample_position():
    return ExchangePosition(
        symbol="BTC/USDT",
        direction="LONG",
        entry=50000.0,
        sl=49500.0,
        tp1=50500.0,
        tp2=51000.0,
        size=0.01,
        order_id="bn-order-abc123",
        opened_at="2026-05-13T10:00:00+00:00",
    )


# ── 1. Constructor backwards-compat ────────────────────────────────────────

def test_order_manager_default_trade_journal_is_none(mock_client):
    """Without trade_journal kwarg, the attribute is None (backwards-compat
    for the 5 existing OrderManager(...) call sites that don't yet wire it)."""
    om = OrderManager(mock_client, dry_run=True)
    assert om.trade_journal is None


def test_order_manager_accepts_trade_journal_kwarg(mock_client, tmp_path):
    """trade_journal kwarg is stored on the OrderManager."""
    journal = TradeJournal(str(tmp_path / "tj.jsonl"))
    om = OrderManager(mock_client, dry_run=True, trade_journal=journal)
    assert om.trade_journal is journal


# ── 2. _record_close hook ──────────────────────────────────────────────────

def test_record_close_writes_full_snapshot_when_journal_present(mock_client, sample_position):
    """A single _record_close call must produce one fully-populated TradeSnapshot
    in the journal: entry fields from the position, exit fields from the close,
    realized_pnl matching the long-side math (exit-entry)*size."""
    mock_journal = MagicMock(spec=TradeJournal)
    om = OrderManager(mock_client, dry_run=True, trade_journal=mock_journal)

    om._record_close(sample_position, exit_price=50500.0, reason="TP1")

    # Entry recorded first (TradeJournal requires record_entry before record_exit).
    assert mock_journal.record_entry.called, "record_entry must be called"
    snap = mock_journal.record_entry.call_args[0][0]
    assert isinstance(snap, TradeSnapshot)
    assert snap.symbol == "BTC/USDT"
    assert snap.direction == "LONG"
    assert snap.entry_price == 50000.0
    assert snap.sl_initial == 49500.0
    assert snap.tp1_initial == 50500.0
    assert snap.tp2_initial == 51000.0
    assert snap.position_size == 0.01

    # Exit recorded with realized_pnl from exchange-side computation.
    assert mock_journal.record_exit.called, "record_exit must be called"
    call = mock_journal.record_exit.call_args
    kw = call.kwargs if call.kwargs else {}
    # Accept positional or kwargs style.
    if call.args:
        trade_id = call.args[0]
        exit_price = call.args[1]
        exit_reason = call.args[2]
        realized_pnl = call.args[3]
    else:
        trade_id = kw["trade_id"]
        exit_price = kw["exit_price"]
        exit_reason = kw["exit_reason"]
        realized_pnl = kw["realized_pnl"]
    # trade_id must match the snapshot's trade_id so record_exit can find it.
    assert trade_id == snap.trade_id
    assert exit_price == 50500.0
    assert exit_reason == "TP1"
    # LONG: (50500 - 50000) * 0.01 = 5.0
    assert realized_pnl == pytest.approx(5.0, rel=0.01)


def test_record_close_noop_when_journal_none(mock_client, sample_position):
    """When trade_journal is None, _record_close must not raise and must
    still update position close metadata (pos.exit_reason, pos.pnl_usdt)."""
    om = OrderManager(mock_client, dry_run=True)
    # Must not raise
    om._record_close(sample_position, exit_price=50500.0, reason="TP1")
    # Existing behavior preserved
    assert sample_position.exit_reason == "TP1"
    assert sample_position.exit_price == 50500.0
    assert sample_position.pnl_usdt == pytest.approx(5.0, rel=0.01)


def test_record_close_short_pnl_sign(mock_client):
    """SHORT realized_pnl must be (entry - exit) * size, positive on price drop."""
    pos = ExchangePosition(
        symbol="ETH/USDT", direction="SHORT",
        entry=2000.0, sl=2050.0, tp1=1980.0, tp2=1950.0,
        size=0.5, order_id="bn-eth-1",
    )
    mock_journal = MagicMock(spec=TradeJournal)
    om = OrderManager(mock_client, dry_run=True, trade_journal=mock_journal)

    om._record_close(pos, exit_price=1970.0, reason="TP2")

    call = mock_journal.record_exit.call_args
    if call.args:
        realized_pnl = call.args[3]
    else:
        realized_pnl = call.kwargs["realized_pnl"]
    # SHORT 2000 → 1970: (2000 - 1970) * 0.5 = 15.0
    assert realized_pnl == pytest.approx(15.0, rel=0.01)
