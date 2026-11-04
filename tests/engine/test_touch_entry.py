"""T-20261104-12: fitil/temas GÖLGE gözlemi (smc_v2.touch_entry: off|shadow; emir yok)."""
import threading
from types import SimpleNamespace

import pandas as pd

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.setup_state import SetupCandidate
from engine.smc_v2.zones import ZoneSpec

TF = 900_000
T0 = 1_700_000_000_000 - (1_700_000_000_000 % TF)


def _df(last_open_ms):
    idx = pd.to_datetime([last_open_ms - TF, last_open_ms], unit="ms")
    return pd.DataFrame({"open": [1.0, 1.0], "high": [1.0, 1.0], "low": [1.0, 1.0],
                         "close": [1.0, 1.0], "volume": [1.0, 1.0]}, index=idx)


def _cand(direction="LONG", state="AWAITING_PULLBACK", low=100.0, high=102.0):
    return SetupCandidate(
        symbol="BTC/USDT", direction=direction, trigger_bar_ts=T0, trigger_price=110.0,
        htf_bias="BULL", target_zone=ZoneSpec(low=low, high=high, source="OB"),
        htf_swing_anchor=95.0, bars_waited=1, state=state, confluence_score=1,
        reasons=["LUX test"],
    )


def _orch(mode="shadow", cands=None):
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"smc_v2": {"touch_entry": mode}, "timeframes": {"entry": "15m"}}
    orch.setup_state_store = SimpleNamespace(candidates=list(cands or []), save=lambda: None)
    orch.persist = False
    orch.instance_mgr = None
    orch._v2_last_df = {"BTC/USDT": _df(T0)}
    orch.placed = []
    orch._place_v2_entry_order = lambda cand, current_price, entry_price, df_entry=None: \
        orch.placed.append((cand.symbol, cand.direction, entry_price))
    orch._v2_po3_blocked = lambda df: False
    return orch


NOW = T0 + TF + 60_000
BAR = T0 + TF


def _shadow_lines(caplog):
    return [r.message for r in caplog.records if "[touch shadow]" in r.message]


def _run(orch, caplog, *a, **k):
    with caplog.at_level("INFO", logger="efloud.safe_orch"):
        return orch.on_intrabar_touch(*a, **k)


def test_off_by_default_does_nothing(caplog):
    c = _cand()
    orch = _orch(cands=[c])
    orch.config["smc_v2"].pop("touch_entry")
    assert orch.touch_entry_mode() == "off"
    assert orch.touch_watch_symbols() == []
    assert _run(orch, caplog, "BTC/USDT", 101.5, 103.0, 101.5, BAR, now_ms=NOW) == 0
    assert _shadow_lines(caplog) == [] and orch.placed == []


def test_live_value_is_not_supported_and_means_off(caplog):
    orch = _orch(mode="live", cands=[_cand()])
    assert orch.touch_entry_mode() == "off"
    assert _run(orch, caplog, "BTC/USDT", 101.5, 103.0, 101.5, BAR, now_ms=NOW) == 0
    assert orch.placed == []


def test_wick_touch_logs_once_never_orders(caplog):
    c = _cand()
    orch = _orch(cands=[c])
    assert orch.touch_watch_symbols() == ["BTC/USDT"]
    assert _run(orch, caplog, "BTC/USDT", price=102.4, bar_high=104.0, bar_low=101.8,
                bar_open_ts=BAR, now_ms=NOW) == 1
    assert _run(orch, caplog, "BTC/USDT", 102.4, 104.0, 101.8, BAR, now_ms=NOW + 1000) == 0
    lines = _shadow_lines(caplog)
    assert len(lines) == 1 and "entry=102 " in lines[0]
    assert f"trigger_bar_ts={T0}" in lines[0] and "bars_waited=1" in lines[0]
    assert c.state == "AWAITING_PULLBACK" and orch.placed == []


def test_short_inside_zone_logs_price(caplog):
    orch = _orch(cands=[_cand(direction="SHORT", state="AWAITING_REENTRY")])
    assert _run(orch, caplog, "BTC/USDT", 100.5, 100.6, 99.0, BAR, now_ms=NOW) == 1
    assert "entry=100.5 " in _shadow_lines(caplog)[0]


def test_no_touch_no_log(caplog):
    orch = _orch(cands=[_cand()])
    assert _run(orch, caplog, "BTC/USDT", 103.0, 104.0, 102.5, BAR, now_ms=NOW) == 0


def test_blown_through_zone_no_log(caplog):
    orch = _orch(cands=[_cand()])
    assert _run(orch, caplog, "BTC/USDT", 99.0, 101.0, 98.5, BAR, now_ms=NOW) == 0


def test_stale_scan_blocks(caplog):
    orch = _orch(cands=[_cand()])
    assert _run(orch, caplog, "BTC/USDT", 101.0, 103.0, 100.8, BAR, now_ms=T0 + 4 * TF) == 0


def test_trigger_bar_itself_ignored(caplog):
    orch = _orch(cands=[_cand()])
    assert _run(orch, caplog, "BTC/USDT", 101.0, 103.0, 100.8, T0, now_ms=NOW) == 0


def test_expired_and_confirmed_skipped(caplog):
    orch = _orch(cands=[_cand(state="EXPIRED"), _cand(state="CONFIRMED")])
    assert orch.touch_watch_symbols() == []
    assert _run(orch, caplog, "BTC/USDT", 101.0, 103.0, 100.8, BAR, now_ms=NOW) == 0


def test_concurrent_touches_log_once():
    orch = _orch(cands=[_cand()])
    results = []
    ts = [threading.Thread(target=lambda: results.append(
        orch.on_intrabar_touch("BTC/USDT", 101.0, 103.0, 100.8, BAR, now_ms=NOW)))
        for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sum(results) == 1 and orch.placed == []
