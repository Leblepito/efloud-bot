"""Total-exposure guard must count the new position as full NOTIONAL (bug-hunt #10).

Pre-fix: `notional` was reassigned to MARGIN (notional/leverage) for the size-cap
check, then that margin value was added to the exposure sum — but existing positions
were summed as full notional (avg_entry × remaining_size). Mixing units undercounted
the new position by the leverage factor, so the exposure cap was too permissive.
Fix: use a separate full_notional for the exposure check so both sides match.
"""
from engine.safety.position_guard import PositionGuard


class _FakeExisting:
    def __init__(self, avg, size, symbol="ETH/USDT", direction="LONG"):
        self.avg_entry_price = avg
        self.remaining_size = size
        self.is_open = True
        self.symbol = symbol
        self.direction = direction
        self.scenario_id = None


def _guard():
    return PositionGuard(
        max_notional_pct_of_balance=50.0,
        max_total_exposure_multiplier=1.0,   # total notional <= 1.0 × balance
        max_holding_hours=24.0,
        max_pyramid_adds=0,
        min_sl_distance_atr=0.0,
        max_sl_distance_atr=100.0,
        reserve_balance=0.0,
        max_open_positions=10,
        reverse_min_profit_pct=0.2,
    )


def test_exposure_rejects_when_full_notional_exceeds_cap():
    g = _guard()
    existing = [_FakeExisting(avg=100.0, size=5.0)]   # 500 notional already open
    # New: entry 100, size 6 → full notional 600 (margin 120 at lev=5).
    # True total notional = 500 + 600 = 1100 > 1000 cap → must REJECT.
    res = g.can_open_position(
        balance=1000.0, entry=100.0, size=6.0, sl=95.0, atr=1.0,
        direction="LONG", symbol="BTC/USDT", existing_positions=existing, leverage=5,
    )
    assert not res.allowed
    assert "exposure" in res.reason.lower()


def test_exposure_allows_within_cap():
    g = _guard()
    existing = [_FakeExisting(avg=100.0, size=2.0)]   # 200 notional
    # New full notional 500 → total 700 < 1000 → allowed (fix must not over-reject).
    res = g.can_open_position(
        balance=1000.0, entry=100.0, size=5.0, sl=95.0, atr=1.0,
        direction="LONG", symbol="BTC/USDT", existing_positions=existing, leverage=5,
    )
    assert res.allowed
