# backend/tests/test_edge_costs.py
from engine.edge_costs import net_r

def test_fees_subtracted_in_r_units():
    out = net_r("LONG", 100.0, 98.0, 1.0, holding_hours=1, funding_pct_sum=0.0, slippage_r=0.0)
    assert abs(out - (1.0 - 0.04)) < 1e-6

def test_funding_signed_for_short():
    out_long = net_r("LONG", 100.0, 98.0, 1.0, holding_hours=8, funding_pct_sum=0.01, slippage_r=0.0)
    out_short = net_r("SHORT", 100.0, 102.0, 1.0, holding_hours=8, funding_pct_sum=0.01, slippage_r=0.0)
    assert out_short > out_long

def test_slippage_haircut():
    a = net_r("LONG", 100.0, 98.0, 1.0, holding_hours=1, funding_pct_sum=0.0, slippage_r=0.0)
    b = net_r("LONG", 100.0, 98.0, 1.0, holding_hours=1, funding_pct_sum=0.0, slippage_r=0.05)
    assert abs((a - b) - 0.05) < 1e-9
