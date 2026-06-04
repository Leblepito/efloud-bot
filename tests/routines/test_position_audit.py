from scripts.routines.position_audit import evaluate

def test_bare_position_no_sltp_is_critical():
    pos = [{"symbol": "BTC/USDT", "contracts": 0.1, "side": "long"}]
    _, b = evaluate(pos, [], [{"symbol": "BTC/USDT", "size": 0.1}])  # no stop/tp orders
    assert any("bare" in x["key"] for x in b if x["severity"] == "critical")

def test_orphan_order_no_position_is_warn():
    orders = [{"symbol": "ADA/USDT", "type": "stop", "reduceOnly": True}]
    _, b = evaluate([], orders, [])
    assert any("orphan" in x["key"] for x in b)

def test_ledger_exchange_size_drift():
    _ , b = evaluate([{"symbol": "OP/USDT", "contracts": 0.5, "side": "long"}], [],
                     [{"symbol": "OP/USDT", "size": 0.4}])           # >1% size drift
    assert any("drift" in x["key"] for x in b)

def test_clean_book_silent():
    pos = [{"symbol": "BTC/USDT", "contracts": 0.1, "side": "long"}]
    orders = [{"symbol": "BTC/USDT", "type": "stop", "reduceOnly": True, "side": "short"},
              {"symbol": "BTC/USDT", "type": "take_profit", "reduceOnly": True, "side": "short"}]
    _, b = evaluate(pos, orders, [{"symbol": "BTC/USDT", "size": 0.1}])
    assert b == []
