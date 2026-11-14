"""Alert rule definitions — log-line matchers + healthz-payload matchers.

Each Rule defines: alert_key, severity, dedup_window_sec, and at least one of
match_log() / match_health(). The alerter's main loop iterates RULES and calls
both methods on every input — rules return None for input types they don't care
about.

In scope (Step 4):
    breaker.tripped.daily/weekly/consecutive  — log-driven
    health.crash_loop, health.unhealthy_15min  — healthz-driven

Out of scope (Step 4b follow-up):
    position.stuck_over_6h, exchange.error_burst, balance.unexpected_change

Overseer-watchdog (added Task E):
    overseer.heartbeat_stale  — file-mtime driven (no payload dependency)
"""
from __future__ import annotations

import html
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Healthz consecutive-failure threshold: 15 minutes
UNHEALTHY_15MIN_THRESHOLD_SEC = 15 * 60

# Overseer-heartbeat staleness threshold — 10 min matches the overseer
# RULE_EVAL_INTERVAL_SEC (10s) × 60 = plenty of grace before flagging stale.
OVERSEER_HEARTBEAT_STALE_THRESHOLD_SEC = 10 * 60


@dataclass
class Rule:
    """Base rule. Subclasses override match_log and/or match_health."""
    alert_key: str = ""
    severity: str = "WARNING"  # "WARNING" or "CRITICAL"
    dedup_window_sec: int = 30 * 60
    # False → text is sent verbatim (no LLM rewrite). For alerts whose numbers
    # must not be altered and that must never read like a trade call.
    ai_format: bool = True

    def match_log(self, rec: dict) -> Optional[str]:
        """Given a parsed JSON log line dict, return formatted alert text or None."""
        return None

    def dedup_key(self, rec: dict) -> str:
        """Dedup key for a matched log record. Default: one key per rule.
        Rules that fire for many independent events (per symbol / zone)
        override this so one event cannot silence another."""
        return self.alert_key

    def match_health(self, payload: dict, history: dict) -> Optional[str]:
        """Given a /healthz response dict and alerter's mutable history dict,
        return formatted alert text or None.

        history is the alerter's in-memory per-rule scratchpad — the rule
        may read/write keys it owns. NOT persisted across alerter restart;
        SQLite dedup is the only persistent state.
        """
        return None


# ─────────────────────────────────────────────────────────────────────
# Log-driven rules
# ─────────────────────────────────────────────────────────────────────


@dataclass
class BreakerDailyRule(Rule):
    """Matches breaker.py:155 _trip() — 'BREAKER TRIPPED: Daily loss ... exceeds ...'"""
    alert_key: str = "breaker.tripped.daily"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 24 * 60 * 60  # 1 per day

    def match_log(self, rec: dict) -> Optional[str]:
        if rec.get("logger") != "efloud.breaker":
            return None
        if rec.get("level") not in ("WARNING", "ERROR", "CRITICAL"):
            return None
        msg = rec.get("message", "")
        # Two-substring check: event prefix AND specific phrase (defends against
        # false positives from unrelated breaker logger output).
        if "BREAKER TRIPPED" in msg and "Daily loss" in msg:
            return f"🚨 <b>Breaker TRIPPED — daily loss limit</b>\n{_esc(msg)}"
        return None


@dataclass
class BreakerWeeklyRule(Rule):
    """Matches breaker.py:162 _halt() — 'BREAKER HALTED: Weekly drawdown ... reached limit ...' (level ERROR)"""
    alert_key: str = "breaker.tripped.weekly"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 7 * 24 * 60 * 60  # 1 per week

    def match_log(self, rec: dict) -> Optional[str]:
        if rec.get("logger") != "efloud.breaker":
            return None
        if rec.get("level") not in ("WARNING", "ERROR", "CRITICAL"):
            return None
        msg = rec.get("message", "")
        if "BREAKER HALTED" in msg and "Weekly drawdown" in msg:
            return f"🚨 <b>Breaker HALTED — weekly drawdown</b>\n{_esc(msg)}"
        return None


@dataclass
class BreakerConsecutiveRule(Rule):
    """Matches breaker.py:168 _trip() — 'BREAKER TRIPPED: N consecutive losses'"""
    alert_key: str = "breaker.tripped.consecutive"
    severity: str = "WARNING"
    dedup_window_sec: int = 30 * 60  # 30 min

    def match_log(self, rec: dict) -> Optional[str]:
        if rec.get("logger") != "efloud.breaker":
            return None
        if rec.get("level") not in ("WARNING", "ERROR", "CRITICAL"):
            return None
        msg = rec.get("message", "")
        if "BREAKER TRIPPED" in msg and "consecutive losses" in msg:
            return f"⚠️ <b>Breaker TRIPPED — consecutive losses</b>\n{_esc(msg)}"
        return None


# ─────────────────────────────────────────────────────────────────────
# Healthz-driven rules
# ─────────────────────────────────────────────────────────────────────


