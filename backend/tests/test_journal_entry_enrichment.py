"""SafeOrchestrator._journal_record_entry signal-context enrichment tests.

PR #51 wired entry snapshots with stub fields (htf_bias="", intent_score=0,
confluence_score=0). This PR teaches the helper to read live signal +
intent context so Phase 0 evidence + post-mortem analysis see the real
decision inputs of every recorded entry.
"""
from unittest.mock import MagicMock
import pytest
import yaml

from engine import SafeOrchestrator
from engine.journal import TradeJournal, TradeSnapshot
from engine.signals import Signal
from engine.intent import IntentScore


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def sample_signal():
    return Signal(
        direction="LONG",
        entry=100.0, sl=98.0, tp1=104.0, tp2=110.0,
        rr1=2.0, rr2=5.0,
        confluence=75,
        reasons=["BoS confirmed", "MTF aligned", "OTE entry"],
        timestamp="2026-05-13T10:00:00Z",
        in_ote=True,
        in_ob=False,
        has_sfp=True,
        zone="DISCOUNT",
    )


@pytest.fixture
def sample_intent():
    return IntentScore(
        score=80,
        label="strong",
        direction="BULL",
        body_ratio=0.85,
        volume_ratio=1.6,
        consecutive=3,
        range_expansion=1.4,
        reasons=["body>0.7", "vol_spike>1.5x"],
    )


def _open_position(orch, **overrides):
    kw = dict(symbol="BTC/USDT", direction="LONG",
              entry_price=100.0, size=1.0,
              sl=98.0, tp1=104.0, tp2=110.0)
    kw.update(overrides)
    return orch.lifecycle.open_position(**kw)


# ── 1. Signal-derived fields ──────────────────────────────────────────────

def test_journal_record_entry_uses_signal_confluence(base_config, tmp_path, sample_signal):
    mock_journal = MagicMock(spec=TradeJournal)
    orch = SafeOrchestrator(base_config, state_dir=str(tmp_path),
                             freshness_check=False, trade_journal=mock_journal)
    pos = _open_position(orch)
    orch._journal_record_entry(pos, signal=sample_signal)

    snap = mock_journal.record_entry.call_args[0][0]
    assert snap.confluence_score == 75


def test_journal_record_entry_uses_signal_reasons(base_config, tmp_path, sample_signal):
    mock_journal = MagicMock(spec=TradeJournal)
    orch = SafeOrchestrator(base_config, state_dir=str(tmp_path),
                             freshness_check=False, trade_journal=mock_journal)
    pos = _open_position(orch)
    orch._journal_record_entry(pos, signal=sample_signal)

    snap = mock_journal.record_entry.call_args[0][0]
    assert list(snap.confluence_reasons) == ["BoS confirmed", "MTF aligned", "OTE entry"]


def test_journal_record_entry_uses_signal_flags_and_zone(base_config, tmp_path, sample_signal):
    mock_journal = MagicMock(spec=TradeJournal)
    orch = SafeOrchestrator(base_config, state_dir=str(tmp_path),
                             freshness_check=False, trade_journal=mock_journal)
    pos = _open_position(orch)
    orch._journal_record_entry(pos, signal=sample_signal)

    snap = mock_journal.record_entry.call_args[0][0]
    assert snap.in_ote is True
    assert snap.in_ob is False
    assert snap.has_sfp is True
    assert snap.zone_at_entry == "DISCOUNT"


# ── 2. Intent-derived fields ───────────────────────────────────────────────

def test_journal_record_entry_uses_intent_score_and_label(base_config, tmp_path, sample_intent):
    mock_journal = MagicMock(spec=TradeJournal)
    orch = SafeOrchestrator(base_config, state_dir=str(tmp_path),
                             freshness_check=False, trade_journal=mock_journal)
    pos = _open_position(orch)
    orch._journal_record_entry(pos, intent=sample_intent)

    snap = mock_journal.record_entry.call_args[0][0]
    assert snap.intent_score_entry == 80
    assert snap.intent_label_entry == "strong"


# ── 3. htf_bias + timeframe ────────────────────────────────────────────────

def test_journal_record_entry_uses_htf_bias_param(base_config, tmp_path):
    mock_journal = MagicMock(spec=TradeJournal)
    orch = SafeOrchestrator(base_config, state_dir=str(tmp_path),
                             freshness_check=False, trade_journal=mock_journal)
    pos = _open_position(orch)
    orch._journal_record_entry(pos, htf_bias="BULL")

    snap = mock_journal.record_entry.call_args[0][0]
    assert snap.htf_bias == "BULL"


def test_journal_record_entry_uses_timeframe_param(base_config, tmp_path):
    mock_journal = MagicMock(spec=TradeJournal)
    orch = SafeOrchestrator(base_config, state_dir=str(tmp_path),
                             freshness_check=False, trade_journal=mock_journal)
    pos = _open_position(orch)
    orch._journal_record_entry(pos, timeframe="15m")

    snap = mock_journal.record_entry.call_args[0][0]
    assert snap.timeframe == "15m"


# ── 4. Backwards-compat: no context provided ──────────────────────────────

def test_journal_record_entry_backwards_compat_no_context(base_config, tmp_path):
    """Calling without signal/intent/htf_bias still produces a valid
    minimal snapshot (the PR #51 behavior). No AttributeError."""
    mock_journal = MagicMock(spec=TradeJournal)
    orch = SafeOrchestrator(base_config, state_dir=str(tmp_path),
                             freshness_check=False, trade_journal=mock_journal)
    pos = _open_position(orch)
    orch._journal_record_entry(pos)  # bare PR #51 form

    snap = mock_journal.record_entry.call_args[0][0]
    assert snap.confluence_score == 0
    assert snap.confluence_reasons == []
    assert snap.intent_score_entry == 0
    assert snap.intent_label_entry == ""
    assert snap.htf_bias == ""
    assert snap.timeframe == ""
    assert snap.in_ote is False
    assert snap.zone_at_entry == ""
