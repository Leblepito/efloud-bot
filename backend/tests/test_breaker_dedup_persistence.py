"""C2 regression: the breaker-dedup flag (``_reported_to_breaker``) must
survive ``to_full_dict`` / ``from_full_dict``.

Background: STEP 5 in ``engine.safe_orchestrator`` records a closed position's
realized PnL to the CircuitBreaker exactly once, guarded by a runtime attribute
``_reported_to_breaker`` set on the Position. ``to_full_dict`` did NOT serialize
that flag and ``from_full_dict`` did NOT restore it, so after a restart every
already-counted closed position (lifecycle never prunes closed positions) was
re-counted by STEP 5 — corrupting ``daily_pnl`` / ``consecutive_losses`` /
``peak_balance`` and potentially masking a real weekly-drawdown HALT (the
2026-05-14 bare-position class).
"""
from engine.lifecycle import Entry, Position


def _make_closed_position() -> Position:
    entry = Entry(id="e1", price=100.0, size=1.0,
                  timestamp="2026-05-13T10:00:00Z", reason="initial")
    return Position(
        id="pos-1", symbol="BTC/USDT", direction="LONG",
        entries=[entry], sl=98.0, tp1=104.0, tp2=110.0, initial_sl=98.0,
        opened_at="2026-05-13T10:00:00Z", closed_at="2026-05-13T12:00:00Z",
    )


def test_to_full_dict_includes_reported_to_breaker():
    """Once STEP 5 has counted a closed trade, the flag must serialize."""
    pos = _make_closed_position()
    pos._reported_to_breaker = True
    assert pos.to_full_dict().get("_reported_to_breaker") is True


def test_reported_flag_survives_round_trip():
    """A counted position reloaded after restart must stay counted, so STEP 5
    does NOT record its PnL to the breaker a second time."""
    pos = _make_closed_position()
    pos._reported_to_breaker = True
    restored = Position.from_full_dict(pos.to_full_dict())
    assert getattr(restored, "_reported_to_breaker", False) is True


def test_unreported_position_round_trips_as_false():
    """A position that was never counted must restore as not-counted."""
    pos = _make_closed_position()
    restored = Position.from_full_dict(pos.to_full_dict())
    assert getattr(restored, "_reported_to_breaker", False) is False


def test_backwards_compat_missing_key_defaults_false():
    """Pre-fix state files lack the key; restore must default to False
    (not crash)."""
    pos = _make_closed_position()
    pos._reported_to_breaker = True
    d = pos.to_full_dict()
    d.pop("_reported_to_breaker", None)
    restored = Position.from_full_dict(d)
    assert getattr(restored, "_reported_to_breaker", False) is False
