"""P3-4: reject an SL wider than the ISOLATED-leverage liquidation distance.

For ISOLATED Nx the position liquidates at ~(1/leverage) adverse move (minus
maintenance margin). An SL placed BEYOND that never triggers — the exchange
liquidates first at a worse price (and _estimate_exit_price then mis-attributes
the exit). The audit flagged that max_sl_atr=5.0 can produce a ~20% SL at 5x,
which equals the liquidation distance; the guard only WARNED. This rejects it.
"""
from engine.safety.position_guard import PositionGuard

_COMMON = dict(
    balance=2000.0, size=1.0, atr=10.0, direction="LONG",
    symbol="BTC/USDT", existing_positions=[],
)


def test_rejects_sl_wider_than_liquidation_at_5x():
    g = PositionGuard()
    # entry=100, sl=80 → 20% SL distance; 5x liquidation ≈ 20% → SL never fires.
    r = g.can_open_position(entry=100.0, sl=80.0, leverage=5, **_COMMON)
    assert r.allowed is False
    assert "liquidation" in (r.reason or "").lower()


def test_allows_sl_inside_liquidation_at_5x():
    g = PositionGuard()
    # entry=100, sl=90 → 10% SL distance, well inside the ~20% liquidation band.
    r = g.can_open_position(entry=100.0, sl=90.0, leverage=5, **_COMMON)
    assert r.allowed is True


def test_same_wide_sl_allowed_at_1x():
    g = PositionGuard()
    # Same 20% SL at 1x: liquidation ≈ 100% away → no liquidation conflict.
    r = g.can_open_position(entry=100.0, sl=80.0, leverage=1, **_COMMON)
    assert r.allowed is True
