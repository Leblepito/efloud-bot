"""TP placement failure → Telegram (T-20261107-03).

The exchange layer already emits structured log events when a TP order cannot
be placed (`_retry_tp_order`):

  - ``order_manager.tp_placement_failed_after_sl`` (WARNING) — retries
    exhausted or a non-transient error; the reconcile repair loop re-tries.
  - ``order_manager.tp_unreachable`` (CRITICAL) — Binance -2021, price is
    already past the TP; the bot stores a sentinel and does NOT retry.

The alerter tails the bot's JSON log; this rule turns those events into an
operator message. Alerter-only: no trading code involved. Default OFF
(EFLOUD_ALERTER_TP_ALERTS).
"""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from ops.alerter.rules import RULES, TpPlacementFailedRule

FLAG = "EFLOUD_ALERTER_TP_ALERTS"
FAILED = "order_manager.tp_placement_failed_after_sl"
UNREACHABLE = "order_manager.tp_unreachable"


def _rec(event=FAILED, leg="TP1", level="WARNING", logger="efloud.exchange", **kw):
    rec = {"level": level, "logger": logger, "message": f"{event}: BTC/USDT LONG tp_leg={leg}",
           "event": event, "symbol": "BTC/USDT", "direction": "LONG", "tp_leg": leg,
           "error": "Request timed out", "attempt": 3, "max_attempts": 3,
           "retryable": True, "entry_order_id": "ENTRY-1"}
    rec.update(kw)
    return rec


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(FLAG, "1")


def test_rule_is_registered():
    assert any(isinstance(r, TpPlacementFailedRule) for r in RULES)


def test_default_off_matches_nothing(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert TpPlacementFailedRule().match_log(_rec()) is None
    assert TpPlacementFailedRule().match_log(_rec(UNREACHABLE, level="CRITICAL")) is None


@pytest.mark.parametrize("leg", ["TP1", "TP2", "TP1_REPAIR", "TP2_REPAIR"])
def test_failed_tp_leg_fires(on, leg):
    out = TpPlacementFailedRule().match_log(_rec(leg=leg))
    assert out is not None
    assert "BTC/USDT LONG" in out and leg in out and "3/3" in out
    assert "Request timed out" in out
    assert "yeniden dener" in out


def test_non_retryable_error_has_no_attempt_counter(on):
    out = TpPlacementFailedRule().match_log(
        _rec(error="insufficient margin", attempt=1, retryable=False))
    assert out is not None
    assert "1/3" not in out
    assert "kalıcı hata" in out
    assert "insufficient margin" in out


def test_failed_wording_scopes_retry_to_open_position(on):
    out = TpPlacementFailedRule().match_log(_rec())
    assert "pozisyon açık kaldığı sürece" in out


def test_unreachable_tp_fires_with_no_retry_wording(on):
    out = TpPlacementFailedRule().match_log(_rec(UNREACHABLE, level="CRITICAL", attempt=None))
    assert out is not None
    assert "BTC/USDT LONG" in out and "TP1" in out
    assert "yeniden denemez" in out.lower()


@pytest.mark.parametrize("rec", [
    _rec(leg="SL"),                                   # SL legs: separate fail-closed paths
    _rec(leg="SL_REPAIR"),
    _rec(event="order_manager.repair_missing_tp", level="CRITICAL"),  # attempt, not failure
    _rec(logger="efloud.safe_orch"),
    {"level": "WARNING", "logger": "efloud.exchange", "message": "unrelated"},
])
def test_non_matching_records_ignored(on, rec):
    assert TpPlacementFailedRule().match_log(rec) is None


def test_error_text_is_html_escaped(on):
    out = TpPlacementFailedRule().match_log(_rec(error="binance {'code': -1, 'msg': '<x> & y'}"))
    assert "<x>" not in out and "&lt;x&gt;" in out and "&amp;" in out


def test_dedup_key_per_position_leg_and_kind():
    r = TpPlacementFailedRule()
    k_open = r.dedup_key(_rec(leg="TP1"))
    k_repair = r.dedup_key(_rec(leg="TP1_REPAIR"))
    assert k_open == k_repair, "initial failure + repeated repair failures share one window"
    assert r.dedup_key(_rec(leg="TP2")) != k_open
    assert r.dedup_key(_rec(symbol="ETH/USDT")) != k_open
    assert r.dedup_key(_rec(direction="SHORT")) != k_open
    assert r.dedup_key(_rec(UNREACHABLE, level="CRITICAL")) != k_open
    assert r.dedup_key(_rec(entry_order_id="ENTRY-2")) != k_open, (
        "a new position on the same symbol+direction within the hour must still alert")
    assert r.dedup_window_sec == 60 * 60
    assert r.ai_format is False


# ── Contract with the real exchange log output (guards against format drift) ──

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
    return client, OrderManager(client, dry_run=False)


@pytest.mark.parametrize("tp1_errors,expected_event", [
    ([RuntimeError("Request timed out")] * 3, FAILED),      # transient, retries exhausted
    ([ValueError("insufficient margin")], FAILED),          # non-transient, no retry
    ([Exception('binance {"code":-2021,"msg":"Order would immediately trigger."}')],
     UNREACHABLE),
])
def test_real_exchange_log_line_matches_rule(on, tp1_errors, expected_event):
    client, om = _order_manager()
    client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "filled": 1.0}, {"id": "SL-1"},
        *tp1_errors,
        {"id": "TP2-1"},
    ]
    cap = _JsonCapture()
    exlog = logging.getLogger("efloud.exchange")
    exlog.addHandler(cap)
    try:
        with patch("exchange._time.sleep"):
            pos = om.open_position("BTC/USDT", "LONG", 1.0,
                                   entry=95000, sl=94000, tp1=96000, tp2=97000)
    finally:
        exlog.removeHandler(cap)
    assert pos is not None

    rule = TpPlacementFailedRule()
    fired = [(rec, rule.match_log(rec)) for rec in cap.records]
    fired = [(rec, txt) for rec, txt in fired if txt]
    assert len(fired) == 1, [r.get("event") for r in cap.records]
    rec, text = fired[0]
    assert rec["event"] == expected_event
    assert rec["entry_order_id"] == "ENTRY-1", "dedup key relies on this extra"
    assert "BTC/USDT LONG" in text and "TP1" in text
