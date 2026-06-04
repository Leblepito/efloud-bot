from scripts.routines.config_drift import evaluate

def test_drift_detected():
    _, b = evaluate({"min_confluence": 50}, {"min_confluence": 80}, ["min_confluence"])
    assert any(x["severity"] == "warn" for x in b)
    assert "50" in b[0]["body"]
    assert "80" in b[0]["body"]

def test_in_sync_silent():
    _, b = evaluate({"min_confluence": 80}, {"min_confluence": 80}, ["min_confluence"])
    assert b == []

def test_nested_drift_detected():
    live = {"safety": {"weekly_drawdown_limit_pct": 5}}
    repo = {"safety": {"weekly_drawdown_limit_pct": 8}}
    _, b = evaluate(live, repo, ["safety.weekly_drawdown_limit_pct"])
    assert any(x["severity"] == "warn" for x in b)
    assert "5" in b[0]["body"]
    assert "8" in b[0]["body"]
