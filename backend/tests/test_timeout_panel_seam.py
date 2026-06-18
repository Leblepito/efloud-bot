"""Final-review regression: a real timeout must carry mfe_r/mae_r through
resolve_open_signals -> ledger -> aggregate, so the 3-way timeout panel's
mark_to_market column is NOT byte-identical to the zero column (which would
collapse edge_sign_stable into a false 'stable' GO gate).
"""
from engine.signal_ledger import SignalLedger
from engine.edge_metrics import aggregate
from scripts.routines.resolve_signals import resolve_open_signals


class FakeFetcher:
    def __init__(self, bars):
        self.bars = bars
    def fetch_bars(self, symbol, tf, since_ms, until_ms):
        return [b for b in self.bars[symbol] if since_ms <= b["ts"] <= until_ms]
    def funding_sum(self, symbol, since_ms, until_ms):
        return 0.0


def _bar(ts, o, h, l, c):
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c}


def test_timeout_carries_mfe_so_panel_columns_differ(tmp_path):
    led = SignalLedger(tmp_path / "s.jsonl")
    led.record_signal(symbol="T/USDT", direction="LONG", brk_ts=0, emitted_entry=100.0,
                      sl=98.0, tp1=110.0, tp2=None, confluence=70, rr1=5.0, rr2=None,
                      timeframe="15m", htf_bias="LONG", regime="trend", reasons=[],
                      was_tradeable=True, entry_is_retrace=False,
                      exit_model="single_target", ts_emitted=0)
    # price rises to 105 (mfe>0) but never hits tp1=110 nor sl=98 -> timeout
    fetcher = FakeFetcher({"T/USDT": [_bar(0, 100, 100, 100, 100),
                                      _bar(60000, 100, 105, 100, 104),
                                      _bar(120000, 104, 105, 103, 104)]})
    cfg = {"resolution_tf": "1m", "max_horizon_hours": 48, "max_symbols": 25,
           "fetch_fail_alert_pct": 20, "smc_version": "v1", "fill_window_bars": 8,
           "state_dir": str(tmp_path)}
    resolve_open_signals(led, fetcher, cfg)

    rec = led.all_signals()[0]
    assert rec.status == "timeout"
    assert rec.mfe_r is not None and rec.mfe_r > 0   # timeout now carries excursions

    metrics = aggregate(led.all_signals(), min_n_print=1, min_n_claim=1)
    panel = metrics["overall"]["timeout_panel"]
    assert panel["mark_to_market"] != panel["zero"]   # 3-way panel no longer degenerate
