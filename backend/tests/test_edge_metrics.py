# backend/tests/test_edge_metrics.py
from engine.signal_ledger import SignalRecord
from engine.edge_metrics import aggregate

def _r(net, outcome="tp1", status="resolved", conf=70, sym="A/USDT", direction="LONG"):
    return SignalRecord(signal_id=f"{sym}-{net}-{outcome}", ts_emitted=0, brk_ts=0, symbol=sym,
        direction=direction, emitted_entry=100, sl=98, tp1=104, tp2=None, confluence=conf,
        rr1=2.0, rr2=None, timeframe="15m", htf_bias="LONG", regime="trend", reasons=[],
        was_tradeable=True, entry_is_retrace=False, exit_model="single_target",
        status=status, outcome=outcome, hypo_r_gross=net, hypo_r_net=net)

def test_min_n_suppressed_below_threshold():
    recs = [_r(1.0) for _ in range(5)]
    out = aggregate(recs, min_n_print=30, min_n_claim=100)
    assert out["overall"]["status"] == "insufficient_sample"
    assert out["overall"].get("expectancy") is None

def test_expectancy_and_pf_when_enough():
    recs = [_r(1.0) for _ in range(60)] + [_r(-1.0, outcome="sl") for _ in range(40)]
    out = aggregate(recs, min_n_print=30, min_n_claim=100)
    assert out["overall"]["n"] == 100
    assert abs(out["overall"]["expectancy"] - 0.2) < 1e-9
    assert out["overall"]["profit_factor"] is not None

def test_pf_null_when_no_losses():
    recs = [_r(1.0) for _ in range(40)]
    out = aggregate(recs, min_n_print=30, min_n_claim=100)
    assert out["overall"]["profit_factor"] is None

def test_three_way_timeout_panel_and_sign_stability():
    recs = ([_r(1.0) for _ in range(60)] + [_r(-1.0, outcome="sl") for _ in range(20)]
            + [_r(0.0, outcome="timeout", status="timeout") for _ in range(20)])
    out = aggregate(recs, min_n_print=30, min_n_claim=100)
    panel = out["overall"]["timeout_panel"]
    assert set(panel) == {"mark_to_market", "zero", "excluded"}
    assert out["overall"]["edge_sign_stable"] in (True, False)

def test_unresolved_excluded():
    recs = [_r(1.0) for _ in range(40)] + [_r(None, status="unresolved_data", outcome=None) for _ in range(10)]
    out = aggregate(recs, min_n_print=30, min_n_claim=100)
    assert out["overall"]["n"] == 40
    assert out["status_breakdown"]["unresolved_data"] == 10
