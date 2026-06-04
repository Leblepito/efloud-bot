from scripts.routines.margin_watch import evaluate

T = {
    "liq_distance_warn_pct": 20.0,
    "liq_distance_alert_pct": 10.0,
    "liq_distance_critical_pct": 5.0,
    "margin_ratio_warn": 0.5,
    "margin_ratio_critical": 0.75
}

def test_close_to_liq_is_critical():
    pos = [{"symbol": "BTC/USDT", "markPrice": 100.0, "liquidationPrice": 97.0, "side": "long"}]
    _, b = evaluate(pos, {"marginRatio": 0.2}, T)            # 3% away
    assert any(x["severity"] == "critical" for x in b)

def test_safe_distance_no_alert():
    pos = [{"symbol": "BTC/USDT", "markPrice": 100.0, "liquidationPrice": 50.0, "side": "long"}]
    _, b = evaluate(pos, {"marginRatio": 0.1}, T)
    assert b == []

def test_high_margin_ratio_alerts():
    _, b = evaluate([], {"marginRatio": 0.8}, T)
    assert any(x["severity"] == "critical" for x in b)