@dataclass
class HealthCrashLoopRule(Rule):
    alert_key: str = "health.crash_loop"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 24 * 60 * 60  # once per occurrence

    def match_health(self, payload: dict, history: dict) -> Optional[str]:
        if payload.get("status") == "suspended" and \
           "crash_loop_suspended" in payload.get("failures", []):
            crash_count = payload.get("checks", {}).get("crash_count", "?")
            return (
                f"🚨 <b>CRASH LOOP detected — bot SUSPENDED</b>\n"
                f"crash_count = {crash_count}\n"
                f"See docs/runbooks/crash-loop-recovery.md"
            )
        return None


@dataclass
class HealthBreakerHaltedRule(Rule):
    """R-1 fix (2026-07-17): HALTED breaker healthz'te 200 + status:'suspended'
    + failures:['breaker_halted'] döner (backend/healthz.py) — hiçbir kural bu
    imzayı eşlemediği için mainnet trading halt'ı operatöre hiç ulaşmıyordu
    (log-tabanlı breaker kuralları prod'da yazılmayan dosyayı tail'liyor,
    breaker_watch rutini de yanlış path/format okuyordu; üç kanal da ölüydü)."""
    alert_key: str = "health.breaker_halted"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 6 * 60 * 60  # HALT sürerken 6 saatte bir hatırlat

    def match_health(self, payload: dict, history: dict) -> Optional[str]:
        if payload.get("status") == "suspended" and \
           "breaker_halted" in payload.get("failures", []):
            return (
                "🚨 <b>CIRCUIT BREAKER HALTED — trading suspended</b>\n"
                "healthz failures = ['breaker_halted']\n"
                "Bot yeni giriş açmıyor; mevcut pozisyon korumaları aktif.\n"
                "Kontrol: /api/breaker durumu + state/breaker.json reason."
            )
        return None


@dataclass
class HealthUnhealthy15MinRule(Rule):
    """Fires when /healthz has returned 503 (status:'unhealthy') continuously
    for at least UNHEALTHY_15MIN_THRESHOLD_SEC.

    Uses history dict to track the timestamp of the first 503 in the current
    streak. Resets when /healthz returns ok or suspended.
    """
    alert_key: str = "health.unhealthy_15min"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 24 * 60 * 60

    def match_health(self, payload: dict, history: dict) -> Optional[str]:
        status = payload.get("status")
        if status != "unhealthy":
            # Streak broken — clear history
            history.pop("unhealthy_since_ts", None)
            return None

        now = int(time.time())
        if "unhealthy_since_ts" not in history:
            history["unhealthy_since_ts"] = now
            return None

        elapsed = now - history["unhealthy_since_ts"]
        if elapsed >= UNHEALTHY_15MIN_THRESHOLD_SEC:
            failures = payload.get("failures", [])
            return (
                f"🚨 <b>Health check failing &gt;15 min</b>\n"
                f"elapsed: {elapsed}s\n"
                f"failures: {failures}"
            )
        return None


# ─────────────────────────────────────────────────────────────────────
# Trade lifecycle (operator visibility — every confirmed open)
# ─────────────────────────────────────────────────────────────────────


@dataclass
class TradeOpenedRule(Rule):
    """Matches safe_orchestrator.py:448 log line on confirmed trade open.

    Format: '✅ [SYMBOL] Opened LONG/SHORT @ {price} size={size} SL=... TP1=... TP2=... Conf=...'

    No dedup — every trade open is a unique event the operator wants to see.
    """
    alert_key: str = "trade.opened"
    severity: str = "INFO"
    dedup_window_sec: int = 0  # always fire — every open is unique

    def match_log(self, rec: dict) -> Optional[str]:
        if rec.get("logger") != "efloud.safe_orch":
            return None
        if rec.get("level") != "INFO":
            return None
        msg = rec.get("message", "")
        # Match: "✅ [SYMBOL] Opened LONG/SHORT @ ..."
        if "Opened" in msg and "@" in msg and ("LONG" in msg or "SHORT" in msg):
            return f"📈 <b>Trade opened</b>\n{msg}"
        return None


@dataclass
class TP1HitRule(Rule):
    """TP1 partial fill — 50% closed, SL moves to break-even, position stays open.

    Two log paths:
    - lifecycle.add_exit (paper-trade): '🎯 TP1 HIT {symbol} | Closed 50% @ ...'
    - exchange reconcile (live): 'RECONCILE: TP1 hit {symbol} → SL → break-even @ ...'
    """
    alert_key: str = "trade.tp1"
    severity: str = "INFO"
    dedup_window_sec: int = 0

    def match_log(self, rec: dict) -> Optional[str]:
        if rec.get("level") != "INFO":
            return None
        logger = rec.get("logger", "")
        msg = rec.get("message", "")
        if logger == "efloud.lifecycle" and "TP1 HIT" in msg:
            return f"🎯 <b>TP1 hit (partial)</b>\n{msg}"
        if logger == "efloud.exchange" and "RECONCILE: TP1 hit" in msg:
            return f"🎯 <b>TP1 hit (partial)</b>\n{msg}"
        return None


