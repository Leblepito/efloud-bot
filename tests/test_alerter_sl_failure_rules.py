"""SL protection failures → Telegram (T-20261107-05).

Alerter-only (no trading code). The exchange layer already logs structured
events (extras land in the JSON log line via utils/logging.JsonFormatter):

  CRITICAL, re-alert every 15 min while it persists (SlUnprotectedRule):
    - tp_placement_failed_after_sl, tp_leg=SL_REPAIR — SL re-send failed;
      the position stays open WITHOUT a stop and the reconcile repair loop
      tries again every cycle (2026-05-14 bare-position failure mode).
    - entry_rollback_failed — entry filled, SL could not be placed, and the
      rollback market close failed too; the bot no longer tracks it.
    - fallback_close_failed, reason=SL_REPAIR_UNREACHABLE — price is past the
      SL and the market close failed; position open and unprotected.

  Informational, once per hour (SlProtectionEventRule):
    - repair_missing_sl — SL missing on the exchange, re-send attempted now.
    - sl_repair_unreachable_closing — price past SL; closing at market.
    - entry_rollback_after_sl_failure — SL could not be placed (open or
      post-placement verify); the entry was rolled back.

Default OFF (EFLOUD_ALERTER_SL_ALERTS).
"""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from ops.alerter.rules import RULES, SlProtectionEventRule, SlUnprotectedRule, TpPlacementFailedRule

FLAG = "EFLOUD_ALERTER_SL_ALERTS"
SL_FAILED = "order_manager.tp_placement_failed_after_sl"
ROLLBACK_FAILED = "order_manager.entry_rollback_failed"
CLOSE_FAILED = "order_manager.fallback_close_failed"
MISSING = "order_manager.repair_missing_sl"
CLOSING = "order_manager.sl_repair_unreachable_closing"
ROLLED_BACK = "order_manager.entry_rollback_after_sl_failure"


def _rec(event, level="CRITICAL", logger="efloud.exchange", **kw):
    rec = {"level": level, "logger": logger, "message": f"{event}: BTC/USDT LONG",
           "event": event, "symbol": "BTC/USDT", "direction": "LONG"}
    rec.update(kw)
    return rec


def _sl_failed(**kw):
    base = dict(level="WARNING", tp_leg="SL_REPAIR", entry_order_id="ENTRY-1",
                error="Request timed out", attempt=3, max_attempts=3, retryable=True)
    base.update(kw)
    return _rec(SL_FAILED, **base)


UNPROTECTED = [
    _sl_failed(),
    _rec(ROLLBACK_FAILED, entry_order_id="ENTRY-1", original_error="SL placement exhausted after retries",
         rollback_error="Service unavailable"),
    _rec(CLOSE_FAILED, reason="SL_REPAIR_UNREACHABLE",
         message="order_manager.fallback_close_failed: BTC/USDT LONG reason=SL_REPAIR_UNREACHABLE "
                 "error=Service unavailable — aborting cleanup; SL/TP siblings and tracking PRESERVED"),
]
EVENTS = [
    _rec(MISSING),
    _rec(CLOSING),
    _rec(ROLLED_BACK, entry_order_id="ENTRY-1", rollback_order_id="RB-1",
         original_error="SL unconfirmed after post-placement verify"),
]


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(FLAG, "1")


def test_rules_are_registered():
    kinds = {type(r) for r in RULES}
    assert SlUnprotectedRule in kinds and SlProtectionEventRule in kinds


@pytest.mark.parametrize("rec", UNPROTECTED + EVENTS)
def test_default_off_matches_nothing(monkeypatch, rec):
    monkeypatch.delenv(FLAG, raising=False)
    assert SlUnprotectedRule().match_log(rec) is None
    assert SlProtectionEventRule().match_log(rec) is None


def test_windows_and_format():
    u, e = SlUnprotectedRule(), SlProtectionEventRule()
    assert u.dedup_window_sec == 15 * 60 and u.severity == "CRITICAL"
    assert e.dedup_window_sec == 60 * 60
    assert u.ai_format is False and e.ai_format is False


