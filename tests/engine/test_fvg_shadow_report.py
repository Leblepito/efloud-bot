"""T-20261114-01: tools/fvg_shadow_report.py parses and aggregates shadow lines."""
from tools.fvg_shadow_report import render, summarize

P = "2026-11-14 10:00:00,000 | efloud.safe_orch       | INFO  | "
LINES = [
    P + "[fvg shadow] setup+ ETH/USDT LONG entry=1959.6 sl=1940 tp1=2000(LUX_OB) tp2=None(NONE)",
    P + "[fvg shadow] filled ETH/USDT LONG entry=1959.6 bar_ts=1",
    P + "[fvg shadow] exit ETH/USDT LONG reason=TP1 gross_r=+2.06 net_r=+1.99 entry=1959.6",
    P + "[fvg shadow] setup+ BTC/USDT SHORT entry=90000 sl=91000 tp1=88000(LUX_BB) tp2=None(NONE)",
    P + "[fvg shadow] filled BTC/USDT SHORT entry=90000 bar_ts=2",
    P + "[fvg shadow] exit BTC/USDT SHORT reason=SL gross_r=-1.00 net_r=-1.06 entry=90000",
    P + "[fvg shadow] expired SOL/USDT LONG entry=80 bars=48",
    P + "[lux] scan ETH/USDT htf_bias=BULL",
]


def test_summarize_counts_and_r():
    s = summarize(LINES)
    t = s["TOTAL"]
    assert t["events"]["setup+"] == 2 and t["events"]["filled"] == 2
    assert t["events"]["expired"] == 1
    assert t["reasons"] == {"TP1": 1, "SL": 1}
    assert t["net"] == [1.99, -1.06]
    assert s["ETH/USDT"]["gross"] == [2.06]


def test_render_waits_below_30_trades():
    out = render(summarize(LINES))
    assert "TOTAL" in out and "WAIT (n=2/30)" in out
    assert "+0.46" in out          # avg net R of the two exits ((1.99-1.06)/2)
