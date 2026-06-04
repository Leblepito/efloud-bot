from scripts.routines._thresholds import derive

def test_dd_tiers_below_breaker():
    t = derive({"safety": {"weekly_drawdown_limit_pct": 10}})
    assert t["dd_warn_pct"] < t["dd_alert_pct"] < t["dd_critical_pct"] < 10

def test_defaults_when_no_config():
    t = derive({})
    assert t["liq_distance_warn_pct"] == 20 and t["liq_distance_critical_pct"] == 5