@dataclass
class TradeClosedRule(Rule):
    """Full position close — TP2, SL, MANUAL, RECONCILED. Position fully exits.

    Two log paths:
    - lifecycle.close_position (paper-trade): '{✅|❌} CLOSE {symbol} {direction} @ ... | Reason={reason} | Total PnL=...'
    - exchange._record_close (live reconcile): '{reason}: {symbol} {direction} | Entry=... Exit=... | PnL=...'
      where {reason} ∈ {TP2, SL, MANUAL, RECONCILED, SL_POLL, TP2_POLL}
    """
    alert_key: str = "trade.closed"
    severity: str = "INFO"
    dedup_window_sec: int = 0

    # Exchange-side close prefixes (full close only — TP1 is partial, handled by TP1HitRule)
    _EXCHANGE_CLOSE_PREFIXES = ("TP2: ", "SL: ", "MANUAL: ", "RECONCILED: ", "SL_POLL: ", "TP2_POLL: ")

    def match_log(self, rec: dict) -> Optional[str]:
        if rec.get("level") != "INFO":
            return None
        logger = rec.get("logger", "")
        msg = rec.get("message", "")
        # lifecycle full close: "✅ CLOSE ..." or "❌ CLOSE ..."
        if logger == "efloud.lifecycle" and " CLOSE " in msg and "Reason=" in msg:
            emoji = "❌" if "❌" in msg else "✅"
            return f"{emoji} <b>Position closed</b>\n{msg}"
        # exchange reconcile full close
        if logger == "efloud.exchange":
            for prefix in self._EXCHANGE_CLOSE_PREFIXES:
                if msg.startswith(prefix):
                    reason = prefix.rstrip(": ")
                    # PnL sign — "+" anywhere after "PnL=" (or "$+") suggests win
                    is_win = "PnL=+" in msg or "$+" in msg
                    emoji = "✅" if is_win else "❌"
                    return f"{emoji} <b>Position closed ({reason})</b>\n{msg}"
        return None


# ─────────────────────────────────────────────────────────────────────
# LuxAlgo zone early warning (T-20261104-08) — read-only, default OFF
# ─────────────────────────────────────────────────────────────────────

LUX_ALERTS_ENV = "EFLOUD_ALERTER_LUX_ALERTS"
_LUX_NOTE = "ℹ️ Bilgi amaçlı — işlem sinyali değil; emri yalnız motor verir."
# safe_orchestrator._lux_trace format: "[lux] <event> <SYM> <DIR> bars=N price=P zone=[lo-hi] | extra"
_RE_LUX = re.compile(
    r"^\[lux\] (?P<event>near|touch|confirmed) (?P<sym>\S+) (?P<dir>LONG|SHORT) "
    r"bars=(?P<bars>\d+) price=(?P<price>\S+) zone=\[(?P<zone>[^\]]+)\](?: \| (?P<extra>.*))?$")
# safe_orchestrator._place_v2_entry_order: "[v2 reject] <SYM>: <reason> (...)"
_RE_REJECT = re.compile(r"^\[v2 reject\] (?P<sym>\S+): (?P<reason>[a-z_0-9]+)(?P<rest>.*)$")
_LUX_TITLES = {
    "near": "👀 <b>Bölgeye yaklaşıyor</b>",
    "touch": "📍 <b>Fiyat bölgede — bot teyit mumu bekliyor</b>",
    "confirmed": "✅ <b>Bölgede teyit geldi — emir kontrollerine gidiyor</b>",
}


def _lux_alerts_on() -> bool:
    return os.environ.get(LUX_ALERTS_ENV, "").strip().lower() in ("1", "true", "yes", "on")


# K1 / ADR-0012: the alerter shares the bot's env_file, so this is the same
# switch the bot reads. Truthy set mirrors engine/safety/position_guard.py
# `_ENV_TRUE` (pinned by tests/test_alerter_lux_rules.py); importing the engine
# package here would drag the whole orchestrator into the alerter.
PAUSE_ENV = "EFLOUD_PAUSE_NEW_ENTRIES"
PAUSE_TRUE = frozenset({"1", "true", "yes", "on"})
_LUX_PAUSED_TITLES = {
    "near": "⏸ <b>Bölgeye yaklaşıyor — yeni girişler DURDURULDU</b>",
    "touch": "⏸ <b>Fiyat bölgede — yeni girişler DURDURULDU</b>",
    "confirmed": "⏸ <b>Bölgede teyit geldi — yeni girişler DURDURULDU</b>",
}
_LUX_PAUSED_NOTE = "⏸ Pause aktif (EFLOUD_PAUSE_NEW_ENTRIES): bot bu bölgeden işlem açmaz."


def _entries_paused() -> bool:
    return os.environ.get(PAUSE_ENV, "").strip().lower() in PAUSE_TRUE


def _safe_orch_msg(rec: dict, levels=("INFO",)) -> Optional[str]:
    if rec.get("logger") != "efloud.safe_orch" or rec.get("level") not in levels:
        return None
    return rec.get("message", "")


def _esc(x) -> str:
    """Telegram parse_mode=HTML: raw '<' / '&' in log text makes the API refuse the message."""
    return html.escape(str(x or ""), quote=False)


