"""
Test v2.2.0 yeni modüller:
  - NotificationManager
  - PermissionManager (mock client ile)
  - CircuitBreaker emergency threshold
  - PositionGuard reserve balance
"""

import sys
sys.path.insert(0, '.')
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')


def test_notification_manager():
    print("\n=== TEST: NotificationManager ===")
    from engine.notifications import NotificationManager
    nm = NotificationManager(channels=['log'])  # sadece log, terminal kalabalık etmesin

    # Read-only signal
    nm.signal_readonly(
        symbol="BTC/USDT", direction="LONG",
        entry=77000.0, sl=76500.0, tp1=78500.0, tp2=80000.0,
        confluence=72,
    )
    nm.position_opened("ETH/USDT", "LONG", 2400.0, 0.04, 2380.0, 2440.0, 65)
    nm.position_closed("ETH/USDT", "LONG", 2440.0, 1.60, "TP1 hit")
    nm.alert("WARNING", "Test alert message")
    print("  ✅ NotificationManager works")


def test_permission_manager_mock():
    print("\n=== TEST: PermissionManager (mock) ===")
    from engine.permissions import PermissionManager

    class MockExchange:
        def fetch_balance(self, params=None): return {"canTrade": True}
        def fapiPrivateV2GetAccount(self): return {"canTrade": True}
        def fapiPublicGetExchangeInfo(self):
            return {"symbols": [
                {"symbol": "BTCUSDT", "status": "TRADING",
                 "filters": [{"filterType": "LOT_SIZE", "minQty": "0.001"},
                              {"filterType": "MIN_NOTIONAL", "notional": "5"}]},
                {"symbol": "ETHUSDT", "status": "TRADING",
                 "filters": [{"filterType": "LOT_SIZE", "minQty": "0.01"},
                              {"filterType": "MIN_NOTIONAL", "notional": "5"}]},
                # APT yok — listeli değil
            ]}

    class MockClient:
        market_type = "futures"
        exchange = MockExchange()

    pm = PermissionManager(MockClient())
    perms = pm.detect_all(["BTC/USDT", "ETH/USDT", "APT/USDT"], estimated_notional=30.0)

    assert pm.is_tradeable("BTC/USDT"), "BTC should be tradeable"
    assert pm.is_tradeable("ETH/USDT"), "ETH should be tradeable"
    assert not pm.is_tradeable("APT/USDT"), "APT not listed → readonly"
    assert pm.permissions["APT/USDT"].reason == "Symbol not listed on Binance futures"

    print(f"  ✅ Tradeable: {pm.get_tradeable_symbols()}")
    print(f"  ✅ Readonly: {pm.get_readonly_symbols()}")


def test_circuit_breaker_emergency():
    print("\n=== TEST: CircuitBreaker emergency threshold ===")
    from engine.safety.breaker import CircuitBreaker, BreakerState

    # $200 starting, $190 emergency
    cb = CircuitBreaker(
        starting_balance=200,
        emergency_balance_threshold=190,
    )
    cb.current_balance = 200

    # Bakiye normalken: OPEN
    status = cb.check()
    assert status.state == BreakerState.OPEN, f"Expected OPEN, got {status.state}"

    # Bakiye 185'e düşünce: HALT
    cb.current_balance = 185
    status = cb.check()
    assert status.state == BreakerState.HALTED, f"Expected HALTED, got {status.state}"
    assert "Emergency" in status.reason, f"Expected Emergency reason: {status.reason}"

    print(f"  ✅ Emergency triggered at $185 < $190 threshold")
    print(f"     Reason: {status.reason}")


def test_position_guard_reserve():
    print("\n=== TEST: PositionGuard reserve balance ===")
    from engine.safety.position_guard import PositionGuard

    # Reserve = 20 USDT, max %3 = 6 USDT margin
    pg = PositionGuard(
        max_notional_pct_of_balance=3.0,
        reserve_balance=20.0,
    )

    # Bakiye 1000, pozisyon margin ~5 USDT → 1000 - 5 - 20 = 975 OK
    result = pg.can_open_position(
        balance=1000, entry=77000.0, size=0.000195, sl=76500.0,
        atr=300, direction="LONG", symbol="BTC/USDT",
        existing_positions=[], leverage=3,
    )
    print(f"  Normal (bakiye=1000, margin~5): allowed={result.allowed}")
    if not result.allowed:
        print(f"     reason: {result.reason}")
    assert result.allowed, f"Expected allowed: {result.reason}"

    # Bakiye 22 USDT, margin ~5, reserve=20 → 22-5-20 = -3 RED
    result2 = pg.can_open_position(
        balance=22, entry=77000.0, size=0.000195, sl=76500.0,
        atr=300, direction="LONG", symbol="BTC/USDT",
        existing_positions=[], leverage=3,
    )
    print(f"  Düşük bakiye reserve ihlali (bakiye=22): allowed={result2.allowed}")
    print(f"     reason: {result2.reason}")
    assert not result2.allowed, "Expected reserve violation"
    assert "Reserve" in result2.reason

    print("  ✅ Reserve balance check works")


if __name__ == "__main__":
    test_notification_manager()
    test_permission_manager_mock()
    test_circuit_breaker_emergency()
    test_position_guard_reserve()
    print("\n  ✅ ALL v2.2.0 TESTS PASSED")
