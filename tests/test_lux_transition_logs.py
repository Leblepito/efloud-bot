"""[lux] state-transition log lines (observability only — no behaviour change).

Why: on 2026-11-04 the mid bot ran ~132 cycles with LuxAlgo setups pending and no
entry. The only lux lines were `setup+` and `expired`, so nobody could tell
whether a setup never reached its order block, touched it without an engulfing
confirmation, or was held back by the Po3 gate. These tests pin one INFO line per
transition for LuxAlgo candidates and check that the state machine itself is
unchanged.
"""
import logging

import pandas as pd

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
from engine.smc_v2.zones import ZoneSpec
from scripts import lux_monitor as lm

BAR0 = 1_700_000_000_000
BAR = 900_000


def _orch(tmp_path, cands):
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"smc_v2": {"luxalgo": {"enabled": True, "pullback_timeout_bars": 100}}}
    store = SetupStateStore(path=tmp_path / "c.json")
    store.candidates = list(cands)
    orch.setup_state_store = store
    orch.placed = []
    orch._place_v2_entry_order = lambda cand, **kw: orch.placed.append((cand.symbol, kw))
    return orch


def _cand(reason="LUX swing BOS BULL aligned with HTF BULL"):
    return SetupCandidate("X", "LONG", 0, 100.0, "BULL", ZoneSpec(50.0, 51.0, "OB"),
                          49.0, 0, "AWAITING_PULLBACK", 0, [reason])


def _df(engulf: bool):
    idx = pd.date_range("2026-11-04", periods=3, freq="15min", tz="UTC")
    if engulf:   # prior bearish inside zone, then bullish engulfing closing inside zone
        o, c = [55.0, 50.9, 50.1], [55.0, 50.2, 50.95]
    else:
        o, c = [55.0, 50.9, 50.6], [55.0, 50.5, 50.4]
    return pd.DataFrame({"open": o, "high": [max(a, b) + 0.01 for a, b in zip(o, c)],
                         "low": [min(a, b) - 0.01 for a, b in zip(o, c)], "close": c}, index=idx)


def _tick(orch, price, bar, df):
    orch._advance_setup_state_tick(symbol="X", current_price=price,
                                   current_bar_ts=BAR0 + bar * BAR, df_15m=df)


def _lux_msgs(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("[lux] ")]


def test_touch_left_reentry_are_logged_and_states_unchanged(tmp_path, caplog):
    c = _cand()
    orch = _orch(tmp_path, [c])
    df = _df(engulf=False)
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 50.5, 0, df)
        assert c.state == "IN_ZONE"
        _tick(orch, 55.0, 1, df)
        assert c.state == "AWAITING_REENTRY" and c.has_left_zone
        _tick(orch, 50.5, 2, df)
        assert c.state == "IN_ZONE"
    msgs = _lux_msgs(caplog)
    events = [lm.RE_TRACE.search(m)["event"] for m in msgs if lm.RE_TRACE.search(m)]
    assert events == ["touch", "left", "reentry"]
    assert orch.placed == []
    assert "zone=[50-51]" in msgs[0] and "price=50.5" in msgs[0]


def test_confirmed_is_logged_before_the_order_path(tmp_path, caplog):
    c = _cand()
    orch = _orch(tmp_path, [c])
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 50.5, 0, _df(engulf=True))     # touch
        _tick(orch, 50.95, 0, _df(engulf=True))    # same bar, engulfing found
    assert c.state == "CONFIRMED" and len(orch.placed) == 1
    events = [lm.RE_TRACE.search(m)["event"] for m in _lux_msgs(caplog) if lm.RE_TRACE.search(m)]
    assert events == ["touch", "confirmed"]


def test_po3_block_is_logged_once_per_bar_and_setup_survives(tmp_path, caplog):
    c = _cand()
    orch = _orch(tmp_path, [c])
    orch._v2_po3_blocked = lambda df: True
    df = _df(engulf=True)
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 50.5, 0, df)        # touch
        _tick(orch, 50.5, 0, df)        # confirmed but blocked -> logged
        _tick(orch, 50.5, 0, df)        # same bar -> not logged again
        _tick(orch, 50.5, 1, df)        # new bar, still blocked -> logged
    assert c.state == "IN_ZONE" and orch.placed == []
    events = [lm.RE_TRACE.search(m)["event"] for m in _lux_msgs(caplog) if lm.RE_TRACE.search(m)]
    assert events == ["touch", "po3-block", "po3-block"]