@dataclass
class LuxZoneAlertRule(Rule):
    """`[lux] near|touch|confirmed` → operator message.

    left/reentry are skipped on purpose: price oscillating at a zone edge
    flips them every 30 s tick. One message per (event, symbol, direction,
    zone) per window.
    """
    alert_key: str = "lux.zone"
    severity: str = "INFO"
    dedup_window_sec: int = 6 * 60 * 60
    ai_format: bool = False

    def match_log(self, rec: dict) -> Optional[str]:
        if not _lux_alerts_on():
            return None
        m = _RE_LUX.match(_safe_orch_msg(rec) or "")
        if not m:
            return None
        extra = f" · {_esc(m['extra'])}" if m["extra"] else ""
        paused = _entries_paused()
        title = (_LUX_PAUSED_TITLES if paused else _LUX_TITLES)[m["event"]]
        note = f"{_LUX_PAUSED_NOTE}\n{_LUX_NOTE}" if paused else _LUX_NOTE
        return (f"{title}\n"
                f"{_esc(m['sym'])} {m['dir']} · bölge [{_esc(m['zone'])}] · fiyat {_esc(m['price'])}{extra}\n"
                f"{note}")

    def dedup_key(self, rec: dict) -> str:
        m = _RE_LUX.match(rec.get("message", ""))
        if not m:
            return self.alert_key
        return f"{self.alert_key}.{m['event']}.{m['sym']}.{m['dir']}.{m['zone']}"


@dataclass
class V2RejectAlertRule(Rule):
    """`[v2 reject] SYM: reason` → operator sees which rule blocked the entry."""
    alert_key: str = "lux.reject"
    severity: str = "INFO"
    dedup_window_sec: int = 60 * 60
    ai_format: bool = False

    def match_log(self, rec: dict) -> Optional[str]:
        if not _lux_alerts_on():
            return None
        # WARNING dahil: sizing / breaker / pos_guard kontrol HATALARI bu seviyede loglanır.
        m = _RE_REJECT.match(_safe_orch_msg(rec, levels=("INFO", "WARNING")) or "")
        if not m:
            return None
        return (f"⛔ <b>Bot girişi reddetti</b>\n"
                f"{_esc(m['sym'])} · kural: {_esc(m['reason'])}{_esc(m['rest'])}\n"
                f"{_LUX_NOTE}")

    def dedup_key(self, rec: dict) -> str:
        m = _RE_REJECT.match(rec.get("message", ""))
        if not m:
            return self.alert_key
        return f"{self.alert_key}.{m['sym']}.{m['reason']}"


# ─────────────────────────────────────────────────────────────────────
# TP placement failure (T-20261107-03) — read-only, default OFF
# ─────────────────────────────────────────────────────────────────────

TP_ALERTS_ENV = "EFLOUD_ALERTER_TP_ALERTS"
# Structured events emitted by exchange.OrderManager._retry_tp_order (extras
# land in the JSON log line: event/symbol/direction/tp_leg/error/attempt/...).
_TP_FAILED_EVENT = "order_manager.tp_placement_failed_after_sl"
_TP_UNREACHABLE_EVENT = "order_manager.tp_unreachable"


def _flag_on(env: str) -> bool:
    return os.environ.get(env, "").strip().lower() in ("1", "true", "yes", "on")


def _tries(rec: dict) -> str:
    """retryable=False → non-transient error, _retry_tp_order stopped after
    one call; an "1/3" counter would wrongly suggest more attempts."""
    if rec.get("retryable", True):
        return f"deneme {_esc(rec.get('attempt'))}/{_esc(rec.get('max_attempts'))}"
    return "kalıcı hata (tekrar denenmedi)"


def _tp_event(rec: dict) -> Optional[str]:
    """Return the event name for a TP-leg placement failure record, else None.
    Labels: TP1 / TP2 (open + post-placement verify), TP1_REPAIR / TP2_REPAIR
    (reconcile repair). SL legs are excluded — their failures go through the
    rollback / fail-closed paths."""
    if rec.get("logger") != "efloud.exchange":
        return None
    event = rec.get("event")
    if event not in (_TP_FAILED_EVENT, _TP_UNREACHABLE_EVENT):
        return None
    if not str(rec.get("tp_leg", "")).startswith("TP"):
        return None
    return event


@dataclass
class TpPlacementFailedRule(Rule):
    """TP order could not be placed → operator message.

    One message per (kind, position, TP1|TP2) per hour: the repair loop
    re-tries every reconcile cycle and would otherwise repeat the alert. The
    position is identified by entry_order_id (logged by every caller), so a
    new position on the same symbol+direction is not silenced.
    """
    alert_key: str = "order.tp_failed"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 60 * 60
    ai_format: bool = False

    def match_log(self, rec: dict) -> Optional[str]:
        if not _flag_on(TP_ALERTS_ENV):
            return None
        event = _tp_event(rec)
        if event is None:
            return None
        head = f"{_esc(rec.get('symbol'))} {_esc(rec.get('direction'))} · {_esc(rec.get('tp_leg'))}"
        error = _esc(str(rec.get("error", ""))[:300])
        if event == _TP_UNREACHABLE_EVENT:
            return ("🚨 <b>TP yerleştirilemiyor — fiyat TP seviyesini geçmiş (-2021)</b>\n"
                    f"{head}\nhata: {error}\n"
                    "Bot bu TP bacağını yeniden denemez; pozisyonu kontrol et.")
        return ("⚠️ <b>TP emri yerleştirilemedi</b>\n"
                f"{head} · {_tries(rec)}\n"
                f"hata: {error}\n"
                "Bot, pozisyon açık kaldığı sürece her reconcile döngüsünde TP'yi "
                "yeniden dener; bu uyarı aynı pozisyon/bacak için saatte en fazla 1 kez gelir.")

    def dedup_key(self, rec: dict) -> str:
        event = _tp_event(rec)
        if event is None:
            return self.alert_key
        kind = "unreachable" if event == _TP_UNREACHABLE_EVENT else "failed"
        leg = str(rec.get("tp_leg", "")).split("_")[0]
        return (f"{self.alert_key}.{kind}.{rec.get('symbol')}.{rec.get('direction')}."
                f"{rec.get('entry_order_id')}.{leg}")