@pytest.mark.parametrize("rec", UNPROTECTED)
def test_unprotected_events_fire_only_on_unprotected_rule(on, rec):
    out = SlUnprotectedRule().match_log(rec)
    assert out is not None and "BTC/USDT LONG" in out
    assert SlProtectionEventRule().match_log(rec) is None


@pytest.mark.parametrize("rec", EVENTS)
def test_info_events_fire_only_on_event_rule(on, rec):
    out = SlProtectionEventRule().match_log(rec)
    assert out is not None and "BTC/USDT LONG" in out
    assert SlUnprotectedRule().match_log(rec) is None


def test_sl_repair_failure_wording(on):
    out = SlUnprotectedRule().match_log(_sl_failed())
    assert "STOP'SUZ" in out and "3/3" in out and "Request timed out" in out
    assert "her reconcile döngüsünde" in out and "15 dakikada" in out


def test_sl_repair_permanent_error_has_no_counter(on):
    out = SlUnprotectedRule().match_log(_sl_failed(attempt=1, retryable=False, error="insufficient margin"))
    assert "1/3" not in out and "kalıcı hata" in out


def test_rollback_failed_wording(on):
    out = SlUnprotectedRule().match_log(UNPROTECTED[1])
    assert "takip etmiyor" in out and "Service unavailable" in out
    assert "Binance" in out


def test_close_failed_only_for_sl_repair_unreachable(on):
    rec = dict(UNPROTECTED[2], reason="KILL_SWITCH")
    assert SlUnprotectedRule().match_log(rec) is None


def test_rollback_success_shows_cause(on):
    out = SlProtectionEventRule().match_log(EVENTS[2])
    assert "geri alındı" in out and "post-placement verify" in out and "RB-1" in out


@pytest.mark.parametrize("rec", [
    _sl_failed(tp_leg="SL"),        # initial SL at open: rollback events report the outcome
    _sl_failed(tp_leg="TP1"),       # TP legs: TpPlacementFailedRule
    _rec("order_manager.tp_unreachable", tp_leg="SL_REPAIR"),  # followed by sl_repair_unreachable_closing
    _rec(MISSING, logger="efloud.safe_orch"),
    {"level": "CRITICAL", "logger": "efloud.exchange", "message": "unrelated"},
])
def test_non_matching_records_ignored(on, rec):
    assert SlUnprotectedRule().match_log(rec) is None
    assert SlProtectionEventRule().match_log(rec) is None


def test_html_escaped(on):
    out = SlUnprotectedRule().match_log(_sl_failed(error="{'msg': '<x> & y'}"))
    assert "<x>" not in out and "&lt;x&gt;" in out and "&amp;" in out


def test_dedup_key_per_position():
    u = SlUnprotectedRule()
    k = u.dedup_key(_sl_failed())
    assert u.dedup_key(_sl_failed(entry_order_id="ENTRY-2")) != k
    assert u.dedup_key(_sl_failed(symbol="ETH/USDT")) != k
    assert u.dedup_key(UNPROTECTED[1]) != k, "different failure kinds keep separate windows"


def test_tp_rule_still_ignores_sl_legs(monkeypatch):
    monkeypatch.setenv("EFLOUD_ALERTER_TP_ALERTS", "1")
    monkeypatch.setenv(FLAG, "1")
    assert TpPlacementFailedRule().match_log(_sl_failed()) is None


# ── Contract with the real exchange log output ──

class _JsonCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        from utils.logging import JsonFormatter
        self.setFormatter(JsonFormatter())
        self.records: list[dict] = []

    def emit(self, record):
        self.records.append(json.loads(self.format(record)))


def _order_manager():
    from exchange import BinanceClient, OrderManager
    client = MagicMock(spec=BinanceClient)
    client.exchange = MagicMock()
    client.exchange.price_to_precision = MagicMock(side_effect=lambda s, p: p)
    client.exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: a)
    client.market_type = "futures"
    client.testnet = True
    client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    om = OrderManager(client, dry_run=False)
    om._persist = MagicMock()
    return client, om


