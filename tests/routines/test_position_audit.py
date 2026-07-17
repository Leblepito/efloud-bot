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


# ── R-3 (2026-07-17): StateStore zarfındaki ledger açılır ───────────────────

def test_run_unwraps_statestore_envelope_ledger(tmp_path, monkeypatch):
    """positions.json StateStore zarfıyla yazılır ({saved_at, data:[…]});
    zarf açılmadan ledger hep boş sayılıyor → açık her pozisyonda kalıcı
    false 'Position Drift' CRITICAL üretiliyordu."""
    import json
    from unittest.mock import Mock
    from scripts.routines import position_audit as pa

    monkeypatch.chdir(tmp_path)
    live_dir = tmp_path / "state_1k"
    live_dir.mkdir()
    (live_dir / "positions.json").write_text(json.dumps({
        "saved_at": "2026-07-17T00:00:00",
        "data": [{"symbol": "BTC/USDT", "size": 0.1}],
    }), encoding="utf-8")

    client = Mock()
    client.fetch_positions = Mock(return_value=[
        {"symbol": "BTC/USDT", "contracts": 0.1, "side": "long"}])
    client.fetch_open_orders = Mock(return_value=[
        {"symbol": "BTC/USDT", "type": "stop", "reduceOnly": True},
        {"symbol": "BTC/USDT", "type": "take_profit", "reduceOnly": True}])

    res = pa.run(client=client, cfg={"operation": {"state_dir": str(live_dir)}})
    assert res.ok
    assert not any("drift" in b["key"] for b in res.breaches), (
        "zarflı ledger açılmadı → false drift (R-3 regresyonu)")


# ── R-2 tamamlama (2026-07-17): sembol normalizasyonu + algo emirleri ───────

def test_ccxt_suffix_vs_ledger_plain_no_false_drift():
    """ccxt fetch_positions 'OP/USDT:USDT', ledger 'OP/USDT' döner — normalize
    edilmeden map'ler eşleşmiyor, pozisyon başına 2 false CRITICAL üriyordu."""
    ex = [{"symbol": "OP/USDT:USDT", "contracts": 0.5, "side": "long"}]
    orders = [{"symbol": "OP/USDT:USDT", "type": "stop", "reduceOnly": True, "side": "short"},
              {"symbol": "OP/USDT:USDT", "type": "take_profit", "reduceOnly": True, "side": "short"}]
    ledger = [{"symbol": "OP/USDT", "size": 0.5}]
    _, b = evaluate(ex, orders, ledger)
    assert not any("drift" in x["key"] for x in b), f"suffix normalizasyonu yok: {b}"


def test_algo_backed_sl_tp_not_flagged_bare(tmp_path, monkeypatch):
    """Botun TP/SL'leri ALGO emirleri; ccxt fetch_open_orders bunları dönmez.
    Algo taraması olmadan her korumalı pozisyon 'Bare Position' CRITICAL'iydi."""
    import json
    from unittest.mock import Mock
    from scripts.routines import position_audit as pa

    monkeypatch.chdir(tmp_path)
    live_dir = tmp_path / "state_1k"
    live_dir.mkdir()
    (live_dir / "positions.json").write_text(json.dumps({
        "saved_at": "x", "data": [{"symbol": "BTC/USDT", "size": 0.1}],
    }), encoding="utf-8")

    client = Mock()
    client.fetch_positions = Mock(return_value=[
        {"symbol": "BTC/USDT:USDT", "contracts": 0.1, "side": "long"}])
    client.fetch_open_orders = Mock(return_value=[])  # regular: boş
    client.fapiPrivateGetOpenAlgoOrders = Mock(return_value=[
        {"symbol": "BTCUSDT", "orderType": "STOP_MARKET", "side": "SELL", "algoId": "1"},
        {"symbol": "BTCUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "algoId": "2"},
    ])

    res = pa.run(client=client, cfg={"operation": {"state_dir": str(live_dir)}})
    assert res.ok
    assert not any("bare" in x["key"] for x in res.breaches), (
        f"algo-korumalı pozisyon çıplak sayıldı: {res.breaches}")
    assert not any("drift" in x["key"] for x in res.breaches)


def test_algo_fetch_failure_skips_bare_but_keeps_drift(tmp_path, monkeypatch):
    """Algo fetch başarısızsa bare kararı verilemez (fail-safe skip); drift
    denetimi çalışmaya devam eder."""
    import json
    from unittest.mock import Mock
    from scripts.routines import position_audit as pa

    monkeypatch.chdir(tmp_path)
    live_dir = tmp_path / "state_1k"
    live_dir.mkdir()
    (live_dir / "positions.json").write_text(json.dumps({
        "saved_at": "x", "data": [],
    }), encoding="utf-8")

    client = Mock()
    client.fetch_positions = Mock(return_value=[
        {"symbol": "BTC/USDT:USDT", "contracts": 0.1, "side": "long"}])
    client.fetch_open_orders = Mock(return_value=[])
    client.fapiPrivateGetOpenAlgoOrders = Mock(side_effect=Exception("binance 5xx"))

    res = pa.run(client=client, cfg={"operation": {"state_dir": str(live_dir)}})
    assert not any("bare" in x["key"] for x in res.breaches), (
        "algo fetch başarısızken bare CRITICAL üretildi (false page riski)")
    # ledger boş + exchange'te pozisyon var → drift hâlâ yakalanmalı
    assert any("drift" in x["key"] for x in res.breaches)
