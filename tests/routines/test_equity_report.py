from scripts.routines.equity_report import build_report

def test_report_has_core_metrics():
    eq = [{"t": "2026-06-01", "equity": 1000.0}, {"t": "2026-06-02", "equity": 1030.0}]
    trades = [{"realized_pnl": 30.0, "symbol": "BTC/USDT"}]
    md = build_report(eq, trades, {"status": "ok"})
    for s in ["Realized PnL", "Max Drawdown", "Sharpe", "Equity"]:
        assert s in md

def test_handles_empty():
    md = build_report([], [], {"status": "ok"})
    assert "No" in md or "0" in md