def test_non_lux_candidates_stay_silent(tmp_path, caplog):
    c = _cand(reason="CHoCH BULL aligned")
    orch = _orch(tmp_path, [c])
    df = _df(engulf=False)
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 50.5, 0, df)
        _tick(orch, 55.0, 1, df)
    assert c.state == "AWAITING_REENTRY"
    assert _lux_msgs(caplog) == []


def test_report_has_a_funnel_from_setup_to_entry():
    lines = [
        "2026-11-04 10:00:00,1 | efloud.safe_orch | INFO  | [lux] setup+ X/USDT LONG zone=[1-2] sl_anchor=0.9 | LUX swing BOS BULL",
        "2026-11-04 10:15:00,1 | efloud.safe_orch | INFO  | [lux] touch X/USDT LONG bars=1 price=1.5 zone=[1-2]",
        "2026-11-04 10:30:00,1 | efloud.safe_orch | INFO  | [lux] left X/USDT LONG bars=2 price=2.5 zone=[1-2]",
        "2026-11-04 10:45:00,1 | efloud.safe_orch | INFO  | [lux] reentry X/USDT LONG bars=3 price=1.5 zone=[1-2]",
        "2026-11-04 11:00:00,1 | efloud.safe_orch | INFO  | [lux] po3-block X/USDT LONG bars=4 price=1.5 zone=[1-2]",
        "2026-11-04 11:15:00,1 | efloud.safe_orch | INFO  | [lux] confirmed X/USDT LONG bars=5 price=1.6 zone=[1-2] | entry=1.6",
        "2026-11-04 11:15:01,1 | efloud.safe_orch | INFO  | [v2 reject] X/USDT: sl_too_far (x)",
    ]
    r = lm.build_report(lines)
    assert r["trace"]["touch"] == 1 and r["trace"]["confirmed"] == 1
    assert r["trace"]["po3-block"] == 1
    txt = lm.render_report(r)
    assert "HUNİ" in txt
    assert "touch 1" in txt and "confirmed 1" in txt and "red 1" in txt
    assert lm.classify(lines[1].split(" | ")[3]) == "trace"


# ── T-20261104-08: "[lux] near" early-warning line (log only, default OFF) ──

def _flat_df(n=20, mid=52.0):
    """Every bar has range 1.0 and no gaps → Wilder ATR(14) == 1.0."""
    idx = pd.date_range("2026-11-04", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": [mid] * n, "high": [mid + 0.5] * n,
                         "low": [mid - 0.5] * n, "close": [mid] * n}, index=idx)


def _near_msgs(caplog):
    return [m for m in _lux_msgs(caplog) if m.startswith("[lux] near ")]


def test_near_line_is_off_by_default(tmp_path, caplog):
    c = _cand()
    orch = _orch(tmp_path, [c])
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 51.8, 0, _flat_df())
    assert _near_msgs(caplog) == []
    assert c.state == "AWAITING_PULLBACK"


def test_near_line_logged_once_within_threshold_and_states_unchanged(tmp_path, caplog):
    c = _cand()
    orch = _orch(tmp_path, [c])
    orch.config["smc_v2"]["luxalgo"]["near_alert_atr"] = 1.0
    df = _flat_df()
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 53.0, 0, df)        # 2.0 ATR above zone high -> silent
        _tick(orch, 51.8, 1, df)        # 0.8 ATR -> near
        _tick(orch, 51.6, 2, df)        # still near -> not repeated
        _tick(orch, 50.5, 3, df)        # inside zone -> touch (unchanged path)
    near = _near_msgs(caplog)
    assert len(near) == 1
    assert "X LONG" in near[0] and "zone=[50-51]" in near[0] and "dist=0.80 ATR" in near[0]
    assert c.state == "IN_ZONE" and orch.placed == []
    events = [lm.RE_TRACE.search(m)["event"] for m in _lux_msgs(caplog) if lm.RE_TRACE.search(m)]
    assert events == ["touch"]


