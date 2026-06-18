# backend/tests/test_resolve_open_signals.py
import json
from pathlib import Path
from engine.signal_ledger import SignalLedger
from scripts.routines.resolve_signals import resolve_open_signals

class FakeFetcher:
    """Mirrors the resolver-facing interface: fetch_bars + funding_sum (the real
    DataFrame-returning OHLCVFetcher is wrapped by an adapter in Task 7)."""
    def __init__(self, bars_by_symbol, fail=()):
        self.bars = bars_by_symbol; self.fail = set(fail)
    def fetch_bars(self, symbol, tf, since_ms, until_ms):
        if symbol in self.fail:
            raise RuntimeError("gap too large")
        return [b for b in self.bars[symbol] if since_ms <= b["ts"] <= until_ms]
    def funding_sum(self, symbol, since_ms, until_ms):
        return 0.0

BASE = dict(symbol="T/USDT", direction="LONG", brk_ts=0, emitted_entry=100.0, sl=98.0,
            tp1=104.0, tp2=None, confluence=70, rr1=2.0, rr2=None, timeframe="15m",
            htf_bias="LONG", regime="trend", reasons=[], was_tradeable=True,
            entry_is_retrace=False, exit_model="single_target", ts_emitted=0)

def _bars():
    return [{"ts":0,"open":100,"high":100,"low":100,"close":100},
            {"ts":60000,"open":100,"high":104,"low":100,"close":104}]

def _cfg(tmp_path):
    return {"resolution_tf":"1m","max_horizon_hours":48,"max_symbols":25,
            "fetch_fail_alert_pct":20,"smc_version":"v1","fill_window_bars":8,
            "state_dir": str(tmp_path)}

def test_resolves_and_nets_costs(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl"); sid = led.record_signal(**BASE)
    f = FakeFetcher({"T/USDT": _bars()})
    summary = resolve_open_signals(led, f, _cfg(tmp_path))
    rec = [r for r in led.all_signals() if r.signal_id == sid][0]
    assert rec.status == "resolved" and rec.outcome == "tp1"
    assert rec.hypo_r_gross is not None and rec.hypo_r_net is not None
    assert rec.hypo_r_net < rec.hypo_r_gross
    assert summary["resolved"] == 1

def test_fetch_failure_marks_unresolved_data_not_dropped(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl"); led.record_signal(**BASE)
    f = FakeFetcher({"T/USDT": _bars()}, fail={"T/USDT"})
    summary = resolve_open_signals(led, f, _cfg(tmp_path))
    rec = led.all_signals()[0]
    assert rec.status == "unresolved_data"
    assert summary["fetch_failed"] == 1

def test_heartbeat_written(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl"); led.record_signal(**BASE)
    f = FakeFetcher({"T/USDT": _bars()})
    resolve_open_signals(led, f, _cfg(tmp_path))
    hb = Path(tmp_path) / "signal_resolver_heartbeat.json"
    assert hb.exists() and json.loads(hb.read_text())["scanned"] == 1
