from exchange import Position


def test_position_has_reconciliation_fields_with_defaults():
    pos = Position(
        symbol="BTC/USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=110.0, tp2=120.0, size=1.0,
    )
    assert pos.realized_pnl_exchange == 0.0
    assert pos.commission_paid == 0.0
    assert pos.funding_paid == 0.0
    assert pos.pnl_source == "estimated"
