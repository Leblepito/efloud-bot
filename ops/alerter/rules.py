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
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

# Healthz consecutive-failure threshold: 15 minutes
UNHEALTHY_15MIN_THRESHOLD_SEC = 15 * 60


@dataclass
class Rule:
    """Base rule. Subclasses override match_log and/or match_health."""
    alert_key: str = ""
    severity: str = "WARNING"  # "WARNING" or "CRITICAL"
    dedup_window_sec: int = 30 * 60

    def match_log(self, rec: dict) -> Optional[str]:
        """Given a parsed JSON log line dict, return formatted alert text or None."""
        return None

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
            return f"🚨 <b>Breaker TRIPPED — daily loss limit</b>\n{msg}"
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
            return f"🚨 <b>Breaker HALTED — weekly drawdown</b>\n{msg}"
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
            return f"⚠️ <b>Breaker TRIPPED — consecutive losses</b>\n{msg}"
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
# Exported list — alerter main loop iterates this
# ─────────────────────────────────────────────────────────────────────

RULES: list[Rule] = [
    BreakerDailyRule(),
    BreakerWeeklyRule(),
    BreakerConsecutiveRule(),
    HealthCrashLoopRule(),
    HealthUnhealthy15MinRule(),
    TradeOpenedRule(),
    TP1HitRule(),
    TradeClosedRule(),
]
