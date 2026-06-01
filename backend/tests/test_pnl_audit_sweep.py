from engine.journal import TradeSnapshot


def _snap(**over):
    base = dict(
        trade_id="t1", symbol="BTC/USDT", direction="LONG", timeframe="",
        entry_timestamp="2026-06-01T00:00:00Z", entry_price=100.0,
        sl_initial=95.0, tp1_initial=110.0, tp2_initial=120.0,
        position_size=1.0, htf_bias="", intent_score_entry=0,
        intent_label_entry="", confluence_score=0,
    )
    base.update(over)
    return TradeSnapshot(**base)


def test_tradesnapshot_has_pnl_source_field():
    snap = _snap()
    assert hasattr(snap, "pnl_source")
    assert snap.pnl_source == "estimated"
    assert hasattr(snap, "realized_pnl_exchange")
