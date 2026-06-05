"""WEAKNESS-exit dust gate must compare NOTIONAL, not asset units (bug-hunt #12).

Pre-fix: MIN_REMAINING_SIZE = 0.01 (commented 'USDT-notional') was compared directly
to pos.remaining_size, which is in ASSET UNITS (contracts). For high-priced assets
(BTC) a remaining 0.005 BTC (~$500) is < 0.01 → wrongly treated as 'dust' and the
weakness de-risk exit was permanently suppressed; for sub-$1 coins it never fired.
Fix: gate on notional (remaining_size × price) against a ~$5 floor.
"""
from engine.lifecycle import Entry, Position, PositionLifecycle


def _pos(remaining_size: float):
    p = Position(id="p", symbol="BTC/USDT", direction="LONG")
    p.entries.append(Entry(id="e", price=100_000.0, size=remaining_size, timestamp="t0"))
    p.tp1_hit = True          # past TP1 → weakness branch eligible
    p.sl = 90_000.0
    p.tp1 = 105_000.0
    p.tp2 = 200_000.0         # far away → TP2 not hit at the test price
    return p


def test_weakness_not_suppressed_for_high_priced_asset():
    mgr = PositionLifecycle()
    pos = _pos(remaining_size=0.005)   # 0.005 BTC @ $100k = $500 notional (NOT dust)
    mgr.positions = [pos]
    mgr.on_tick({"BTC/USDT": 100_000.0}, intent_checker=lambda p: True)
    assert pos.weakness_exit_count == 1     # weakness exit fired
    assert pos.remaining_size < 0.005       # 0.25 partial-closed


def test_weakness_suppressed_for_true_dust():
    mgr = PositionLifecycle()
    pos = _pos(remaining_size=0.00003)  # 0.00003 BTC @ $100k = $3 notional (< $5 floor)
    mgr.positions = [pos]
    mgr.on_tick({"BTC/USDT": 100_000.0}, intent_checker=lambda p: True)
    assert pos.weakness_exit_count == 0     # genuine dust → suppressed