# ─────────────────────────────────────────────────────────────────────
# SL protection failure (T-20261107-05) — read-only, default OFF
# ─────────────────────────────────────────────────────────────────────

SL_ALERTS_ENV = "EFLOUD_ALERTER_SL_ALERTS"
# Position may be open WITHOUT a stop right now → SlUnprotectedRule.
_SL_UNPROTECTED_KINDS = ("repair_failed", "rollback_failed", "close_failed")


def _sl_kind(rec: dict) -> Optional[str]:
    """Classify an exchange SL-protection event (structured extras), else None.

    The initial SL at open (tp_leg="SL") and the -2021 SL_REPAIR line are not
    matched directly: their outcome is reported by the rollback /
    sl_repair_unreachable_closing / fallback_close_failed events below.
    verify.sl_unconfirmed_rollback is not matched either: it always ends in
    one of the two rollback events (original_error names the verify path)
    because the sibling cancel before the rollback swallows its own errors
    (_cancel_position_siblings). be_sl_placement_failed and
    verify.no_read_tolerated are left to the next reconcile repair, whose
    repair_missing_sl / SL_REPAIR events are matched."""
    if rec.get("logger") != "efloud.exchange":
        return None
    event = rec.get("event")
    if event == _TP_FAILED_EVENT and rec.get("tp_leg") == "SL_REPAIR":
        return "repair_failed"
    if event == "order_manager.entry_rollback_failed":
        return "rollback_failed"
    if (event == "order_manager.fallback_close_failed"
            and rec.get("reason") in ("SL_REPAIR_UNREACHABLE", "SL_BE_UNREACHABLE")):
        return "close_failed"
    if event == "order_manager.repair_missing_sl":
        return "missing"
    if event in ("order_manager.sl_repair_unreachable_closing",
                 "order_manager.be_sl_unreachable_closing"):
        return "closing"
    if event == "order_manager.entry_rollback_after_sl_failure":
        return "rolled_back"
    return None


def _sl_text(kind: str, rec: dict) -> str:
    head = f"{_esc(rec.get('symbol'))} {_esc(rec.get('direction'))}"
    if kind == "repair_failed":
        return ("🚨 <b>POZİSYON STOP'SUZ — SL yeniden gönderilemedi</b>\n"
                f"{head} · {_tries(rec)}\nhata: {_esc(str(rec.get('error', ''))[:300])}\n"
                "Bot, pozisyon açık kaldığı sürece her reconcile döngüsünde SL'yi yeniden dener; "
                "sorun sürerse bu uyarı 15 dakikada bir tekrarlanır.")
    if kind == "rollback_failed":
        return ("🚨 <b>GİRİŞ GERİ ALINAMADI — borsada STOP'SUZ pozisyon olabilir</b>\n"
                f"{head}\nsebep: {_esc(str(rec.get('original_error', ''))[:200])}\n"
                f"kapatma hatası: {_esc(str(rec.get('rollback_error', ''))[:200])}\n"
                "Bot bu pozisyonu artık takip etmiyor. Hemen Binance'te kontrol et. "
                "Orphan koruması açıksa sonraki reconcile'larda girişten varsayılan %2 "
                "uzaklıkta bir SL koymayı dener (döngü başına 1 pozisyon, emir okuması "
                "başarısızsa atlanır) — garanti değil.")
    if kind == "close_failed":
        return ("🚨 <b>Stop'suz pozisyon KAPATILAMADI</b>\n"
                f"{head} · fiyat stop seviyesini (SL ya da break-even) geçmişti, "
                "market kapatma başarısız\n"
                f"{_esc(str(rec.get('message', ''))[:300])}\n"
                "Pozisyon açık ve korumasız; bot sonraki reconcile döngüsünde yeniden dener. "
                "Manuel kontrol et.")
    if kind == "missing":
        return ("⚠️ <b>SL emri borsada yok — bot yeniden gönderiyor</b>\n"
                f"{head}\n"
                "SL hiç konmamış ya da borsadan kaybolmuş. Gönderim başarısız olursa "
                "ayrı bir STOP'SUZ uyarısı gelir.")
    if kind == "closing":
        where = ("break-even" if rec.get("event") == "order_manager.be_sl_unreachable_closing"
                 else "SL")
        return (f"⚠️ <b>Stop konamıyor — fiyat {where} seviyesini geçmiş (-2021)</b>\n"
                f"{head}\n"
                "Bot pozisyonu (kalan kısmını) market emriyle kapatıyor. "
                "Kapatma başarısız olursa ayrı uyarı gelir.")
    return ("ℹ️ <b>Giriş geri alındı — SL konamadı</b>\n"
            f"{head}\nsebep: {_esc(str(rec.get('original_error', ''))[:200])}\n"
            "Pozisyon için reduceOnly market kapatma emri gönderildi "
            f"(rollback emri {_esc(rec.get('rollback_order_id'))}).")


