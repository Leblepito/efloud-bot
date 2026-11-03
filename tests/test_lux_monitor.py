"""scripts/lux_monitor.py + orkestratör [lux] log satırları."""
import io
import json
import logging

import pandas as pd

from scripts import lux_monitor as lm

PLAIN = [
    "2026-11-01 15:00:01,1 | efloud.safe_orch       | INFO  | [lux] scan BTC/USDT htf_bias=BULL ltf_swing=BULL ltf_internal=BEAR last_break=int-CHoCH-BEAR active_obs=4 cands=1 eq=67000.5",
    "2026-11-01 15:00:02,1 | efloud.safe_orch       | INFO  | [lux] setup+ BTC/USDT LONG zone=[66000-66200] sl_anchor=65800 | LUX swing BOS BULL aligned with HTF BULL",
    "2026-11-01 15:00:03,1 | efloud.safe_orch       | INFO  | [v2 gate] ETH/USDT SHORT setup dropped at emit: zone 9.1 ATR away > max_entry_dist_atr 8.0 (src=OB)",
    "2026-11-01 15:30:00,1 | efloud.safe_orch       | INFO  | [v2] LONG BTC/USDT entry=66100.0000 sl=65700.0000 tp1=67000.5000 tp2=68000.0000 size=0.001000 (zone=OB, tp1=LUX_EQUILIBRIUM, tp2=LUX_OB)",
    "2026-11-01 15:31:00,1 | efloud.safe_orch       | INFO  | [v2 reject] SOL/USDT: sl_too_far (x)",
    "2026-11-01 15:32:00,1 | efloud.safe_orch       | INFO  | [lux] expired XRP/USDT SHORT after 49 bars (state was waiting for pullback)",
    "2026-11-01 15:33:00,1 | efloud.engine          | INFO  | unrelated line",
]


def test_parse_plain_and_json_and_filter():
    assert lm.parse_line(PLAIN[-1]) is None
    ts, msg = lm.parse_line(PLAIN[1])
    assert ts.startswith("2026-11-01 15:00:02") and msg.startswith("[lux] setup+")
    js = json.dumps({"ts": "2026-11-01T15:00:00Z", "message": "[lux] scan X htf_bias=BULL"})
    assert lm.parse_line(js) == ("2026-11-01T15:00:00Z", "[lux] scan X htf_bias=BULL")


def test_follow_prints_only_relevant_lines():
    out = io.StringIO()
    n = lm.follow(PLAIN, out=out, color=False)
    assert n == 6
    assert "unrelated" not in out.getvalue()
    assert "ENTRY" in out.getvalue() and "SETUP+" in out.getvalue()


def test_report_aggregates():
    r = lm.build_report(PLAIN)
    assert r["scans"]["BTC/USDT"]["bias"] == "BULL"
    assert r["setups"][("BTC/USDT", "LONG")] == 1
    assert r["gates"]["ETH/USDT"] == 1
    assert r["reject_reasons"]["sl_too_far"] == 1
    assert r["expired"][("XRP/USDT", "SHORT")] == 1
    assert r["entries"][0]["s1"] == "LUX_EQUILIBRIUM"
    txt = lm.render_report(r)
    assert "LuxAlgo hedefi: 1/1" in txt and "BTC/USDT" in txt
    assert "bulunamadı" in lm.render_report(lm.build_report([]))


def test_state_lists_lux_candidates(tmp_path):
    p = tmp_path / "setup_candidates.json"
    p.write_text(json.dumps({"version": 1, "candidates": [
        {"symbol": "BTC/USDT", "direction": "LONG", "state": "IN_ZONE", "bars_waited": 3,
         "target_zone": {"low": 1.0, "high": 2.0, "source": "OB"},
         "htf_swing_anchor": 0.9, "reasons": ["LUX swing BOS BULL aligned with HTF BULL"]},
        {"symbol": "ETH/USDT", "direction": "SHORT", "state": "AWAITING_PULLBACK",
         "bars_waited": 1, "target_zone": {"low": 3.0, "high": 4.0, "source": "OTE"},
         "htf_swing_anchor": 4.5, "reasons": ["CHoCH BEAR aligned"]},
    ]}), encoding="utf-8")
    txt = lm.render_state(str(p))
    assert "BTC/USDT" in txt and "ETH/USDT" not in txt
    assert "ETH/USDT" in lm.render_state(str(p), show_all=True)
    assert "bulunamadı" in lm.render_state(str(tmp_path / "yok.json"))


# ── orkestratör log satırları monitörün regex'leriyle eşleşiyor mu ──

class _Store:
    def add(self, c):
        return True


def test_orchestrator_emits_parsable_lux_lines(caplog):
    from engine.safe_orchestrator import SafeOrchestrator
    from engine.smc_v2 import luxalgo as lx
    from tests.engine.test_luxalgo import _down_then_up, CFG

    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"smc_v2": {"luxalgo": {"enabled": True}}}
    orch.setup_state_store = _Store()
    res = lx.analyze(_down_then_up(), CFG)
    cands = lx.generate_candidates("BTC/USDT", res, "BULL", 0,
                                   require_premium_discount=False)
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        orch._lux_log_scan("BTC/USDT", "BULL", res, cands)
        orch._lux_log_scan("BTC/USDT", "BULL", res, cands)   # değişmedi → basılmaz
        orch._emit_setup_candidates(
            symbol="BTC/USDT", htf_bias="BULL", ltf_structure_breaks=[],
            htf_swings={"swing_highs": [], "swing_lows": []}, htf_bars=[],
            htf_fvgs=[], ote_band=(0.0, 0.0), ltf_trigger_idx_min=0,
            current_price=None, df_entry=None, precomputed_candidates=cands)
    msgs = [r.getMessage() for r in caplog.records]
    scans = [m for m in msgs if m.startswith("[lux] scan")]
    assert len(scans) == 1 and lm.RE_SCAN.search(scans[0])
    setups = [m for m in msgs if m.startswith("[lux] setup+")]
    assert len(setups) == len(cands) and all(lm.RE_SETUP.search(m) for m in setups)
    rep = lm.build_report(msgs)
    assert sum(rep["setups"].values()) == len(cands)


def test_expired_lux_candidate_logs(tmp_path, caplog):
    from engine.safe_orchestrator import SafeOrchestrator
    from engine.smc_v2.setup_state import SetupStateStore, SetupCandidate
    from engine.smc_v2.zones import ZoneSpec
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"smc_v2": {"luxalgo": {"enabled": True, "pullback_timeout_bars": 1}}}
    store = SetupStateStore(path=tmp_path / "c.json")
    c = SetupCandidate("X", "LONG", 0, 100.0, "BULL", ZoneSpec(50.0, 51.0, "OB"),
                       49.0, 0, "AWAITING_PULLBACK", 0, ["LUX swing BOS BULL"])
    store.candidates = [c]
    orch.setup_state_store = store
    df = pd.DataFrame({"open": [100.0] * 20, "high": [101.0] * 20,
                       "low": [99.0] * 20, "close": [100.0] * 20})
    with caplog.at_level(logging.INFO, logger="efloud.safe_orch"):
        for i in range(3):
            orch._advance_setup_state_tick(symbol="X", current_price=100.0,
                                           current_bar_ts=1_700_000_000_000 + i * 900_000,
                                           df_15m=df)
    assert c.state == "EXPIRED"
    assert any(lm.RE_EXPIRED.search(r.getMessage()) for r in caplog.records)
