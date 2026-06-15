"""Customer-channel Telegram notifier — T-018 (P-003 W3).

DISTINCT from `backend.notifications.TelegramNotifier` (the operator's real-time
position alerter). This one feeds the PUBLIC u2algo customer channel and is built
to stay on the safe side of the "signal service" regulatory line (P-003 §2b):

  • AGGREGATE / DELAYED only — a once-daily digest summarising CLOSED trades in
    aggregate (count, win-rate, aggregate return). It deliberately exposes NO
    per-trade entry/SL/TP/symbol, so a subscriber cannot reconstruct a tradeable
    signal from it.
  • DOUBLE-GATED, default OFF — emits only when BOTH the config flag
    (`notifications.telegram.enabled`, default False) AND the two customer-channel
    credentials are present. Either missing → hard no-op, zero HTTP.
  • SEPARATE credentials from the operator alerter (EFLOUD_CUSTOMER_TG_* vs
    EFLOUD_TELEGRAM_*) so the two channels never cross.
  • BEST-EFFORT — every send swallows exceptions; a Telegram outage must never
    propagate. (This module is never called from the trading loop anyway; a
    separate daily routine builds the digest and calls it.)

It intentionally does NOT touch NotificationManager, so operator terminal/log
notifications are structurally unaffected (G-P3-3 regression).

Env (both required to enable, on top of the config flag):
  - EFLOUD_CUSTOMER_TG_TOKEN       BotFather token for the customer-channel bot
  - EFLOUD_CUSTOMER_TG_CHANNEL_ID  public channel id (e.g. "-1001234567890")
Optional:
  - EFLOUD_CUSTOMER_TG_THREAD_ID   forum topic id
  - EFLOUD_CUSTOMER_TG_PARSE_MODE  "Markdown" (default) | "HTML"
  - EFLOUD_CUSTOMER_TG_TIMEOUT_SECS  HTTP timeout (default 5.0)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

log = logging.getLogger("efloud.notify.customer_tg")

_DEFAULT_TIMEOUT_SECS = 5.0

# Aggregate digest schema — the ONLY shape that leaves this module. Keeping it a
# fixed whitelist is the structural guard against per-trade signal leakage.
_DIGEST_KEYS = ("date", "closed_count", "wins", "losses", "win_rate_pct", "net_return_pct")


def build_daily_digest(closed_trades: list, date_label: str) -> dict:
    """Reduce a list of CLOSED-trade rows into an aggregate-only daily digest.

    `closed_trades`: rows with at least `pnl_usdt` and `pnl_pct`. Any per-trade
    signal fields (symbol/entry/sl/tp) are ignored — never copied into the output.
    Returns a dict with exactly `_DIGEST_KEYS` (aggregate only).
    """
    count = len(closed_trades)
    wins = sum(1 for t in closed_trades if (t.get("pnl_usdt") or 0) > 0)
    losses = sum(1 for t in closed_trades if (t.get("pnl_usdt") or 0) < 0)
    win_rate = round(wins / count * 100, 1) if count else 0.0
    net_return = round(sum((t.get("pnl_pct") or 0) for t in closed_trades), 2)
    return {
        "date": date_label,
        "closed_count": count,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
        "net_return_pct": net_return,
    }


class CustomerChannelNotifier:
    """Daily aggregate-digest poster for the public customer Telegram channel.

    Construction is cheap and reads credentials from env once. `config` is the
    `notifications.telegram` sub-dict; the `enabled` flag defaults to False so the
    notifier is inert unless an operator explicitly turns it on AND credentials
    are provisioned.
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        cfg = config or {}
        self.flag_enabled: bool = bool(cfg.get("enabled", False))
        # 'daily_digest' is the only implemented (and regulation-safe) mode.
        self.mode: str = cfg.get("mode", "daily_digest")

        self.token: Optional[str] = os.environ.get("EFLOUD_CUSTOMER_TG_TOKEN")
        self.channel_id: Optional[str] = os.environ.get("EFLOUD_CUSTOMER_TG_CHANNEL_ID")
        self.thread_id: Optional[str] = os.environ.get("EFLOUD_CUSTOMER_TG_THREAD_ID")
        self.parse_mode: str = os.environ.get("EFLOUD_CUSTOMER_TG_PARSE_MODE", "Markdown")
        try:
            self.timeout: float = float(
                os.environ.get("EFLOUD_CUSTOMER_TG_TIMEOUT_SECS", str(_DEFAULT_TIMEOUT_SECS))
            )
        except ValueError:
            self.timeout = _DEFAULT_TIMEOUT_SECS

        # Double gate: config flag AND both credentials.
        self.enabled: bool = self.flag_enabled and bool(self.token and self.channel_id)
        if self.enabled:
            log.info(f"Customer Telegram notifier enabled (channel={self.channel_id}, mode={self.mode})")
        else:
            why = "flag off" if not self.flag_enabled else "creds missing"
            log.info(f"Customer Telegram notifier disabled ({why})")

    def post_daily_digest(self, digest: dict) -> bool:
        """Post an aggregate daily digest. No-op (returns False) when disabled.

        `digest` should come from `build_daily_digest`. Even if a caller hands a
        richer dict, only the aggregate fields are formatted — per-trade fields are
        never rendered.
        """
        if not self.enabled:
            return False
        return self._send(self._format_digest(digest))

    def _format_digest(self, digest: dict) -> str:
        """Render the aggregate digest. Reads ONLY whitelisted aggregate keys."""
        date = digest.get("date", "")
        count = digest.get("closed_count", 0)
        wins = digest.get("wins", 0)
        losses = digest.get("losses", 0)
        wr = digest.get("win_rate_pct", 0.0)
        ret = digest.get("net_return_pct", 0.0)
        if count == 0:
            return (
                f"📊 *u2algo — Günlük Özet ({date})*\n"
                f"Bugün kapanan işlem yok."
            )
        return (
            f"📊 *u2algo — Günlük Özet ({date})*\n"
            f"Kapanan işlem: `{count}`  (✅ {wins} / ❌ {losses})\n"
            f"Kazanma oranı: `{wr:.1f}%`\n"
            f"Toplam getiri: `{ret:+.2f}%`\n"
            f"_Gecikmeli, toplulaştırılmış özet — yatırım tavsiyesi değildir._"
        )

    def _send(self, text: str) -> bool:
        """Best-effort POST to the customer channel. NEVER raises."""
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.channel_id,
            "text": text,
            "parse_mode": self.parse_mode,
            "disable_web_page_preview": True,
        }
        if self.thread_id:
            payload["message_thread_id"] = self.thread_id
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code >= 300:
                log.warning(f"Customer Telegram send failed: HTTP {resp.status_code} {resp.text[:200]}")
                return False
            return True
        except Exception as e:
            log.warning(f"Customer Telegram send exception: {e}")
            return False