def _sl_dedup_key(alert_key: str, kind: str, rec: dict) -> str:
    # entry_order_id identifies the position where the caller logs it
    # (repair_failed / rollback events); otherwise symbol+direction.
    return (f"{alert_key}.{kind}.{rec.get('symbol')}.{rec.get('direction')}."
            f"{rec.get('entry_order_id')}")


@dataclass
class SlUnprotectedRule(Rule):
    """Position may be open without a stop loss right now.

    15-minute window (vs 1 h for TP): an unprotected position is the
    2026-05-14 bare-position failure mode, so the operator is reminded every
    15 min while the repair loop keeps failing — not every 30 s cycle."""
    alert_key: str = "order.sl_unprotected"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 15 * 60
    ai_format: bool = False

    def match_log(self, rec: dict) -> Optional[str]:
        if not _flag_on(SL_ALERTS_ENV):
            return None
        kind = _sl_kind(rec)
        return _sl_text(kind, rec) if kind in _SL_UNPROTECTED_KINDS else None

    def dedup_key(self, rec: dict) -> str:
        return _sl_dedup_key(self.alert_key, _sl_kind(rec) or "", rec)


@dataclass
class SlProtectionEventRule(Rule):
    """SL went missing / could not be placed and the bot handled it (re-send
    attempted, position closed, or entry rolled back). WARNING: informational —
    a failed outcome is reported separately by SlUnprotectedRule."""
    alert_key: str = "order.sl_event"
    severity: str = "WARNING"
    dedup_window_sec: int = 60 * 60
    ai_format: bool = False

    def match_log(self, rec: dict) -> Optional[str]:
        if not _flag_on(SL_ALERTS_ENV):
            return None
        kind = _sl_kind(rec)
        return _sl_text(kind, rec) if kind and kind not in _SL_UNPROTECTED_KINDS else None

    def dedup_key(self, rec: dict) -> str:
        return _sl_dedup_key(self.alert_key, _sl_kind(rec) or "", rec)


# SL-coverage blind spots (risk-ops follow-up to #350 / Ö1). When the algo-order
# read fails, verify and reconcile both fail closed (no false close, no duplicate
# SL) — but nobody can confirm SL/TP either. Surface it; no bot change needed.
_RE_NO_READ = re.compile(r"^verify\.no_read_tolerated: (?P<sym>\S+) (?P<dir>LONG|SHORT)\b")
_RECON_ALGO_FAIL = "Reconcile: algo orders fetch failed"


@dataclass
class VerifyNoReadRule(Rule):
    """A new position's SL/TP could not be confirmed at all (every verify read failed)."""
    alert_key: str = "order.verify_no_read"
    severity: str = "WARNING"
    dedup_window_sec: int = 60 * 60
    ai_format: bool = False

    def match_log(self, rec: dict) -> Optional[str]:
        if not _flag_on(SL_ALERTS_ENV):
            return None
        m = _RE_NO_READ.match(rec.get("message", "") or "")
        if not m:
            return None
        return (f"⚠️ <b>Yeni pozisyonun SL/TP'si doğrulanamadı</b>\n"
                f"{_esc(m['sym'])} {m['dir']} · borsa emir okuması başarısız; "
                f"reconcile okuma düzelince kontrol edecek. Borsada SL'i elle kontrol et.")

    def dedup_key(self, rec: dict) -> str:
        m = _RE_NO_READ.match(rec.get("message", "") or "")
        return f"{self.alert_key}.{m['sym']}.{m['dir']}" if m else self.alert_key


ALGO_STREAK_COUNT = 3
ALGO_STREAK_WINDOW_SEC = 10 * 60


@dataclass
class AlgoFetchStreakRule(Rule):
    """Reconcile's algo-order read failed >= ALGO_STREAK_COUNT times within
    ALGO_STREAK_WINDOW_SEC (record time) → SL/TP coverage cannot be confirmed.
    A single transient failure (≈ once a month in prod) stays silent."""
    alert_key: str = "order.algo_fetch_blind"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 60 * 60
    ai_format: bool = False
    _fails: list = field(default_factory=list)

    def match_log(self, rec: dict) -> Optional[str]:
        if not _flag_on(SL_ALERTS_ENV):
            return None
        if not (rec.get("message", "") or "").startswith(_RECON_ALGO_FAIL):
            return None
        try:
            t = datetime.fromisoformat(str(rec.get("ts"))).timestamp()
        except ValueError:
            return None
        self._fails = [x for x in self._fails if t - x < ALGO_STREAK_WINDOW_SEC] + [t]
        if len(self._fails) < ALGO_STREAK_COUNT:
            return None
        return (f"🚨 <b>Borsa algo emir okuması tekrar tekrar başarısız</b>\n"
                f"{len(self._fails)} hata / {ALGO_STREAK_WINDOW_SEC // 60} dk — bot SL/TP'nin "
                f"borsada durduğunu doğrulayamıyor (onarım da bekliyor). Borsada açık "
                f"pozisyonların SL'ini elle kontrol et.")


