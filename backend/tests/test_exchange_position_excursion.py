"""exchange.Position per-bar MAE/MFE tracking + journal wiring.

Counterpart to backend/tests/test_position_excursion.py (which pins the
engine.lifecycle.Position contract). PR fix/exchange-position-mae-mfe-journal
adds the same monotonic-positive excursion contract to the exchange-side
Position dataclass and threads mae_pct/mfe_pct into
OrderManager._journal_record_close → TradeJournal.record_exit.

Before this PR every live trade (reconcile-driven close) journaled
mae_pct=0, mfe_pct=0 because the args were never passed, and the dataclass
didn't even have the fields.
"""
from unittest.mock import MagicMock
import pytest

from exchange import OrderManager, Position as ExchangePosition
from engine.journal import TradeJournal


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def long_pos():
    return ExchangePosition(
        symbol="BTC/USDT",
        direction="LONG",
        entry=100.0,
        sl=95.0,
        tp1=105.0,
        tp2=110.0,
        size=1.0,
        order_id="bn-order-excursion-long",
    )


@pytest.fixture
def short_pos():
    return ExchangePosition(
        symbol="ETH/USDT",
        direction="SHORT",
        entry=2000.0,
        sl=2100.0,
        tp1=1950.0,
        tp2=1900.0,
        size=0.5,
        order_id="bn-order-excursion-short",
    )


# ── 1. Field defaults & dataclass shape ─────────────────────────────────────

def test_position_default_mae_mfe_zero(long_pos):
    """Fresh exchange.Position has mae_pct == mfe_pct == 0.0."""
    assert long_pos.mae_pct == 0.0
    assert long_pos.mfe_pct == 0.0


# ── 2. update_excursion: LONG path ──────────────────────────────────────────

def test_long_low_below_entry_grows_mae(long_pos):
    long_pos.update_excursion(high=101.0, low=98.0)  # 2% adverse
    assert long_pos.mae_pct == pytest.approx(2.0, rel=1e-6)
    assert long_pos.mfe_pct == pytest.approx(1.0, rel=1e-6)


def test_long_high_above_entry_grows_mfe(long_pos):
    long_pos.update_excursion(high=103.0, low=99.5)  # 0.5% adverse, 3% favorable
    assert long_pos.mae_pct == pytest.approx(0.5, rel=1e-6)
    assert long_pos.mfe_pct == pytest.approx(3.0, rel=1e-6)


# ── 3. update_excursion: SHORT path (signs invert) ──────────────────────────

def test_short_high_above_entry_grows_mae(short_pos):
    short_pos.update_excursion(high=2050.0, low=1990.0)  # 2.5% adverse for SHORT
    assert short_pos.mae_pct == pytest.approx(2.5, rel=1e-6)
    assert short_pos.mfe_pct == pytest.approx(0.5, rel=1e-6)


def test_short_low_below_entry_grows_mfe(short_pos):
    short_pos.update_excursion(high=2010.0, low=1940.0)  # 0.5% adverse, 3% favorable
    assert short_pos.mae_pct == pytest.approx(0.5, rel=1e-6)
    assert short_pos.mfe_pct == pytest.approx(3.0, rel=1e-6)


# ── 4. Monotonicity (never shrinks) ─────────────────────────────────────────

def test_excursion_monotonic_mae_only_grows(long_pos):
    long_pos.update_excursion(high=101.0, low=97.0)  # MAE = 3%
    long_pos.update_excursion(high=102.0, low=99.0)  # MAE candidate 1% < 3%
    assert long_pos.mae_pct == pytest.approx(3.0, rel=1e-6)


def test_excursion_monotonic_mfe_only_grows(long_pos):
    long_pos.update_excursion(high=104.0, low=99.0)  # MFE = 4%
    long_pos.update_excursion(high=102.0, low=99.5)  # MFE candidate 2% < 4%
    assert long_pos.mfe_pct == pytest.approx(4.0, rel=1e-6)


# ── 5. Invalid inputs are no-ops ────────────────────────────────────────────

def test_excursion_ignores_zero_or_negative(long_pos):
    long_pos.update_excursion(high=0.0, low=98.0)
    long_pos.update_excursion(high=101.0, low=0.0)
    long_pos.update_excursion(high=-1.0, low=-1.0)
    assert long_pos.mae_pct == 0.0
    assert long_pos.mfe_pct == 0.0


def test_excursion_ignores_zero_entry():
    pos = ExchangePosition(
        symbol="X/USDT", direction="LONG", entry=0.0, sl=0.0, tp1=0.0, tp2=0.0,
        size=1.0,
    )
    pos.update_excursion(high=100.0, low=90.0)
    assert pos.mae_pct == 0.0
    assert pos.mfe_pct == 0.0


# ── 6. Journal wiring: _journal_record_close passes MAE/MFE ─────────────────

def test_journal_record_close_passes_mae_mfe(mock_client, long_pos):
    """Core bug fix: when _record_close runs, the trade_journal.record_exit
    call MUST receive mae_pct and mfe_pct from the position. Before this PR
    these kwargs were never passed → default 0.0 silently overwrote real
    excursion data in production."""
    mock_journal = MagicMock(spec=TradeJournal)

    # Simulate a bar's worth of excursion before close.
    long_pos.update_excursion(high=103.5, low=98.5)
    expected_mae = long_pos.mae_pct
    expected_mfe = long_pos.mfe_pct
    assert expected_mae > 0 and expected_mfe > 0  # sanity

    om = OrderManager(mock_client, dry_run=True, trade_journal=mock_journal)
    om._record_close(long_pos, exit_price=102.0, reason="TP1")

    # record_exit must have been called exactly once.
    assert mock_journal.record_exit.call_count == 1
    kwargs = mock_journal.record_exit.call_args.kwargs
    assert kwargs["mfe_pct"] == pytest.approx(expected_mfe, rel=1e-6)
    assert kwargs["mae_pct"] == pytest.approx(expected_mae, rel=1e-6)


def test_journal_record_close_zero_when_no_excursion_recorded(mock_client, long_pos):
    """A position closed before any update_excursion call still journals
    cleanly with mae=mfe=0 (default). This guards against regressions where
    a NoneType slips into the kwarg."""
    mock_journal = MagicMock(spec=TradeJournal)

    om = OrderManager(mock_client, dry_run=True, trade_journal=mock_journal)
    om._record_close(long_pos, exit_price=99.0, reason="SL")

    kwargs = mock_journal.record_exit.call_args.kwargs
    assert kwargs["mae_pct"] == 0.0
    assert kwargs["mfe_pct"] == 0.0
