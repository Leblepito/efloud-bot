"""Position MAE/MFE state persistence across to_full_dict / from_full_dict.

Background: PR #57 added per-bar MAE/MFE tracking to engine.lifecycle.Position
but to_full_dict / from_full_dict — which power state persistence across bot
restarts — did NOT serialize these fields. So an open position resumed
post-restart with mae_pct=mfe_pct=0.0, losing the running maxima and
under-reporting Phase 0 evidence for any restart-spanning trade.

This regression was flagged by the PR #57 code review and is fixed here.
"""
import pytest

from engine.lifecycle import Position, Entry


def _make_position(mae: float = 0.0, mfe: float = 0.0) -> Position:
    entry = Entry(id="e1", price=100.0, size=1.0, timestamp="2026-05-13T10:00:00Z", reason="initial")
    return Position(
        id="pos-1",
        symbol="BTC/USDT",
        direction="LONG",
        entries=[entry],
        sl=98.0,
        tp1=104.0,
        tp2=110.0,
        initial_sl=98.0,
        opened_at="2026-05-13T10:00:00Z",
        mae_pct=mae,
        mfe_pct=mfe,
    )


def test_to_full_dict_includes_mae_mfe():
    """to_full_dict must serialize mae_pct and mfe_pct so they survive
    state persistence across bot restarts."""
    pos = _make_position(mae=5.5, mfe=8.25)
    d = pos.to_full_dict()
    assert d["mae_pct"] == pytest.approx(5.5, rel=1e-6)
    assert d["mfe_pct"] == pytest.approx(8.25, rel=1e-6)


def test_from_full_dict_round_trip_preserves_mae_mfe():
    """A serialized Position reconstructed via from_full_dict must have
    the same mae_pct / mfe_pct values."""
    pos = _make_position(mae=3.0, mfe=12.5)
    d = pos.to_full_dict()
    restored = Position.from_full_dict(d)
    assert restored.mae_pct == pytest.approx(3.0, rel=1e-6)
    assert restored.mfe_pct == pytest.approx(12.5, rel=1e-6)


def test_from_full_dict_backwards_compat_when_keys_missing():
    """Old state files (written before this PR) may not contain mae_pct /
    mfe_pct keys. from_full_dict must default them to 0.0 so a state-volume
    upgrade does not crash."""
    pos = _make_position(mae=1.5, mfe=2.5)
    d = pos.to_full_dict()
    # Simulate a pre-fix state file by removing the keys.
    d.pop("mae_pct", None)
    d.pop("mfe_pct", None)
    restored = Position.from_full_dict(d)
    assert restored.mae_pct == 0.0
    assert restored.mfe_pct == 0.0


def test_freshly_opened_position_serializes_zero_excursions():
    """A position with default mae=mfe=0 round-trips cleanly."""
    pos = _make_position()  # mae=mfe=0
    restored = Position.from_full_dict(pos.to_full_dict())
    assert restored.mae_pct == 0.0
    assert restored.mfe_pct == 0.0
