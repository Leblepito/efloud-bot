from scripts.routines.breaker_watch import evaluate

def test_halt_transition_pages():
    rep, b = evaluate({"state": "OPEN"}, {"state": "HALTED", "reason": "weekly_dd"})
    assert any(x["severity"] == "critical" for x in b)
    assert "HALTED" in rep

def test_no_change_silent():
    rep, b = evaluate({"state": "OPEN"}, {"state": "OPEN"})
    assert b == []

def test_recovery_info():
    rep, b = evaluate({"state": "HALTED"}, {"state": "OPEN"})
    assert any(x["severity"] == "info" for x in b)
