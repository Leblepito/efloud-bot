"""Edge Measurement Core activation (2026-07-03).

Covers the activation-checklist items implemented for go-live:
  A — runner registers/schedules signal_resolver + edge_report
  B — Task 8: orchestrator first-sight recorder hook (flag-gated, best-effort)
  C — 'unfilled' only finalized after the fill window elapses (survivorship)
  D — signal_resolver RoutineResult.ok derived from counters
  I — edge_report explicit empty-ledger line
  + EFLOUD_SIGNAL_LEDGER_ENABLED env override (prod activation path)
"""
from __future__ import annotations

import time
import pytest

from engine.signal_ledger import SignalLedger, ledger_enabled


# ---------------------------------------------------------------- env gate
def test_ledger_enabled_env_override(monkeypatch):
    monkeypatch.delenv("EFLOUD_SIGNAL_LEDGER_ENABLED", raising=False)
    assert ledger_enabled({"enabled": False}) is False
    assert ledger_enabled({"enabled": True}) is True
    assert ledger_enabled(None) is False
    monkeypatch.setenv("EFLOUD_SIGNAL_LEDGER_ENABLED", "1")
    assert ledger_enabled({"enabled": False}) is True
    monkeypatch.setenv("EFLOUD_SIGNAL_LEDGER_ENABLED", "0")
    assert ledger_enabled({"enabled": True}) is False


# ---------------------------------------------------------------- item A
def test_runner_registers_and_schedules_edge_routines():
    from scripts.routines import runner
    assert "signal_resolver" in runner.REGISTRY
    assert "edge_report" in runner.REGISTRY
    assert runner.CADENCES.get("signal_resolver") == 300
    assert runner.CADENCES.get("edge_report") == 3600


# ---------------------------------------------------------------- item C
class _EmptyFetcher:
    def fetch_bars(self, symbol, tf, since_ms, until_ms):
        return []  # no bars -> replay_fill returns None -> 'unfilled'

    def funding_sum(self, symbol, since_ms, until_ms):
        return 0.0


def _cfg(tmp_path):
    return {"resolution_tf": "1m", "max_horizon_hours": 48,
            "fill_window_bars": 8, "max_symbols": 25,
            "fetch_fail_alert_pct": 20, "state_dir": str(tmp_path),
            "smc_version": "v1"}


def _record(ledger, ts_emitted, symbol="BTC/USDT"):
    return ledger.record_signal(
        ts_emitted=ts_emitted, brk_ts=ts_emitted, symbol=symbol,
        direction="LONG", emitted_entry=100.0, sl=99.0, tp1=102.0, tp2=None,
        confluence=70.0, rr1=2.0, rr2=None, timeframe="15m", htf_bias="BULL",
        regime="trend", reasons=[], was_tradeable=True,
        entry_is_retrace=False, exit_model="single_target",
    )


def test_young_unfilled_signal_not_finalized(tmp_path):
    """Fill window not yet elapsed -> record stays open (awaiting_fill)."""
    from scripts.routines.resolve_signals import resolve_open_signals
    ledger = SignalLedger(tmp_path / "ledger.jsonl")
    now_ms = int(time.time() * 1000)
    sid = _record(ledger, now_ms)  # emitted just now
    counters = resolve_open_signals(ledger, _EmptyFetcher(), _cfg(tmp_path))
    assert counters["awaiting_fill"] == 1
    assert counters["unfilled"] == 0
    assert len(ledger.open_signals()) == 1, "young signal must stay open"


def test_old_unfilled_signal_finalized(tmp_path):
    """Fill window elapsed (8 x 1m bars) -> finalized as unfilled."""
    from scripts.routines.resolve_signals import resolve_open_signals
    ledger = SignalLedger(tmp_path / "ledger.jsonl")
    old_ms = int(time.time() * 1000) - 10 * 60_000  # 10min ago > 8min window
    sid = _record(ledger, old_ms)
    counters = resolve_open_signals(ledger, _EmptyFetcher(), _cfg(tmp_path))
    assert counters["unfilled"] == 1
    assert counters["awaiting_fill"] == 0
    assert len(ledger.open_signals()) == 0, "old unfilled signal must finalize"