def _fired(records):
    rules = (SlUnprotectedRule(), SlProtectionEventRule())
    out = []
    for rec in records:
        for rule in rules:
            if rule.match_log(rec):
                out.append((type(rule).__name__, rec["event"], rule.dedup_key(rec)))
    return out


def _capture(fn):
    cap = _JsonCapture()
    exlog = logging.getLogger("efloud.exchange")
    exlog.addHandler(cap)
    try:
        with patch("exchange._time.sleep"):
            fn()
    finally:
        exlog.removeHandler(cap)
    return cap.records


def _open(om):
    return om.open_position("BTC/USDT", "LONG", 1.0, entry=95000, sl=94000, tp1=96000, tp2=97000)


@pytest.mark.parametrize("rollback_result,expected", [
    ({"id": "RB-1"}, ("SlProtectionEventRule", ROLLED_BACK)),
    (RuntimeError("Service unavailable"), ("SlUnprotectedRule", ROLLBACK_FAILED)),
])
def test_contract_open_sl_failure(on, rollback_result, expected):
    client, om = _order_manager()
    client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "filled": 1.0},
        ValueError("insufficient margin"),   # SL, non-transient
        rollback_result,
    ]
    records = _capture(lambda: _open(om))
    fired = _fired(records)
    assert [(f[0], f[1]) for f in fired] == [expected]
    assert "ENTRY-1" in fired[0][2]


def _tracked_pos(om, sl_order_id=""):
    from exchange import Position
    pos = Position(symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
                   tp1=96000, tp2=97000, size=1.0, order_id="ENTRY-1",
                   sl_order_id=sl_order_id, tp1_order_id="TP1-1", tp2_order_id="TP2-1")
    om.positions.append(pos)
    return pos


def test_contract_sl_repair_failure_is_unprotected(on):
    client, om = _order_manager()
    _tracked_pos(om)
    client.exchange.create_order.side_effect = ValueError("insufficient margin")
    records = _capture(lambda: om._repair_missing_protection_orders({"TP1-1", "TP2-1"}))
    fired = [(f[0], f[1]) for f in _fired(records)]
    assert fired == [("SlProtectionEventRule", MISSING), ("SlUnprotectedRule", SL_FAILED)]


def test_contract_sl_repair_unreachable_close_failed(on):
    client, om = _order_manager()
    _tracked_pos(om)
    client.exchange.create_order.side_effect = [
        Exception('binance {"code":-2021,"msg":"Order would immediately trigger."}'),  # SL_REPAIR
        RuntimeError("Service unavailable"),                                            # market close
    ]
    records = _capture(lambda: om._repair_missing_protection_orders({"TP1-1", "TP2-1"}))
    fired = [(f[0], f[1]) for f in _fired(records)]
    assert fired == [("SlProtectionEventRule", MISSING),
                     ("SlProtectionEventRule", CLOSING),
                     ("SlUnprotectedRule", CLOSE_FAILED)]


def test_contract_verify_rollback(on):
    client, om = _order_manager()
    pos = _tracked_pos(om, sl_order_id="SL-1")
    om.enable_post_placement_verify = True
    om.verify_delay_sec = 0
    om.verify_max_attempts = 1
    om.rollback_on_sl_failure = True
    client.exchange.create_order.side_effect = [
        ValueError("insufficient margin"),   # SL re-place inside verify
        {"id": "RB-1"},                      # rollback market close
    ]
    with patch.object(om, "_fetch_protection_order_ids", return_value=({"TP1-1", "TP2-1"}, True)), \
         patch.object(om, "_cancel_position_siblings", return_value={}):
        records = _capture(lambda: om._verify_and_repair_protection(pos))
    fired = _fired(records)
    assert [(f[0], f[1]) for f in fired] == [("SlProtectionEventRule", ROLLED_BACK)]
    rolled = next(r for r in records if r.get("event") == ROLLED_BACK)
    assert "post-placement verify" in rolled["original_error"]
