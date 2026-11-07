"""Recurring Telegram alert while an orphan position exists (T-20261107-11).

`OrderManager.reconcile()` logs `ORPHAN POSITION DETECTED: <SYM> <side> qty=..
entry=.. upnl=..` (free text, WARNING, logger efloud.exchange) on EVERY cycle
while the exchange holds a position the bot does not track. The one-shot
`entry_rollback_failed` alert (#314) can be lost if its Telegram send fails;
this rule re-alerts once per hour per (symbol, side) for as long as the
orphan line keeps appearing, so an untracked live position cannot go
unnoticed. Alerter-only; gated by EFLOUD_ALERTER_SL_ALERTS (default OFF).
"""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from ops.alerter.rules import RULES, OrphanPositionRule

FLAG = "EFLOUD_ALERTER_SL_ALERTS"
LINE = ("⚠️  ORPHAN POSITION DETECTED: BTC/USDT long qty=0.5 entry=95000.0 upnl=-12.5 "
        "— NOT in local state. Bot will NOT manage SL/TP for this position. "
        "Manual reconcile required if this was a bot-opened trade.")
NO_DETAILS = "⚠️  ORPHAN POSITION DETECTED: ETH/USDT — details unavailable"


def _rec(msg=LINE, level="WARNING", logger="efloud.exchange"):
    return {"level": level, "logger": logger, "message": msg}


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(FLAG, "1")


def test_rule_is_registered():
    assert any(isinstance(r, OrphanPositionRule) for r in RULES)


def test_default_off(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert OrphanPositionRule().match_log(_rec()) is None


def test_fires_with_details(on):
    out = OrphanPositionRule().match_log(_rec())
    assert out is not None
    assert "BTC/USDT long" in out and "0.5" in out and "95000.0" in out and "-12.5" in out
    assert "takip etmiyor" in out and "saatte bir" in out


def test_fires_without_details(on):
    out = OrphanPositionRule().match_log(_rec(NO_DETAILS))
    assert out is not None and "ETH/USDT" in out


@pytest.mark.parametrize("rec", [
    _rec(logger="efloud.safe_orch"),
    _rec(msg="Reconcile: positions fetch failed: boom"),
    _rec(msg="orphan_protect[BTC/USDT]: placed_sl sl=93100.0", level="INFO"),
])
def test_non_matching_ignored(on, rec):
    assert OrphanPositionRule().match_log(rec) is None


def test_html_escaped(on):
    out = OrphanPositionRule().match_log(_rec(
        "⚠️  ORPHAN POSITION DETECTED: <X>&Y long qty=1 entry=1 upnl=0 — NOT in local state."))
    assert "<X>" not in out and "&lt;X&gt;&amp;Y" in out


IGNORE = "EFLOUD_ALERTER_ORPHAN_IGNORE_SYMBOLS"


@pytest.mark.parametrize("ignore", ["BTC/USDT", "btcusdt", " eth/usdt , BTCUSDT ", "BTC/USDT:USDT"])
def test_ignore_list_mutes_deliberate_manual_position(on, monkeypatch, ignore):
    monkeypatch.setenv(IGNORE, ignore)
    assert OrphanPositionRule().match_log(_rec()) is None


def test_ignore_list_only_mutes_listed_symbols(on, monkeypatch):
    monkeypatch.setenv(IGNORE, "ETH/USDT")
    assert OrphanPositionRule().match_log(_rec()) is not None
    assert OrphanPositionRule().match_log(_rec(NO_DETAILS)) is None


def test_ignore_list_empty_by_default(on, monkeypatch):
    monkeypatch.setenv(IGNORE, "")
    assert OrphanPositionRule().match_log(_rec()) is not None


def test_text_names_protection_mode(on):
    out = OrphanPositionRule().match_log(_rec())
    assert "place_missing_sl" in out and "warn_only" in out


def test_dedup_per_symbol_and_side_hourly():
    r = OrphanPositionRule()
    k = r.dedup_key(_rec())
    assert r.dedup_key(_rec(LINE.replace("BTC/USDT", "SOL/USDT"))) != k
    assert r.dedup_key(_rec(LINE.replace(" long ", " short "))) != k
    assert r.dedup_key(_rec(LINE.replace("qty=0.5", "qty=0.7"))) == k, "qty/upnl drift must not re-alert"
    assert r.dedup_window_sec == 60 * 60
    assert r.ai_format is False and r.severity == "CRITICAL"


# ── Contract: the real reconcile path emits the line this rule matches ──

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


def test_contract_rollback_failure_then_reconcile_reports_orphan_every_cycle(on):
    """entry fills, SL fails, rollback close fails → bot drops the position;
    every following reconcile logs the orphan line and the rule matches it."""
    client, om = _order_manager()
    client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "filled": 0.5},
        ValueError("insufficient margin"),        # SL
        RuntimeError("Service unavailable"),      # rollback close
    ]
    _capture(lambda: om.open_position("BTC/USDT", "LONG", 0.5, entry=95000, sl=94000,
                                      tp1=96000, tp2=97000))
    assert om.positions == []

    client.get_open_positions = MagicMock(return_value=[
        {"symbol": "BTC/USDT:USDT", "side": "long", "contracts": 0.5,
         "entryPrice": 95000.0, "unrealizedPnl": -12.5}])
    client.exchange.fetch_open_orders = MagicMock(return_value=[])
    client.exchange.fapiPrivateGetOpenAlgoOrders = MagicMock(return_value=[])

    rule = OrphanPositionRule()
    for _cycle in range(2):
        records = _capture(om.reconcile)
        hits = [(rule.match_log(r), rule.dedup_key(r)) for r in records]
        hits = [h for h in hits if h[0]]
        assert len(hits) == 1
        text, key = hits[0]
        assert "BTC/USDT long" in text and "0.5" in text
    assert key.endswith("BTC/USDT.long")
