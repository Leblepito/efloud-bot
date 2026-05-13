"""OrderManager._record_close behavior when TradeJournal raises.

PR #56 wired TradeJournal into _record_close. The hook is wrapped in
try/except → a journal write failure must degrade to log.warning and
NEVER break the close flow. The PR #56 code-review (efloud-code-reviewer
agent, 2026-05-13) flagged that this safety contract had no explicit
test — these two tests pin it.

Both tests verify that even when TradeJournal raises:
  - Existing close metadata (pos.exit_reason, pos.exit_price, pos.pnl_usdt)
    is still updated.
  - _emit("position_closed", pos) STILL fires (observers / WS push are
    not skipped).
"""
from unittest.mock import MagicMock
import pytest

from exchange import OrderManager, Position as ExchangePosition
from engine.journal import TradeJournal


@pytest.fixture
def mock_client():
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
        order_id="bn-order-failure-1",
        opened_at="2026-05-13T10:00:00+00:00",
    )


def test_record_close_completes_when_journal_record_entry_raises(mock_client, sample_position):
    """If TradeJournal.record_entry raises (e.g. disk full, JSONDecodeError
    on cache reload, or _cache state corruption), _record_close MUST:
      1. Still update pos.exit_reason, pos.exit_price, pos.pnl_usdt.
      2. Still fire the on_position_change('position_closed', pos) callback.
    """
    on_change = MagicMock()
    mock_journal = MagicMock(spec=TradeJournal)
    mock_journal.record_entry.side_effect = OSError("simulated journal write failure")

    om = OrderManager(
        mock_client, dry_run=True,
        on_position_change=on_change,
        trade_journal=mock_journal,
    )

    # Must not raise.
    om._record_close(sample_position, exit_price=50500.0, reason="TP1")

    # 1. Existing close metadata updated.
    assert sample_position.exit_reason == "TP1"
    assert sample_position.exit_price == 50500.0
    assert sample_position.pnl_usdt == pytest.approx(5.0, rel=0.01)

    # 2. _emit still fired position_closed exactly once.
    assert on_change.call_count == 1
    event, pos_arg = on_change.call_args[0]
    assert event == "position_closed"
    assert pos_arg is sample_position


def test_record_close_completes_when_journal_record_exit_raises(mock_client, sample_position):
    """If record_exit raises AFTER record_entry succeeded, _record_close
    MUST still complete and emit the callback. Same contract as above —
    the journal hook is observability, not a critical path."""
    on_change = MagicMock()
    mock_journal = MagicMock(spec=TradeJournal)
    mock_journal.record_entry.return_value = None   # entry OK
    mock_journal.record_exit.side_effect = RuntimeError("simulated exit write failure")

    om = OrderManager(
        mock_client, dry_run=True,
        on_position_change=on_change,
        trade_journal=mock_journal,
    )

    om._record_close(sample_position, exit_price=50500.0, reason="SL")

    assert sample_position.exit_reason == "SL"
    assert sample_position.exit_price == 50500.0
    # LONG: (exit - entry) * size; SL hit so price moved against, but math
    # still applies — for this test the sign isn't important, just that
    # pnl_usdt got set by the existing code path before the journal hook.
    assert sample_position.pnl_usdt == pytest.approx(5.0, rel=0.01)
    assert on_change.call_count == 1
    assert on_change.call_args[0][0] == "position_closed"


def test_record_close_completes_when_trade_snapshot_import_fails(mock_client, sample_position, monkeypatch):
    """Defense-in-depth: even if the lazy import of TradeSnapshot inside
    _journal_record_close were to fail (e.g. engine.journal removed at
    runtime), the close flow MUST still complete because the helper is
    wrapped in try/except."""
    on_change = MagicMock()
    mock_journal = MagicMock(spec=TradeJournal)

    om = OrderManager(
        mock_client, dry_run=True,
        on_position_change=on_change,
        trade_journal=mock_journal,
    )

    # Simulate an exception during snapshot construction — monkeypatch the
    # TradeSnapshot symbol in engine.journal so the import inside the
    # helper resolves to a callable that raises.
    import engine.journal
    def boom(*args, **kwargs):
        raise TypeError("simulated snapshot construction failure")
    monkeypatch.setattr(engine.journal, "TradeSnapshot", boom)

    om._record_close(sample_position, exit_price=50500.0, reason="TP2")

    assert sample_position.exit_reason == "TP2"
    assert sample_position.exit_price == 50500.0
    assert on_change.call_count == 1
