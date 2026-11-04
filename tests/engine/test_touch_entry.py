"""T-20261104-12: fitil/temas girişi (smc_v2.touch_entry, varsayılan off)."""
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


def _orch(mode="live", cands=None):
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


def test_off_by_default_does_nothing():
    c = _cand()
    orch = _orch(mode=None, cands=[c])
    orch.config["smc_v2"].pop("touch_entry")
    assert orch.touch_entry_mode() == "off"
    assert orch.touch_watch_symbols() == []
    assert orch.on_intrabar_touch("BTC/USDT", 101.5, 103.0, 101.5, BAR, now_ms=NOW) == 0
    assert c.state == "AWAITING_PULLBACK" and orch.placed == []


def test_wick_touch_long_enters_at_zone_edge():
    c = _cand()
    orch = _orch(cands=[c])
    assert orch.touch_watch_symbols() == ["BTC/USDT"]
    n = orch.on_intrabar_touch("BTC/USDT", price=102.4, bar_high=104.0, bar_low=101.8,
                               bar_open_ts=BAR, now_ms=NOW)
    assert n == 1 and c.state == "CONFIRMED"
    assert orch.placed == [("BTC/USDT", "LONG", 102.0)]


def test_price_inside_zone_short_enters_at_price():
    c = _cand(direction="SHORT", state="AWAITING_REENTRY")
    orch = _orch(cands=[c])
    assert orch.on_intrabar_touch("BTC/USDT", 100.5, 100.6, 99.0, BAR, now_ms=NOW) == 1
    assert orch.placed == [("BTC/USDT", "SHORT", 100.5)]


def test_no_touch_no_entry():
    c = _cand()
    orch = _orch(cands=[c])
    assert orch.on_intrabar_touch("BTC/USDT", 103.0, 104.0, 102.5, BAR, now_ms=NOW) == 0
    assert c.state == "AWAITING_PULLBACK"


def test_blown_through_zone_no_entry():
    c = _cand()
    orch = _orch(cands=[c])
    assert orch.on_intrabar_touch("BTC/USDT", 99.0, 101.0, 98.5, BAR, now_ms=NOW) == 0
    assert c.state == "AWAITING_PULLBACK"


def test_no_double_fire():
    c = _cand()
    orch = _orch(cands=[c])
    assert orch.on_intrabar_touch("BTC/USDT", 101.0, 103.0, 100.8, BAR, now_ms=NOW) == 1
    assert orch.on_intrabar_touch("BTC/USDT", 101.0, 103.0, 100.8, BAR, now_ms=NOW + 1000) == 0
    assert len(orch.placed) == 1


def test_shadow_logs_only(caplog):
    c = _cand()
    orch = _orch(mode="shadow", cands=[c])
    with caplog.at_level("INFO", logger="efloud.safe_orch"):
        assert orch.on_intrabar_touch("BTC/USDT", 101.0, 103.0, 100.8, BAR, now_ms=NOW) == 0
        orch.on_intrabar_touch("BTC/USDT", 101.0, 103.0, 100.8, BAR, now_ms=NOW + 1000)
    assert c.state == "AWAITING_PULLBACK" and orch.placed == []
    assert sum("[touch shadow]" in r.message for r in caplog.records) == 1


def test_stale_scan_blocks():
    c = _cand()
    orch = _orch(cands=[c])
    assert orch.on_intrabar_touch("BTC/USDT", 101.0, 103.0, 100.8, BAR,
                                  now_ms=T0 + TF + 3 * TF) == 0
    assert c.state == "AWAITING_PULLBACK"


def test_trigger_bar_itself_ignored():
    c = _cand()
    orch = _orch(cands=[c])
    assert orch.on_intrabar_touch("BTC/USDT", 101.0, 103.0, 100.8, T0, now_ms=NOW) == 0


def test_po3_block_keeps_candidate():
    c = _cand()
    orch = _orch(cands=[c])
    orch._v2_po3_blocked = lambda df: True
    orch._lux_trace_po3 = lambda *a, **k: None
    assert orch.on_intrabar_touch("BTC/USDT", 101.0, 103.0, 100.8, BAR, now_ms=NOW) == 0
    assert c.state == "AWAITING_PULLBACK"


def test_expired_and_confirmed_skipped():
    orch = _orch(cands=[_cand(state="EXPIRED"), _cand(state="CONFIRMED")])
    assert orch.touch_watch_symbols() == []
    assert orch.on_intrabar_touch("BTC/USDT", 101.0, 103.0, 100.8, BAR, now_ms=NOW) == 0


def test_concurrent_touches_place_once():
    c = _cand()
    orch = _orch(cands=[c])
    results = []
    ts = [threading.Thread(target=lambda: results.append(
        orch.on_intrabar_touch("BTC/USDT", 101.0, 103.0, 100.8, BAR, now_ms=NOW)))
        for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sum(results) == 1 and len(orch.placed) == 1
