"""End-to-end seam test: ledger -> resolver -> edge_metrics -> edge_report.

The per-task unit tests each use isolated fixtures; nothing exercises the full
chain. This validates that the patch dict resolve_open_signals writes back is
consumable by edge_metrics.aggregate and edge_report.build_report.
"""
from engine.signal_ledger import SignalLedger
from engine.edge_metrics import aggregate
from scripts.routines.resolve_signals import resolve_open_signals
from scripts.routines.edge_report import build_report


class FakeFetcher:
    def __init__(self, bars_by_symbol):
        self.bars = bars_by_symbol
    def fetch_bars(self, symbol, tf, since_ms, until_ms):
        return [b for b in self.bars[symbol] if since_ms <= b["ts"] <= until_ms]
    def funding_sum(self, symbol, since_ms, until_ms):
        return 0.0


def _bar(ts, o, h, l, c):
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c}


def _sig(symbol, brk_ts):
    return dict(symbol=symbol, direction="LONG", brk_ts=brk_ts, emitted_entry=100.0,
               sl=98.0, tp1=104.0, tp2=None, confluence=70, rr1=2.0, rr2=None,
               timeframe="15m", htf_bias="LONG", regime="trend", reasons=[],
               was_tradeable=True, entry_is_retrace=False, exit_model="single_target",
               ts_emitted=0)


def _cfg(tmp_path):
    return {"resolution_tf": "1m", "max_horizon_hours": 48, "max_symbols": 25,
            "fetch_fail_alert_pct": 20, "smc_version": "v1", "fill_window_bars": 8,
            "state_dir": str(tmp_path)}


def test_full_chain_record_resolve_aggregate_report(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl")
    led.record_signal(**_sig("AAA/USDT", 1000))   # will hit TP
    led.record_signal(**_sig("BBB/USDT", 2000))   # will hit SL

    fetcher = FakeFetcher({
        "AAA/USDT": [_bar(0, 100, 100, 100, 100), _bar(60000, 100, 104, 100, 104)],
        "BBB/USDT": [_bar(0, 100, 100, 100, 100), _bar(60000, 100, 100, 97, 98)],
    })

    summary = resolve_open_signals(led, fetcher, _cfg(tmp_path))
    assert summary["resolved"] == 2

    rows = {r.symbol: r for r in led.all_signals()}
    assert rows["AAA/USDT"].outcome == "tp1" and rows["AAA/USDT"].hypo_r_net is not None
    assert rows["BBB/USDT"].outcome == "sl" and rows["BBB/USDT"].hypo_r_net is not None

    # default thresholds -> insufficient sample, but the chain must still build a report
    metrics_default = aggregate(led.all_signals())
    assert metrics_default["overall"]["status"] == "insufficient_sample"
    assert metrics_default["status_breakdown"]["resolved"] == 2
    report_default = build_report(metrics_default)
    assert "INSUFFICIENT" in report_default.splitlines()[0].upper()
    assert "-5.3" in report_default

    # lowered thresholds -> populated path exercises expectancy + disclaimer end-to-end
    metrics_pop = aggregate(led.all_signals(), min_n_print=1, min_n_claim=2)
    assert metrics_pop["overall"]["n"] == 2
    assert metrics_pop["overall"]["expectancy"] is not None
    report_pop = build_report(metrics_pop)
    assert "NET E[R]" in report_pop
    assert "Not financial advice" in report_pop
