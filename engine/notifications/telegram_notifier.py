"""Customer-channel Telegram notifier — T-018 (P-003 W3).

DISTINCT from `backend.notifications.TelegramNotifier` (the operator's real-time
position alerter). This one feeds the PUBLIC u2algo customer channel and is built
to stay on the safe side of the "signal service" regulatory line (P-003 §2b):

  • AGGREGATE / DELAYED digest — a once-daily digest summarising CLOSED trades in
    aggregate (count, win-rate, aggregate return). The digest exposes NO
    per-trade entry/SL/TP/symbol.
  • PER-TRADE posts (post_trade_opened / _tp1 / _closed) ALSO exist: real-time
    symbol + entry/SL/TP. They are default OFF (EFLOUD_CUSTOMER_TG_TRADES). WARNING:
    these are NOT covered by the CMP-3 compliance gate and sit on the P-003 s2b
    "signal service" line - enabling them on a PUBLIC channel requires operator /
    legal sign-off first. The public close reason is whitelisted (TP1/TP2/SL/BE/closed).
  • Per-trade posts are fire-and-forget: queued to a single daemon worker thread
    (bounded queue, dropped when full) so a slow Telegram call never blocks the caller.
  • DIGEST is DOUBLE-GATED, default OFF — emits only when BOTH the config flag
    (`notifications.telegram.enabled`, default False) AND the two customer-channel
    credentials are present. Either missing → hard no-op, zero HTTP.
  • PER-TRADE posts are gated separately: EFLOUD_CUSTOMER_TG_TRADES AND the two
    credentials (the config flag is not consulted). They are always sent as
    legacy Markdown, whatever EFLOUD_CUSTOMER_TG_PARSE_MODE says.
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
  - EFLOUD_CUSTOMER_TG_PARSE_MODE  "Markdown" (default) | "HTML" — digest only
  - EFLOUD_CUSTOMER_TG_TIMEOUT_SECS  HTTP timeout (default 5.0)
  - EFLOUD_CUSTOMER_TG_TRADES      "1"/"true"/"yes" enables per-trade posts
                                   (open / TP1 / close) — default OFF. Customer-safe:
                                   no balance, USD PnL, size or account data.
"""
from __future__ import annotations

import logging
import os
import queue
import re
import threading
from typing import Optional

import requests

log = logging.getLogger("efloud.notify.customer_tg")

_DEFAULT_TIMEOUT_SECS = 5.0
_TRUTHY = ("1", "true", "yes")
_BRAND = "u2algo Price Action"
_DISCLAIMER = "_Eğitim amaçlıdır, yatırım tavsiyesi değildir. / Not financial advice._"


def _fmt_price(x) -> str:
    """Compact price: up to 8 significant decimals, trailing zeros trimmed."""
    s = f"{float(x):.8f}".rstrip("0").rstrip(".")
    return s or "0"


_QUEUE_MAX = 100
_TRADE_PARSE_MODE = "Markdown"  # per-trade texts use legacy Markdown markup


def _public_reason(reason) -> str:
    """Whitelist the close reason shown publicly: TP1 / TP2 / SL / BE, else 'closed'."""
    tokens = set(re.split(r"[^A-Z0-9]+", str(reason or "").upper()))
    if "TP2" in tokens:
        return "TP2"
    if "TP1" in tokens:
        return "TP1"
    # BE before SL: a stop moved to breakeven ("SL_BE") is a breakeven exit.
    if tokens & {"BE", "BREAKEVEN"}:
        return "BE"
    if tokens & {"SL", "STOP"}:
        return "SL"
    return "closed"


def _clean(text) -> str:
    """Strip Markdown/HTML control characters from free text."""
    return "".join(c for c in str(text).replace("_", " ") if c not in "*`[]<>&").strip()

# Aggregate digest schema — the ONLY shape that leaves this module. Keeping it a
# fixed whitelist is the structural guard against per-trade signal leakage.
_DIGEST_KEYS = ("date", "closed_count", "wins", "losses", "win_rate_pct", "net_return_pct")


