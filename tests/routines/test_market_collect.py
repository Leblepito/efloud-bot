from scripts.routines.market_collect import dedup_candles, detect_gaps, score_market

def test_dedup_on_symbol_ts_source():
    rows = [{"symbol": "BTC", "ts": 1, "src": "1m", "o": 1}, {"symbol": "BTC", "ts": 1, "src": "1m", "o": 1}]
    assert len(dedup_candles(rows)) == 1

def test_detect_gaps_flags_missing_bar():
    ts = [0, 60000, 180000]  # 1m bars, 120000 missing
    assert detect_gaps(ts, step_ms=60000) == [120000]

def test_score_flags_oi_spike():
    breaches = score_market({"oi_change_4h_pct": 15.0, "funding_8h": 0.0005}, {"oi_spike_pct_4h": 10.0, "funding_rate_elevated_8h": 0.001})
    assert any("oi_spike" in x["key"] for x in breaches)
