"""SafeOrchestrator ↔ TradeJournal wiring tests.

Background: Phase 0 smoke (PR #48) showed journal_rows=0 in production.
Investigation (Hermes handoff Task C) confirmed Case C — TradeJournal
class exists but is never instantiated, and lifecycle hooks never call
record_entry / record_exit.

This file pins the minimum-viable wiring: orchestrator accepts an optional
TradeJournal, exposes two helper methods, and is a no-op when no journal
is provided (backwards-compat).
"""
from unittest.mock import MagicMock
import pytest
import yaml

from engine import SafeOrchestrator
from engine.journal import TradeJournal, TradeSnapshot


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── 1. Constructor backwards-compat ────────────────────────────────────────

def test_orchestrator_default_trade_journal_is_none(base_config, tmp_path):
    """Without trade_journal kwarg, the attribute is None (backwards-compat)."""
    orch = SafeOrchestrator(
        base_config, state_dir=str(tmp_path), freshness_check=False
    )
    assert orch.trade_journal is None


def test_orchestrator_accepts_trade_journal_kwarg(base_config, tmp_path):
    """trade_journal kwarg is stored on the orchestrator."""
    journal = TradeJournal(str(tmp_path / "tj.jsonl"))
    orch = SafeOrchestrator(
        base_config,
        state_dir=str(tmp_path),
        freshness_check=False,
        trade_journal=journal,
    )
    assert orch.trade_journal is journal


# ── 2. _journal_record_entry helper ────────────────────────────────────────

def test_journal_record_entry_helper_writes_snapshot_when_present(base_config, tmp_path):
    """When a journal is wired, the entry helper passes a TradeSnapshot to
    record_entry with the position's id, symbol, direction, entry price,
    size, and initial SL."""
    mock_journal = MagicMock(spec=TradeJournal)
    orch = SafeOrchestrator(
        base_config,
        state_dir=str(tmp_path),
        freshness_check=False,
        trade_journal=mock_journal,
    )
    pos = orch.lifecycle.open_position(
        symbol="BTC/USDT", direction="LONG",
        entry_price=100.0, size=1.0,
        sl=99.0, tp1=101.0, tp2=102.0,
        scenario_id="test-scenario",
    )

    orch._journal_record_entry(pos)

    assert mock_journal.record_entry.called, "record_entry must be called"
    snap = mock_journal.record_entry.call_args[0][0]
    assert isinstance(snap, TradeSnapshot)
    assert snap.trade_id == pos.id
    assert snap.symbol == "BTC/USDT"
    assert snap.direction == "LONG"
    assert snap.entry_price == 100.0
    assert snap.position_size == 1.0
    assert snap.sl_initial == 99.0
    assert snap.tp1_initial == 101.0
    assert snap.tp2_initial == 102.0


def test_journal_record_entry_helper_is_noop_when_journal_none(base_config, tmp_path):
    """When trade_journal is None, the entry helper is a silent no-op.
    Must not raise AttributeError or any exception."""
    orch = SafeOrchestrator(
        base_config, state_dir=str(tmp_path), freshness_check=False
    )
    pos = orch.lifecycle.open_position(
        symbol="BTC/USDT", direction="LONG",
        entry_price=100.0, size=1.0,
        sl=99.0, tp1=101.0, tp2=102.0,
    )
    # Must not raise
    orch._journal_record_entry(pos)


# ── 3. _journal_record_exit helper ─────────────────────────────────────────

def test_journal_record_exit_helper_writes_exit_when_present(base_config, tmp_path):
    """When a journal is wired, the exit helper calls record_exit with the
    position's id, exit price, reason, realized_pnl, and bars_held."""
    mock_journal = MagicMock(spec=TradeJournal)
    orch = SafeOrchestrator(
        base_config,
        state_dir=str(tmp_path),
        freshness_check=False,
        trade_journal=mock_journal,
    )
    pos = orch.lifecycle.open_position(
        symbol="BTC/USDT", direction="LONG",
        entry_price=100.0, size=1.0,
        sl=99.0, tp1=101.0, tp2=102.0,
    )
    orch.lifecycle.close_position(pos, price=101.5, reason="MANUAL")

    orch._journal_record_exit(pos, exit_price=101.5, reason="MANUAL")

    assert mock_journal.record_exit.called, "record_exit must be called"
    call = mock_journal.record_exit.call_args
    # Accept positional or keyword style; bind to the TradeJournal.record_exit signature.
    if call.args:
        trade_id = call.args[0]
        exit_price = call.args[1]
        exit_reason = call.args[2]
        realized_pnl = call.args[3]
        bars_held = call.args[4] if len(call.args) > 4 else call.kwargs.get("bars_held")
    else:
        trade_id = call.kwargs["trade_id"]
        exit_price = call.kwargs["exit_price"]
        exit_reason = call.kwargs["exit_reason"]
        realized_pnl = call.kwargs["realized_pnl"]
        bars_held = call.kwargs["bars_held"]
    assert trade_id == pos.id
    assert exit_price == 101.5
    assert exit_reason == "MANUAL"
    assert realized_pnl == pytest.approx(1.5, rel=0.01)
    assert isinstance(bars_held, int) and bars_held >= 0


# ── 4. End-to-end roundtrip with a real TradeJournal + filesystem ──────────

def test_open_close_roundtrip_writes_jsonl_file(base_config, tmp_path):
    """With a real TradeJournal pointed at tmp_path, an open + close cycle
    must produce exactly one JSONL line containing the entry+exit fields.

    This is the contract Phase 0's extract_sl_evidence.py relies on
    (`journal_rows > 0`) — pre-fix it was silently 0 in production.
    """
    journal_path = tmp_path / "state_test" / "trade_journal.jsonl"
    journal = TradeJournal(str(journal_path))
    orch = SafeOrchestrator(
        base_config,
        state_dir=str(tmp_path),
        freshness_check=False,
        trade_journal=journal,
    )
    pos = orch.lifecycle.open_position(
        symbol="ETH/USDT", direction="SHORT",
        entry_price=2000.0, size=0.5,
        sl=2050.0, tp1=1980.0, tp2=1950.0,
    )
    orch._journal_record_entry(pos)
    orch.lifecycle.close_position(pos, price=1970.0, reason="MANUAL")
    orch._journal_record_exit(pos, exit_price=1970.0, reason="MANUAL")

    assert journal_path.exists(), "JSONL file must be created on close"
    lines = journal_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1, f"expected 1 JSONL line, got {len(lines)}"

    import json
    rec = json.loads(lines[0])
    assert rec["trade_id"] == pos.id
    assert rec["symbol"] == "ETH/USDT"
    assert rec["direction"] == "SHORT"
    assert rec["entry_price"] == 2000.0
    assert rec["sl_initial"] == 2050.0
    assert rec["exit_price"] == 1970.0
    assert rec["exit_reason"] == "MANUAL"
    # SHORT 2000 → 1970: profit of 30 * 0.5 = 15.0
    assert rec["realized_pnl"] == pytest.approx(15.0, rel=0.01)
    assert rec["is_winner"] is True
