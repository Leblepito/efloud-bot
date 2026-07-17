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


# ── R-14 (2026-07-17): weight eşikleri artık değerlendiriliyor ──────────────

def test_weight_breach_levels():
    from scripts.routines.market_collect import _weight_breach
    th = {"weight_warn_pct": 75, "weight_alert_pct": 90, "weight_critical_pct": 95}
    assert _weight_breach(0, th) == []
    assert _weight_breach(600, th) == []            # %50
    w = _weight_breach(960, th)                     # %80 → warn
    assert w and w[0]["severity"] == "warn" and w[0]["key"] == "weight:warn"
    a = _weight_breach(1100, th)                    # %91.7 → alert
    assert a and a[0]["severity"] == "critical" and a[0]["key"] == "weight:alert"
    c = _weight_breach(1180, th)                    # %98.3 → critical
    assert c and c[0]["key"] == "weight:critical"


def test_weight_breach_missing_header_silent():
    from scripts.routines.market_collect import _weight_breach
    assert _weight_breach(None, {"weight_warn_pct": 75}) == []
