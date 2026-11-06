"""Per-trade community Telegram posts (default OFF, customer-safe, never raises)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.notifications.telegram_notifier import CustomerChannelNotifier


def _make(monkeypatch, *, creds=True, trades="1"):
    for k in ("EFLOUD_CUSTOMER_TG_TOKEN", "EFLOUD_CUSTOMER_TG_CHANNEL_ID", "EFLOUD_CUSTOMER_TG_TRADES"):
        monkeypatch.delenv(k, raising=False)
    if creds:
        monkeypatch.setenv("EFLOUD_CUSTOMER_TG_TOKEN", "tok")
        monkeypatch.setenv("EFLOUD_CUSTOMER_TG_CHANNEL_ID", "-100123")
    if trades is not None:
        monkeypatch.setenv("EFLOUD_CUSTOMER_TG_TRADES", trades)
    return CustomerChannelNotifier()


@pytest.fixture
def post(monkeypatch):
    m = MagicMock()
    m.return_value.status_code = 200
    monkeypatch.setattr("engine.notifications.telegram_notifier.requests.post", m)
    return m


def _open(n):
    return n.post_trade_opened("BTCUSDT", "LONG", 65000.0, 64000.0, 66500.0, 68000.0, setup="OTE_RETRACE")


@pytest.mark.parametrize("trades", [None, "0", "", "no"])
def test_flag_off_no_http(monkeypatch, post, trades):
    n = _make(monkeypatch, trades=trades)
    assert _open(n) is False
    assert n.post_trade_tp1("BTCUSDT", "LONG", 65000.0, 66500.0) is False
    assert n.post_trade_closed("BTCUSDT", "LONG", 65000.0, 66500.0) is False
    post.assert_not_called()


def test_no_creds_no_http(monkeypatch, post):
    n = _make(monkeypatch, creds=False, trades="1")
    assert _open(n) is False
    post.assert_not_called()


@pytest.mark.parametrize("val", ["1", "true", "YES"])
def test_flag_on_open_message(monkeypatch, post, val):
    n = _make(monkeypatch, trades=val)
    assert _open(n) is True
    post.assert_called_once()
    payload = post.call_args.kwargs["json"]
    assert payload["chat_id"] == "-100123"
    text = payload["text"]
    for needle in ("BTCUSDT", "LONG", "65000", "64000", "66500", "68000",
                   "Eğitim amaçlıdır", "Not financial advice", "u2algo Price Action"):
        assert needle in text
    low = text.lower()
    assert "$" not in text and "balance" not in low and "size" not in low and "usdt:" not in low


def test_tp1_and_close_messages(monkeypatch, post):
    n = _make(monkeypatch)
    assert n.post_trade_tp1("ETHUSDT", "SHORT", 3000.0, 2900.0) is True
    assert n.post_trade_closed("ETHUSDT", "SHORT", 3000.0, 2950.0, pnl_r=1.25, reason="TP2") is True
    t1, t2 = (c.kwargs["json"]["text"] for c in post.call_args_list)
    assert "ETHUSDT" in t1 and "TP1" in t1 and "2900" in t1
    assert "2950" in t2 and "+1.25R" in t2 and "TP2" in t2
    for t in (t1, t2):
        assert "$" not in t and "u2algo Price Action" in t and "Not financial advice" in t


def test_send_error_returns_false(monkeypatch):
    n = _make(monkeypatch)
    monkeypatch.setattr("engine.notifications.telegram_notifier.requests.post",
                        MagicMock(side_effect=RuntimeError("boom")))
    assert _open(n) is False
    assert n.post_trade_closed("A", "LONG", 1.0, 2.0) is False


def test_bad_input_never_raises(monkeypatch, post):
    n = _make(monkeypatch)
    assert n.post_trade_opened("A", "LONG", "x", None, object()) is False


# --- bot_runner wiring -------------------------------------------------------
def _pos(**kw):
    base = dict(symbol="BTCUSDT", direction="LONG", entry=65000.0, sl=64000.0,
                tp1=66500.0, tp2=68000.0, size=0.5, exit_price=66500.0,
                pnl_usdt=12.3, exit_reason="TP1", opened_at=0, closed_at=0,
                entry_setup_source="OTE_RETRACE")
    base.update(kw)
    return SimpleNamespace(**base)


def _runner():
    from backend.bot_runner import BotRunner
    r = BotRunner()
    r.notifier = MagicMock()
    r.community = MagicMock()
    return r


def test_runner_open_close_tp1_invoke_both():
    r = _runner()
    p = _pos()
    r._on_position_change("position_opened", p)
    r._on_position_change("tp1_hit", p)
    r._on_position_change("position_closed", p)
    r.notifier.notify_position_opened.assert_called_once()
    r.notifier.notify_tp1_hit.assert_called_once()
    r.notifier.notify_position_closed.assert_called_once()
    r.community.post_trade_opened.assert_called_once()
    r.community.post_trade_tp1.assert_called_once()
    r.community.post_trade_closed.assert_called_once()
    kw = r.community.post_trade_opened.call_args.kwargs
    assert "size" not in kw and kw["symbol"] == "BTCUSDT" and kw["tp1"] == 66500.0


def test_runner_community_exception_swallowed_ops_unaffected():
    r = _runner()
    r.community.post_trade_opened.side_effect = RuntimeError("x")
    r.community.post_trade_closed.side_effect = RuntimeError("x")
    p = _pos()
    r._on_position_change("position_opened", p)
    r._on_position_change("position_closed", p)
    r.notifier.notify_position_opened.assert_called_once()
    r.notifier.notify_position_closed.assert_called_once()


def test_runner_ops_exception_does_not_block_community():
    r = _runner()
    r.notifier.notify_position_opened.side_effect = RuntimeError("ops")
    r._on_position_change("position_opened", _pos())
    r.community.post_trade_opened.assert_called_once()