# Orphan position (T-20261107-11). exchange.OrderManager.reconcile logs this
# free-text WARNING on every cycle while the exchange holds a position the bot
# does not track: "⚠️  ORPHAN POSITION DETECTED: SYM side qty=.. entry=.. upnl=.."
# or "... SYM — details unavailable". No structured extras → regex.
_RE_ORPHAN = re.compile(
    r"ORPHAN POSITION DETECTED: (?P<sym>\S+)"
    r"(?: (?P<side>\S+) qty=(?P<qty>\S+) entry=(?P<entry>\S+) upnl=(?P<upnl>\S+))?")


ORPHAN_IGNORE_ENV = "EFLOUD_ALERTER_ORPHAN_IGNORE_SYMBOLS"


def _norm_symbol(sym: str) -> str:
    """'BTC/USDT:USDT' / 'btc/usdt' / 'BTCUSDT' → 'BTCUSDT'."""
    return sym.split(":")[0].replace("/", "").strip().upper()


def _orphan_ignored(sym: str) -> bool:
    """Operator allowlist for deliberate manual positions (comma-separated,
    default empty → nothing muted)."""
    raw = os.environ.get(ORPHAN_IGNORE_ENV, "")
    return _norm_symbol(sym) in {_norm_symbol(s) for s in raw.split(",") if s.strip()}


def _orphan_match(rec: dict):
    if rec.get("logger") != "efloud.exchange" or rec.get("level") != "WARNING":
        return None
    return _RE_ORPHAN.search(rec.get("message", ""))


@dataclass
class OrphanPositionRule(Rule):
    """Recurring reminder while an untracked (orphan) position exists.

    Backstop for the one-shot entry_rollback_failed alert: that event is
    logged once, so a failed Telegram send would lose it; the orphan line
    repeats every reconcile cycle, so this rule re-alerts hourly per
    (symbol, side) until the position is closed or tracked again. Same
    family as the SL rules ("a live position may lack bot protection") →
    same flag (EFLOUD_ALERTER_SL_ALERTS); deliberate manual positions are
    muted per symbol via EFLOUD_ALERTER_ORPHAN_IGNORE_SYMBOLS.

    Limits of the underlying detection (exchange code, unchanged here):
    - reconcile compares by SYMBOL only, so in hedge mode an orphan side next
      to a tracked opposite side on the same symbol is never logged (prod is
      one-way mode; fix = compare (symbol, side), separate trading-code task);
    - dry_run and a failed positions fetch return before orphan detection →
      no line, no alert for that cycle;
    - the detailed and the "details unavailable" line have different dedup
      keys (side vs '?'), so a symbol alternating between them may alert
      twice in an hour (rare)."""
    alert_key: str = "order.orphan_position"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 60 * 60
    ai_format: bool = False

    def match_log(self, rec: dict) -> Optional[str]:
        if not _flag_on(SL_ALERTS_ENV):
            return None
        m = _orphan_match(rec)
        if not m or _orphan_ignored(m["sym"]):
            return None
        if m["side"]:
            detail = (f"{_esc(m['sym'])} {_esc(m['side'])} · miktar {_esc(m['qty'])} · "
                      f"giriş {_esc(m['entry'])} · uPnL {_esc(m['upnl'])}")
        else:
            detail = f"{_esc(m['sym'])} · detay alınamadı"
        return ("🚨 <b>Borsada botun takip etmediği pozisyon var (orphan)</b>\n"
                f"{detail}\n"
                "Bot bu pozisyonu takip etmiyor; TP'sini ve kapanışını yönetmez. Orphan "
                "koruması `place_missing_sl` modundaysa (mid prod) SL yoksa varsayılan bir "
                "SL koymayı dener — döngü başına en fazla 1 pozisyon; emir okuması "
                "başarısızsa ya da SL fiyata çok yakınsa atlanır. `warn_only` modunda hiçbir "
                "emir koymaz. Bot dışında bilerek açılmadıysa (ör. geri alınamayan giriş) "
                "Binance'te kontrol et. Pozisyon durdukça saatte bir hatırlatılır "
                "(bilerek açılan sembol: EFLOUD_ALERTER_ORPHAN_IGNORE_SYMBOLS).")

    def dedup_key(self, rec: dict) -> str:
        m = _orphan_match(rec)
        if not m:
            return self.alert_key
        return f"{self.alert_key}.{m['sym']}.{m['side'] or '?'}"


# ─────────────────────────────────────────────────────────────────────
# Overseer watchdog (file-mtime driven)
# ─────────────────────────────────────────────────────────────────────


