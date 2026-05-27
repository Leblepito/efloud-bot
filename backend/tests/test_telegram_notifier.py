"""Unit tests for backend.notifications.TelegramNotifier.

Covers:
- env-gated enable/disable behavior
- message formatting for each lifecycle event
- best-effort failure handling (network errors must NEVER propagate)
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from backend.notifications import TelegramNotifier


class TestEnableDisable:
    def test_disabled_when_no_env_vars(self, monkeypatch):
        monkeypatch.delenv("EFLOUD_TELEGRAM_TOKEN", raising=False)
        monkeypatch.delenv("EFLOUD_TELEGRAM_CHAT_ID", raising=False)
        n = TelegramNotifier()
        assert n.enabled is False

    def test_disabled_when_only_token_set(self, monkeypatch):
        monkeypatch.setenv("EFLOUD_TELEGRAM_TOKEN", "1:abc")
        monkeypatch.delenv("EFLOUD_TELEGRAM_CHAT_ID", raising=False)
        n = TelegramNotifier()
        assert n.enabled is False

    def test_disabled_when_only_chat_id_set(self, monkeypatch):
        monkeypatch.delenv("EFLOUD_TELEGRAM_TOKEN", raising=False)
        monkeypatch.setenv("EFLOUD_TELEGRAM_CHAT_ID", "12345")
        n = TelegramNotifier()
        assert n.enabled is False

    def test_enabled_with_both_env_vars(self, monkeypatch):
        monkeypatch.setenv("EFLOUD_TELEGRAM_TOKEN", "1:abc")
        monkeypatch.setenv("EFLOUD_TELEGRAM_CHAT_ID", "12345")
        n = TelegramNotifier()
        assert n.enabled is True

    def test_send_returns_false_when_disabled(self, monkeypatch):
        """send() must be a no-op (return False) when env vars are missing,
        and MUST NOT make any HTTP call."""
        monkeypatch.delenv("EFLOUD_TELEGRAM_TOKEN", raising=False)
        n = TelegramNotifier()
        with patch("backend.notifications.requests.post") as mock_post:
            assert n.send("hello") is False
            mock_post.assert_not_called()


class TestSendBehavior:
    """send() HTTP behavior with mocked requests."""

    @pytest.fixture
    def notifier(self, monkeypatch):
        monkeypatch.setenv("EFLOUD_TELEGRAM_TOKEN", "1:abc")
        monkeypatch.setenv("EFLOUD_TELEGRAM_CHAT_ID", "-100123")
        return TelegramNotifier()

    def test_send_posts_to_telegram_api_with_correct_payload(self, notifier):
        with patch("backend.notifications.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            assert notifier.send("hello world") is True
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            # URL contains bot token
            url = call_args.args[0]
            assert "1:abc" in url
            assert url.endswith("/sendMessage")
            # JSON payload has correct fields
            payload = call_args.kwargs["json"]
            assert payload["chat_id"] == "-100123"
            assert payload["text"] == "hello world"
            assert payload["parse_mode"] == "Markdown"

    def test_send_includes_thread_id_when_set(self, monkeypatch):
        monkeypatch.setenv("EFLOUD_TELEGRAM_TOKEN", "1:abc")
        monkeypatch.setenv("EFLOUD_TELEGRAM_CHAT_ID", "-100123")
        monkeypatch.setenv("EFLOUD_TELEGRAM_THREAD_ID", "42")
        n = TelegramNotifier()
        with patch("backend.notifications.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            n.send("hi")
            payload = mock_post.call_args.kwargs["json"]
            assert payload["message_thread_id"] == "42"

    def test_send_returns_false_on_http_error(self, notifier):
        """Telegram returning 4xx/5xx must NOT raise — log + return False."""
        with patch("backend.notifications.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=429, text="rate limited")
            assert notifier.send("hi") is False

    def test_send_swallows_network_exception(self, notifier):
        """Network failure must NEVER propagate into the trading loop."""
        with patch("backend.notifications.requests.post",
                   side_effect=ConnectionError("Telegram unreachable")):
            # Must not raise
            assert notifier.send("hi") is False


class TestMessageFormatters:
    """Lifecycle event formatters produce correct Markdown output."""

    @pytest.fixture
    def notifier(self, monkeypatch):
        monkeypatch.setenv("EFLOUD_TELEGRAM_TOKEN", "1:abc")
        monkeypatch.setenv("EFLOUD_TELEGRAM_CHAT_ID", "-100123")
        return TelegramNotifier()

    def test_position_opened_long_message_format(self, notifier):
        with patch.object(notifier, "send") as mock_send:
            notifier.notify_position_opened(
                symbol="LTC/USDT", direction="LONG",
                entry=58.184, sl=56.4, tp1=60.86, tp2=62.64, size=55.434,
            )
            text = mock_send.call_args.args[0]
            assert "🟢" in text
            assert "LTC/USDT" in text
            assert "LONG" in text
            assert "58.1840" in text  # 4-decimal entry
            assert "56.4000" in text
            assert "60.8600" in text

    def test_position_opened_short_uses_red_emoji(self, notifier):
        with patch.object(notifier, "send") as mock_send:
            notifier.notify_position_opened(
                symbol="ADA/USDT", direction="SHORT",
                entry=0.2762, sl=0.2845, tp1=0.2628, tp2=0.2539, size=16219,
            )
            text = mock_send.call_args.args[0]
            assert "🔴" in text
            assert "SHORT" in text

    def test_tp1_hit_message_format(self, notifier):
        with patch.object(notifier, "send") as mock_send:
            notifier.notify_tp1_hit(symbol="BTC/USDT", direction="LONG", entry=95000.0)
            text = mock_send.call_args.args[0]
            assert "🎯" in text
            assert "TP1 hit" in text
            assert "BTC/USDT" in text
            assert "break-even" in text

    def test_position_closed_winning_uses_check_emoji(self, notifier):
        with patch.object(notifier, "send") as mock_send:
            notifier.notify_position_closed(
                symbol="LTC/USDT", direction="LONG",
                entry=58.184, exit_price=62.64,
                pnl_usdt=247.30, exit_reason="TP2",
            )
            text = mock_send.call_args.args[0]
            assert "✅" in text
            assert "LTC/USDT" in text
            assert "TP2" in text
            assert "+247.30" in text

    def test_position_closed_losing_uses_x_emoji(self, notifier):
        with patch.object(notifier, "send") as mock_send:
            notifier.notify_position_closed(
                symbol="LTC/USDT", direction="LONG",
                entry=58.184, exit_price=56.4,
                pnl_usdt=-99.30, exit_reason="SL",
            )
            text = mock_send.call_args.args[0]
            assert "❌" in text
            assert "-99.30" in text
            assert "SL" in text

    def test_position_closed_short_pnl_pct_calculation(self, notifier):
        """SHORT: profit when exit < entry. PnL% must reflect that."""
        with patch.object(notifier, "send") as mock_send:
            notifier.notify_position_closed(
                symbol="ADA/USDT", direction="SHORT",
                entry=0.2762, exit_price=0.2628,
                pnl_usdt=217.34, exit_reason="TP1",
            )
            text = mock_send.call_args.args[0]
            # (0.2762 - 0.2628) / 0.2762 * 100 = +4.85%
            assert "+4.85%" in text

    def test_position_closed_calculates_fees_and_net_pnl(self, notifier):
        """When size > 0, notify_position_closed must compute fees and net PnL."""
        with patch.object(notifier, "send") as mock_send:
            # Let's say entry=2000, exit=2010 (LONG), size=2, gross pnl = 20 USDT.
            # Total fee = (2000 + 2010) * 2 * 0.0005 = 4.01 USDT
            # Real net pnl = 20 - 4.01 = 15.99 USDT
            notifier.notify_position_closed(
                symbol="ETH/USDT", direction="LONG",
                entry=2000.0, exit_price=2010.0,
                pnl_usdt=20.0, exit_reason="TP1",
                size=2.0,
            )
            text = mock_send.call_args.args[0]
            assert "Gross PnL: `+20.00` USDT" in text
            assert "Fee Paid: `4.0100` USDT" in text
            assert "Real Net PnL: *`+15.99`* USDT" in text
            assert "✅" in text  # Real net PnL is positive


    def test_formatters_are_noop_when_disabled(self, monkeypatch):
        """When notifier is disabled, formatters MUST NOT call send()."""
        monkeypatch.delenv("EFLOUD_TELEGRAM_TOKEN", raising=False)
        n = TelegramNotifier()
        with patch.object(n, "send") as mock_send:
            n.notify_position_opened("BTC/USDT", "LONG", 1, 1, 1, 1, 1)
            n.notify_tp1_hit("BTC/USDT", "LONG", 1)
            n.notify_position_closed("BTC/USDT", "LONG", 1, 1, 1, "TP2")
            mock_send.assert_not_called()


class TestZeroDivisionGuard:
    """Defensive: entry=0 in PnL% calc (shouldn't happen in prod but tests
    and dry-run code paths can hit it). Must not raise."""

    def test_zero_entry_does_not_crash_pnl_pct(self, monkeypatch):
        monkeypatch.setenv("EFLOUD_TELEGRAM_TOKEN", "1:abc")
        monkeypatch.setenv("EFLOUD_TELEGRAM_CHAT_ID", "-100123")
        n = TelegramNotifier()
        with patch.object(n, "send") as mock_send:
            # entry=0 — must use fallback 0.0% rather than ZeroDivisionError
            n.notify_position_closed(
                symbol="BTC/USDT", direction="LONG",
                entry=0.0, exit_price=100.0,
                pnl_usdt=50.0, exit_reason="TP2",
            )
            text = mock_send.call_args.args[0]
            assert "+0.00%" in text