def build_daily_digest(closed_trades: list[dict], date_label: str) -> dict:
    """Reduce a list of CLOSED-trade rows into an aggregate-only daily digest.

    `closed_trades`: rows with at least `pnl_usdt` and `pnl_pct`. Any per-trade
    signal fields (symbol/entry/sl/tp) are ignored — never copied into the output.
    Returns a dict with exactly `_DIGEST_KEYS` (aggregate only).

    Win/loss use strict `> 0` / `< 0`, so a breakeven trade (`pnl_usdt == 0`)
    counts toward `closed_count` but is neither a win nor a loss; `win_rate_pct`
    denominator is the total closed count (honest for a public channel). Missing
    or `None` pnl fields coerce to 0.
    """
    count = len(closed_trades)
    wins = sum(1 for t in closed_trades if (t.get("pnl_usdt") or 0) > 0)
    losses = sum(1 for t in closed_trades if (t.get("pnl_usdt") or 0) < 0)
    win_rate = round(wins / count * 100, 1) if count else 0.0
    net_return = round(sum((t.get("pnl_pct") or 0) for t in closed_trades), 2)
    values = {
        "date": date_label,
        "closed_count": count,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
        "net_return_pct": net_return,
    }
    # Build the result FROM the whitelist so _DIGEST_KEYS is the single source of
    # truth — a stray per-trade field can never slip into the emitted digest.
    return {k: values[k] for k in _DIGEST_KEYS}


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

        # Per-trade posts: independent env flag, default OFF.
        self.trades_enabled: bool = (
            os.environ.get("EFLOUD_CUSTOMER_TG_TRADES", "").strip().lower() in _TRUTHY
            and bool(self.token and self.channel_id)
        )

        # Double gate: config flag AND both credentials.
        self.enabled: bool = self.flag_enabled and bool(self.token and self.channel_id)
        if self.enabled:
            log.info(f"Customer Telegram notifier enabled (channel={self.channel_id}, mode={self.mode})")
        else:
            why = "flag off" if not self.flag_enabled else "creds missing"
            log.info(f"Customer Telegram notifier digest disabled ({why})")
        log.info(f"Customer Telegram per-trade posts: {'ENABLED' if self.trades_enabled else 'disabled'}")

        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=_QUEUE_MAX)
        self._worker: Optional[threading.Thread] = None
        self._worker_lock = threading.Lock()

    def post_daily_digest(self, digest: dict) -> bool:
        """Post an aggregate daily digest. No-op (returns False) when disabled.

        `digest` should come from `build_daily_digest`. Even if a caller hands a
        richer dict, only the aggregate fields are formatted — per-trade fields are
        never rendered.
        """
        if not self.enabled:
            return False
        return self._send(self._format_digest(digest))

    # ── per-trade posts (customer-safe; default OFF; never raise) ─────────────
    def _post_trade(self, build) -> bool:
        if not self.trades_enabled:
            return False
        try:
            text = build()
        except Exception as e:
            log.warning(f"Customer Telegram trade post build failed: {e}")
            return False
        # Fire-and-forget: never block the caller (reconcile / kill-switch paths).
        try:
            self._ensure_worker()
            self._queue.put_nowait(text)
            return True
        except queue.Full:
            log.warning("Customer Telegram trade post dropped: queue full")
            return False
        except Exception as e:
            log.warning(f"Customer Telegram trade post enqueue failed: {e}")
            return False

    def _ensure_worker(self) -> None:
        with self._worker_lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._run_worker, name="customer-tg-worker", daemon=True)
                self._worker.start()

    def _run_worker(self) -> None:
        while True:
            text = self._queue.get()
            try:
                self._deliver(text, parse_mode=_TRADE_PARSE_MODE)
            except Exception as e:  # _deliver never raises; belt and braces
                log.warning(f"Customer Telegram worker error: {e}")
            finally:
                self._queue.task_done()

    def post_trade_opened(self, symbol, direction, entry, sl, tp1, tp2=None, setup=None) -> bool:
        def build() -> str:
            icon = "🟢" if str(direction).upper() == "LONG" else "🔴"
            lines = [
                f"{icon} *{_clean(symbol)} {_clean(direction).upper()}* — yeni işlem / new trade",
                f"Entry: `{_fmt_price(entry)}`",
                f"SL: `{_fmt_price(sl)}`",
                f"TP1: `{_fmt_price(tp1)}`",
            ]
            if tp2:
                lines.append(f"TP2: `{_fmt_price(tp2)}`")
            if setup:
                lines.append(f"Setup: {_clean(setup)}")
            lines += [_BRAND, _DISCLAIMER]
            return "\n".join(lines)
        return self._post_trade(build)

    def post_trade_tp1(self, symbol, direction, entry, price) -> bool:
        def build() -> str:
            return "\n".join([
                f"🎯 *{_clean(symbol)} {_clean(direction).upper()}* — TP1 hit",
                f"Entry: `{_fmt_price(entry)}` → TP1: `{_fmt_price(price)}`",
                _BRAND, _DISCLAIMER,
            ])
        return self._post_trade(build)

    def post_trade_closed(self, symbol, direction, entry, exit_price, pnl_r=None, reason=None) -> bool:
        def build() -> str:
            lines = [
                f"🏁 *{_clean(symbol)} {_clean(direction).upper()}* — işlem kapandı / trade closed",
                f"Entry: `{_fmt_price(entry)}` → Exit: `{_fmt_price(exit_price)}`"
                if exit_price else f"Entry: `{_fmt_price(entry)}`",
            ]
            if pnl_r is not None:
                lines.append(f"Sonuç / Result: `{float(pnl_r):+.2f}R`")
            if reason:
                pub = _public_reason(reason)
                lines.append(f"Neden / Reason: {pub if pub != 'closed' else 'kapandı / closed'}")
            lines += [_BRAND, _DISCLAIMER]
            return "\n".join(lines)
        return self._post_trade(build)

    def _format_digest(self, digest: dict) -> str:
        """Render the aggregate digest. Reads ONLY whitelisted aggregate keys.

        R-11 fix (2026-07-17): TR kopya EN'in uyumlu yüzeyine hizalandı.
        compliance gate format_en_digest'i denetliyordu ama kanala GİDEN bu TR
        metin "Kazanma oranı: %x" + "Toplam getiri: %x" içeriyordu — CMP-3
        performance_pct_claim'in ('getiri' bir `%`'nin yanında) tam ihlali:
        denetlenen metin gönderilmiyor, gönderilen metin denetlenmiyordu.
        EN'le aynı çözüm (bkz. format_en_digest yorumu): win-rate satırı düşer,
        getiri → 'Net K/Z' (perf-kelimesi değil), sayılar aynen kalır.
        telegram_digest.run() artık BU render'ı da gate'ler (savunma katmanı).
        """
        date = digest.get("date", "")
        count = digest.get("closed_count", 0)
        wins = digest.get("wins", 0)
        losses = digest.get("losses", 0)
        ret = digest.get("net_return_pct", 0.0)
        if count == 0:
            return (
                f"📊 *u2algo — Günlük Özet ({date})*\n"
                f"Bugün kapanan işlem yok."
            )
        return (
            f"📊 *u2algo — Günlük Özet ({date})*\n"
            f"Kapanan işlem: `{count}`  (✅ {wins} / ❌ {losses})\n"
            f"Net K/Z: `{ret:+.2f}%`\n"
            f"_Gecikmeli, toplulaştırılmış özet — yatırım tavsiyesi değildir._"
        )

    def _send(self, text: str) -> bool:
        """Digest path: gated on the digest `enabled` flag."""
        if not self.enabled:
            return False
        return self._deliver(text)

    def _deliver(self, text: str, parse_mode: Optional[str] = None) -> bool:
        """Best-effort POST to the customer channel (no flag check). NEVER raises."""
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.channel_id,
            "text": text,
            "parse_mode": parse_mode or self.parse_mode,
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
