"""Telegram position notification adapter.

Sends inline notifications for position lifecycle events (opened, TP1 hit,
closed) directly from the bot to a Telegram chat. Decoupled from
notifications mainline because Telegram is one of multiple possible channels
(Discord, Slack, etc. could follow the same shape).

Env vars (both required to enable, otherwise the notifier is a no-op):
- EFLOUD_TELEGRAM_TOKEN: BotFather token (e.g. "123456:ABC-DEF...")
- EFLOUD_TELEGRAM_CHAT_ID: chat or channel ID (e.g. "-1001234567890")

Optional:
- EFLOUD_TELEGRAM_THREAD_ID: forum topic / thread ID (omit for plain DM/channel)
- EFLOUD_TELEGRAM_PARSE_MODE: "Markdown" (default) or "HTML"
- EFLOUD_TELEGRAM_TIMEOUT_SECS: HTTP timeout (default 5.0 — fire-and-forget,
  do NOT block the trading loop on a slow Telegram API)

Design contract:
- All public methods MUST swallow exceptions and emit a single warning log.
  A failed Telegram POST must NEVER propagate into the trading loop. Every
  notification is best-effort.
- The notifier is constructed once at bot startup and reused; it caches
  config from env vars at construction so runtime env changes are ignored
  (predictable behavior across cycles).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

log = logging.getLogger("efloud.notify.telegram")

_DEFAULT_TIMEOUT_SECS = 5.0


class TelegramNotifier:
    """Fire-and-forget Telegram message sender for position events.

    Construction is cheap and env-driven. If required env vars are missing,
    the notifier becomes an explicit no-op (`enabled = False`) — this lets
    the bot run in dev/test/CI without Telegram credentials.
    """

    def __init__(self) -> None:
        self.bot_token: Optional[str] = os.environ.get("EFLOUD_TELEGRAM_TOKEN")
        self.chat_id: Optional[str] = os.environ.get("EFLOUD_TELEGRAM_CHAT_ID")
        self.thread_id: Optional[str] = os.environ.get("EFLOUD_TELEGRAM_THREAD_ID")
        self.parse_mode: str = os.environ.get("EFLOUD_TELEGRAM_PARSE_MODE", "Markdown")
        try:
            self.timeout: float = float(
                os.environ.get("EFLOUD_TELEGRAM_TIMEOUT_SECS", str(_DEFAULT_TIMEOUT_SECS))
            )
        except ValueError:
            self.timeout = _DEFAULT_TIMEOUT_SECS

        self.enabled: bool = bool(self.bot_token and self.chat_id)
        if self.enabled:
            log.info(
                f"Telegram notifier enabled (chat_id={self.chat_id}"
                f"{', thread=' + self.thread_id if self.thread_id else ''})"
            )
        else:
            log.info("Telegram notifier disabled (EFLOUD_TELEGRAM_TOKEN/CHAT_ID not set)")

    def send(self, text: str) -> bool:
        """Send a Telegram message. Returns True on 2xx response, False otherwise.

        NEVER raises. All exceptions are caught and logged at WARNING. Callers
        in the trading loop rely on this guarantee — a network blip on
        Telegram's end must not affect order placement or reconciliation.
        """
        if not self.enabled:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": self.parse_mode,
            "disable_web_page_preview": True,
        }
        if self.thread_id:
            payload["message_thread_id"] = self.thread_id

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code >= 300:
                # Truncate body — Telegram errors are usually short, but be safe.
                log.warning(
                    f"Telegram send failed: HTTP {resp.status_code} {resp.text[:200]}"
                )
                return False
            return True
        except Exception as e:
            log.warning(f"Telegram send exception: {e}")
            return False

    # ─────────────────────────────────────────────────────────────
    # Convenience formatters — keep message logic close to data shape
    # so the bot_runner callback stays readable.
    # ─────────────────────────────────────────────────────────────

    def notify_position_opened(
        self,
        symbol: str,
        direction: str,
        entry: float,
        sl: float,
        tp1: float,
        tp2: float,
        size: float,
    ) -> None:
        """Fire-and-forget notification for a freshly opened position."""
        if not self.enabled:
            return
        emoji = "🟢" if direction == "LONG" else "🔴"
        text = (
            f"{emoji} *Yeni pozisyon: {symbol} {direction}*\n"
            f"Entry: `{entry:.4f}`  Size: `{size}`\n"
            f"SL: `{sl:.4f}`  TP1: `{tp1:.4f}`  TP2: `{tp2:.4f}`"
        )
        self.send(text)

    def notify_tp1_hit(self, symbol: str, direction: str, entry: float) -> None:
        """Fire-and-forget notification for a TP1 fill (SL→break-even)."""
        if not self.enabled:
            return
        text = (
            f"🎯 *TP1 hit: {symbol} {direction}*\n"
            f"SL → break-even @ `{entry:.4f}`\n"
            f"Kalan yarı pozisyon TP2'yi bekliyor."
        )
        self.send(text)

    def notify_position_closed(
        self,
        symbol: str,
        direction: str,
        entry: float,
        exit_price: float,
        pnl_usdt: float,
        exit_reason: str,
    ) -> None:
        """Fire-and-forget notification for a closed position."""
        if not self.enabled:
            return
        winning = pnl_usdt > 0
        emoji = "✅" if winning else "❌"
        # Compute PnL % defensively — avoid div-by-zero when entry is 0
        # (shouldn't happen in production but tests/dry-run can hit it).
        if entry:
            if direction == "LONG":
                pnl_pct = (exit_price - entry) / entry * 100
            else:
                pnl_pct = (entry - exit_price) / entry * 100
        else:
            pnl_pct = 0.0
        text = (
            f"{emoji} *{symbol} {direction} kapandı* — `{exit_reason}`\n"
            f"Entry: `{entry:.4f}` → Exit: `{exit_price:.4f}`\n"
            f"PnL: `{pnl_usdt:+.2f}` USDT (`{pnl_pct:+.2f}%`)"
        )
        self.send(text)