def test_near_line_short_measures_distance_below_zone_low(tmp_path, caplog):
    c = SetupCandidate("X", "SHORT", 0, 40.0, "BEAR", ZoneSpec(53.0, 54.0, "OB"),
                       54.5, 0, "AWAITING_PULLBACK", 0, ["LUX internal CHoCH BEAR aligned with HTF BEAR"])
    orch = _orch(tmp_path, [c])
    orch.config["smc_v2"]["luxalgo"]["near_alert_atr"] = 1.0
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 52.5, 0, _flat_df())   # 0.5 ATR below zone low
    near = _near_msgs(caplog)
    assert len(near) == 1 and "dist=0.50 ATR" in near[0]


def test_near_line_skipped_without_atr(tmp_path, caplog):
    c = _cand()
    orch = _orch(tmp_path, [c])
    orch.config["smc_v2"]["luxalgo"]["near_alert_atr"] = 1.0
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 51.8, 0, _df(engulf=False))   # 3 bars -> ATR not computable
    assert _near_msgs(caplog) == []


def test_bad_near_alert_atr_value_never_breaks_the_state_machine(tmp_path, caplog):
    """A config typo in a log-only knob must not abort the trading tick."""
    c = _cand()
    orch = _orch(tmp_path, [c])
    orch.config["smc_v2"]["luxalgo"]["near_alert_atr"] = "1.0x"
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 51.8, 0, _flat_df())
        _tick(orch, 50.5, 1, _flat_df())
    assert c.state == "IN_ZONE" and c.bars_waited == 2
    assert _near_msgs(caplog) == []


def test_near_line_not_logged_right_after_leaving_the_zone(tmp_path, caplog):
    """AWAITING_REENTRY is next to the edge it just left — 'approaching' would mislead."""
    c = _cand()
    orch = _orch(tmp_path, [c])
    orch.config["smc_v2"]["luxalgo"]["near_alert_atr"] = 1.0
    df = _flat_df()
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 50.5, 0, df)    # touch
        _tick(orch, 51.5, 1, df)    # left, 0.5 ATR above zone
        _tick(orch, 51.5, 2, df)    # still outside, waiting for re-entry
    assert c.state == "AWAITING_REENTRY"
    assert _near_msgs(caplog) == []


def test_orchestrator_lux_lines_match_the_alerter_rule(tmp_path, caplog, monkeypatch):
    """Contract: the exact lines the engine writes are the lines the alerter parses."""
    from ops.alerter.rules import LuxZoneAlertRule
    monkeypatch.setenv("EFLOUD_ALERTER_LUX_ALERTS", "1")
    c = _cand()
    orch = _orch(tmp_path, [c])
    orch.config["smc_v2"]["luxalgo"]["near_alert_atr"] = 1.0
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 51.8, 0, _flat_df())            # near
        _tick(orch, 50.5, 1, _df(engulf=True))      # touch
        _tick(orch, 50.95, 1, _df(engulf=True))     # confirmed
    rule = LuxZoneAlertRule()
    fired = [rule.match_log({"level": "INFO", "logger": "efloud.safe_orch", "message": m})
             for m in _lux_msgs(caplog)]
    assert [f is not None for f in fired] == [True, True, True]


def test_exception_inside_near_block_never_breaks_the_state_machine(tmp_path, caplog, monkeypatch):
    """The near trace is observability only: if it raises, the tick still advances."""
    import engine.smc_v2.atr as atr_mod
    monkeypatch.setattr(atr_mod, "wilder_atr", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    c = _cand()
    orch = _orch(tmp_path, [c])
    orch.config["smc_v2"]["luxalgo"]["near_alert_atr"] = 1.0
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 51.8, 0, _flat_df())
        _tick(orch, 50.5, 1, _flat_df())
    assert c.state == "IN_ZONE" and c.bars_waited == 2
    assert _near_msgs(caplog) == []


def test_huge_near_alert_atr_value_is_treated_as_off(tmp_path, caplog):
    c = _cand()
    orch = _orch(tmp_path, [c])
    orch.config["smc_v2"]["luxalgo"]["near_alert_atr"] = 10 ** 400
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        _tick(orch, 51.8, 0, _flat_df())
    assert c.state == "AWAITING_PULLBACK" and c.bars_waited == 1
