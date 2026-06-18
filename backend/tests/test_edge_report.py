from scripts.routines.edge_report import build_report

def test_status_line_first_and_disclaimer():
    metrics = {"overall": {"n": 23, "status": "insufficient_sample", "expectancy": None,
                           "win_rate": None, "profit_factor": None, "timeout_rate": 0.1,
                           "edge_sign_stable": False, "timeout_panel": {}},
               "breakdowns": {}, "status_breakdown": {"resolved": 23, "open": 5},
               "primary_hypothesis": "pooled NET expectancy, tradeable universe"}
    out = build_report(metrics)
    first = out.strip().splitlines()[0].lower()
    assert "insufficient" in first
    assert "not financial advice" in out.lower() or "hypothetical" in out.lower()
    assert "-5.3" in out