# ---------------------------------------------------------------- item D
def test_routine_result_ok_derived_from_counters(monkeypatch):
    import scripts.routines.resolve_signals as rs
    # high fetch-fail ratio -> ok=False
    monkeypatch.setattr(rs, "main", lambda: {
        "scanned": 10, "fetch_failed": 5, "fetch_fail_alert_pct": 20})
    res = rs._routine_run()
    assert res.ok is False
    # healthy pass -> ok=True
    monkeypatch.setattr(rs, "main", lambda: {
        "scanned": 10, "fetch_failed": 0, "fetch_fail_alert_pct": 20})
    assert rs._routine_run().ok is True
    # disabled skip -> ok=True
    monkeypatch.setattr(rs, "main", lambda: {"skipped": "disabled"})
    assert rs._routine_run().ok is True


# ---------------------------------------------------------------- item I
def test_report_states_empty_ledger():
    from engine.edge_metrics import aggregate
    from scripts.routines.edge_report import build_report
    text = build_report(aggregate([]))
    assert "No signals recorded yet" in text


# ---------------------------------------------------------------- Task 8 (B)
def _minimal_config(tmp_path, enabled=True):
    return {
        "structure": {"swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
                      "eq_threshold_pct": 0.1, "range_lookback": 50},
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {"max_open_positions": 7, "min_rr": 1.8, "min_confluence": 55,
                 "risk_per_trade_pct": 0.75, "recency_bars": 40},
        "safety": {"daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
                   "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
                   "starting_balance": 10000, "max_position_notional_pct": 20,
                   "max_total_exposure": 5.0, "max_holding_hours": 48,
                   "max_pyramid_adds": 2, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
                   "adx_trend_threshold": 25, "adx_range_threshold": 20,
                   "volatile_atr_mult": 2.5, "reverse_min_profit_pct": 0.2},
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "operation": {"check_interval_sec": 30, "log_level": "INFO",
                      "state_dir": str(tmp_path)},
        "signal_ledger": {"enabled": enabled},
    }


def _signal():
    from engine.signals import Signal
    return Signal(direction="LONG", entry=100.0, sl=99.0, tp1=102.0, tp2=103.0,
                  rr1=2.0, rr2=3.0, confluence=70,
                  reasons=["HTF bias"], timestamp="2026-07-03T04:00:00+00:00")


def test_hook_records_signal_when_enabled(tmp_path, monkeypatch):
    monkeypatch.delenv("EFLOUD_SIGNAL_LEDGER_ENABLED", raising=False)
    from engine.safe_orchestrator import SafeOrchestrator
    orc = SafeOrchestrator(_minimal_config(tmp_path, enabled=True),
                           state_dir=str(tmp_path), persist=False)
    sid = orc._ledger_record_signal("BTC/USDT", _signal(),
                                    was_tradeable=True,
                                    htf_bias="BULL", regime="trend")
    assert sid is not None
    assert (tmp_path / "signal_ledger.jsonl").exists()
    rec = orc.signal_ledger.all_signals()[0]
    # item J: seam equality by construction
    assert rec.ts_emitted == rec.brk_ts
    assert rec.was_tradeable is True
    assert rec.htf_bias == "BULL"
    # idempotent dedup: same signal recorded once
    assert orc._ledger_record_signal("BTC/USDT", _signal(),
                                     was_tradeable=True) is None


def test_hook_inert_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("EFLOUD_SIGNAL_LEDGER_ENABLED", raising=False)
    from engine.safe_orchestrator import SafeOrchestrator
    orc = SafeOrchestrator(_minimal_config(tmp_path, enabled=False),
                           state_dir=str(tmp_path), persist=False)
    assert orc._ledger_record_signal("BTC/USDT", _signal(),
                                     was_tradeable=True) is None
    assert orc.signal_ledger is None
    assert not (tmp_path / "signal_ledger.jsonl").exists()


def test_hook_never_raises(tmp_path, monkeypatch):
    """Ledger failure must not touch the trade path (best-effort contract)."""
    monkeypatch.delenv("EFLOUD_SIGNAL_LEDGER_ENABLED", raising=False)
    from engine.safe_orchestrator import SafeOrchestrator
    orc = SafeOrchestrator(_minimal_config(tmp_path, enabled=True),
                           state_dir=str(tmp_path), persist=False)

    class _Boom:
        def record_signal(self, **kw):
            raise RuntimeError("disk full")

    orc.signal_ledger = _Boom()
    assert orc._ledger_record_signal("BTC/USDT", _signal(),
                                     was_tradeable=False) is None
