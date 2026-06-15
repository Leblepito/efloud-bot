"""Tests for engine.notifications.telegram_notifier (T-018, P-003 W3).

The CUSTOMER-channel notifier is distinct from backend.notifications.TelegramNotifier
(the operator's real-time position alerter):

- Customer channel = SEPARATE bot token/channel (EFLOUD_CUSTOMER_TG_*).
- DELAYED / AGGREGATE only — a once-daily digest, NO per-trade real-time entry/SL/TP
  (regulatory "not a signal service" guard, P-003 §2b).
- Double-gated: requires BOTH the config flag (`notifications.telegram.enabled`,
  default OFF) AND the two env credentials. Either missing → hard no-op, zero HTTP.
- Best-effort: a Telegram outage MUST NEVER propagate.
- It does NOT touch NotificationManager, so operator terminal/log notifications are
  structurally unaffected (G-P3-3 regression).
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from engine.notifications.telegram_notifier import (
    CustomerChannelNotifier,
    build_daily_digest,
)


# ── credentials present in env (but flag still governs) ──
@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("EFLOUD_CUSTOMER_TG_TOKEN", "9:cust")
    monkeypatch.setenv("EFLOUD_CUSTOMER_TG_CHANNEL_ID", "-100999")


class TestDoubleGate:
    """enabled requires BOTH config flag AND env creds. Default OFF."""

    def test_default_off_with_no_config(self, creds):
        # creds set, but no config → flag defaults OFF → disabled
        n = CustomerChannelNotifier()
        assert n.enabled is False

    def test_off_when_flag_false_even_with_creds(self, creds):
        n = CustomerChannelNotifier({"enabled": False})
        assert n.enabled is False

    def test_off_when_flag_true_but_no_creds(self, monkeypatch):
        monkeypatch.delenv("EFLOUD_CUSTOMER_TG_TOKEN", raising=False)
        monkeypatch.delenv("EFLOUD_CUSTOMER_TG_CHANNEL_ID", raising=False)
        n = CustomerChannelNotifier({"enabled": True})
        assert n.enabled is False

    def test_on_only_when_flag_true_and_creds_present(self, creds):
        n = CustomerChannelNotifier({"enabled": True})
        assert n.enabled is True

    def test_disabled_posts_nothing_and_makes_no_http(self, creds):
        n = CustomerChannelNotifier({"enabled": False})
        with patch("engine.notifications.telegram_notifier.requests.post") as mock_post:
            assert n.post_daily_digest(build_daily_digest([], "2026-06-15")) is False
            mock_post.assert_not_called()


class TestRegulatoryGuard:
    """The digest must be AGGREGATE only — no per-trade signal surface."""

    def test_build_daily_digest_is_aggregate_only(self):
        rows = [
            {"symbol": "BTC/USDT", "direction": "LONG", "entry": 95000, "sl": 94000,
             "tp1": 96000, "pnl_usdt": 120.0, "pnl_pct": 1.2},
            {"symbol": "ETH/USDT", "direction": "SHORT", "entry": 2600, "sl": 2650,
             "tp1": 2550, "pnl_usdt": -40.0, "pnl_pct": -0.8},
        ]
        d = build_daily_digest(rows, "2026-06-15")
        # whitelist: ONLY aggregate fields — no symbol/entry/sl/tp leakage
        assert set(d.keys()) == {
            "date", "closed_count", "wins", "losses", "win_rate_pct", "net_return_pct",
        }
        assert d["closed_count"] == 2
        assert d["wins"] == 1
        assert d["losses"] == 1
        assert d["win_rate_pct"] == 50.0

    def test_digest_text_contains_no_per_trade_signal_fields(self, creds):
        n = CustomerChannelNotifier({"enabled": True})
        rows = [{"symbol": "BTC/USDT", "direction": "LONG", "entry": 95000,
                 "sl": 94000, "tp1": 96000, "pnl_usdt": 120.0, "pnl_pct": 1.2}]
        with patch.object(n, "_send", return_value=True) as mock_send:
            n.post_daily_digest(build_daily_digest(rows, "2026-06-15"))
            text = mock_send.call_args.args[0]
        # no entry price, no SL, no TP, no symbol ticker → not a tradeable signal
        for leak in ("95000", "94000", "96000", "BTC/USDT"):
            assert leak not in text

    def test_empty_day_digest_is_valid(self):
        d = build_daily_digest([], "2026-06-15")
        assert d["closed_count"] == 0
        assert d["win_rate_pct"] == 0.0
        assert d["net_return_pct"] == 0.0


class TestSendBehavior:
    def test_post_uses_customer_token_and_channel(self, creds):
        n = CustomerChannelNotifier({"enabled": True})
        with patch("engine.notifications.telegram_notifier.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            assert n.post_daily_digest(build_daily_digest([], "2026-06-15")) is True
            url = mock_post.call_args.args[0]
            payload = mock_post.call_args.kwargs["json"]
            assert "9:cust" in url and url.endswith("/sendMessage")
            assert payload["chat_id"] == "-100999"

    def test_http_error_returns_false_never_raises(self, creds):
        n = CustomerChannelNotifier({"enabled": True})
        with patch("engine.notifications.telegram_notifier.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=429, text="rate limited")
            assert n.post_daily_digest(build_daily_digest([], "2026-06-15")) is False

    def test_network_exception_swallowed(self, creds):
        n = CustomerChannelNotifier({"enabled": True})
        with patch("engine.notifications.telegram_notifier.requests.post",
                   side_effect=ConnectionError("unreachable")):
            assert n.post_daily_digest(build_daily_digest([], "2026-06-15")) is False


class TestOperatorPathUntouched:
    """G-P3-3: the customer notifier must NOT import or mutate NotificationManager.
    Constructing the operator manager with default channels stays telegram-free."""

    def test_default_notification_manager_has_no_telegram_channel(self):
        from engine.notifications import NotificationManager
        mgr = NotificationManager()
        assert "telegram" not in mgr.channels  # default ['terminal','log']