@dataclass
class OverseerHeartbeatStaleRule(Rule):
    """Watches the overseer sidecar from inside the alerter.

    Reads EFLOUD_OVERSEER_HEARTBEAT_FILE every healthz tick and CRITICAL-
    alerts when the file is missing OR its embedded `ts` (or legacy
    `alerter_heartbeat_ts`) is older than OVERSEER_HEARTBEAT_STALE_THRESHOLD_SEC.

    Why piggy-back on match_health(): the alerter already calls
    match_health(payload, history) on every 30s healthz poll, so a
    file-mtime rule that returns from inside match_health() inherits the
    existing dispatch cadence + dedup + rate limiting for free — no new
    polling loop required.

    Env var must be configured for the rule to do anything; missing env →
    silent no-op so a partial rollout (alerter deployed, overseer not yet)
    doesn't page on every healthz tick.
    """
    alert_key: str = "overseer.heartbeat_stale"
    severity: str = "CRITICAL"
    # 10 min dedup window — same as the stale threshold so we fire at most
    # once per bucket. (Operator gets one CRITICAL, then silence until either
    # overseer recovers or the window rolls over.)
    dedup_window_sec: int = 10 * 60

    def match_health(self, payload: dict, history: dict) -> Optional[str]:
        path_str = os.environ.get("EFLOUD_OVERSEER_HEARTBEAT_FILE", "")
        if not path_str:
            # No env → overseer not deployed; rule is a no-op (don't page).
            return None
        path = Path(path_str)
        now = int(time.time())

        if not path.exists():
            return (
                f"🚨 <b>Overseer heartbeat stale</b> (file missing)\n"
                f"Path: {path_str}\n"
                f"Investigate the overseer sidecar — it may be crashed or "
                f"disk-volume unmounted."
            )

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Unreadable / malformed file — treat as stale.
            return (
                f"🚨 <b>Overseer heartbeat stale</b> (unreadable)\n"
                f"Path: {path_str}"
            )

        # Accept both schemas: {"ts": ...} (overseer.state) and
        # {"alerter_heartbeat_ts": ...} (legacy alerter heartbeat).
        ts_raw = data.get("ts")
        if ts_raw is None:
            ts_raw = data.get("alerter_heartbeat_ts")
        if ts_raw is None:
            return (
                f"🚨 <b>Overseer heartbeat stale</b> (no ts in payload)\n"
                f"Path: {path_str}"
            )
        try:
            ts = int(ts_raw)
        except (TypeError, ValueError):
            return (
                f"🚨 <b>Overseer heartbeat stale</b> (bad ts payload)\n"
                f"Path: {path_str}"
            )

        age = now - ts
        if age <= OVERSEER_HEARTBEAT_STALE_THRESHOLD_SEC:
            return None
        age_min = age // 60
        # Format last-update as ISO for the human reader.
        last_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
        return (
            f"🚨 <b>Overseer heartbeat stale</b> (&gt;10min)\n"
            f"Last update: {last_iso} ({age_min}m ago)\n"
            f"Investigate."
        )


# ─────────────────────────────────────────────────────────────────────
# Exported list — alerter main loop iterates this
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# Long-hold reminder (T-20261108-04) — information only, nothing closes
# ─────────────────────────────────────────────────────────────────────

_HOLD_ID_RE = re.compile(r"\bid=(\S+)")
_HOLD_BUCKET_RE = re.compile(r"\bbucket=(\d+)")


@dataclass
class PositionHoldAgeRule(Rule):
    """Forwards the bot's '⏳ HOLD_AGE {sym} {dir} open {h}h bucket={n} | ... |
    id={pos_id}' warning (safety.hold_alert_hours). Dedup per position and bucket
    so a bot or alerter restart does not repeat a bucket. Raw text (no AI
    rewrite) so prices and the 'nothing closes' note stay exact."""
    alert_key: str = "position.hold_age"
    severity: str = "INFO"
    dedup_window_sec: int = 30 * 24 * 3600
    ai_format: bool = False

    def match_log(self, rec: dict) -> Optional[str]:
        if rec.get("logger") != "efloud.safe_orch" or rec.get("level") != "WARNING":
            return None
        msg = rec.get("message", "")
        if "HOLD_AGE" not in msg:
            return None
        body = msg.split("HOLD_AGE", 1)[1].strip()
        return f"⏳ <b>Uzun süredir açık pozisyon</b>\n{_esc(body)}"

    def dedup_key(self, rec: dict) -> str:
        msg = rec.get("message", "")
        pid = _HOLD_ID_RE.search(msg)
        bucket = _HOLD_BUCKET_RE.search(msg)
        return f"{self.alert_key}:{pid.group(1) if pid else '?'}:{bucket.group(1) if bucket else '?'}"


RULES: list[Rule] = [
    BreakerDailyRule(),
    BreakerWeeklyRule(),
    BreakerConsecutiveRule(),
    HealthCrashLoopRule(),
    HealthBreakerHaltedRule(),
    HealthUnhealthy15MinRule(),
    # Trade open / TP1 / close are sent directly by the bot (backend/notifications
    # TelegramNotifier on exchange events — every path, exchange-truth PnL) since
    # the real chat id was set 2026-11-08. These rules stay defined but inactive,
    # otherwise every event arrived twice.
    OverseerHeartbeatStaleRule(),
    LuxZoneAlertRule(),
    V2RejectAlertRule(),
    TpPlacementFailedRule(),
    SlUnprotectedRule(),
    SlProtectionEventRule(),
    VerifyNoReadRule(),
    AlgoFetchStreakRule(),
    OrphanPositionRule(),
    PositionHoldAgeRule(),
]
