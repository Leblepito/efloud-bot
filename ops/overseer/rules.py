"""Overseer deterministic rule engine — pure functions over a state snapshot.

Each rule is a side-effect-free callable that takes a state dict and returns
Optional[Alert]. The orchestrator (watch.py, Task C) iterates OVERSEER_RULES,
hands the state to each rule, and routes any returned Alert through dedup +
sinks. Keeping the rules pure lets us unit-test them without faking sinks,
timers, or DB connections.

state dict shape (filled by watch.py at runtime):
    {
        "now_ts": int — UTC seconds at evaluation time,
        "log_lines": list[dict] — last N parsed JSON log lines
            (each dict carries event/ts plus rule-specific fields like
             symbol/regime),
        "healthz": {
            "status_code": int,
            "last_ok_ts": int | None,
            "consecutive_failures": int,
        },
        "journal_recent": list[dict] — last N closed trade snapshots,
            each at minimum {"trade_id", "realized_pnl"},
        "audit_recent": list[dict] | None — last N audit rows
            (None means audit infra is disabled / not yet populated),
        "overseer_heartbeat_path": str | None — optional path the file rule
            (future) will parse,
    }

Rules MUST NOT mutate state. tests/overseer/test_rules.py asserts this via
a deepcopy round-trip — keep it that way.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any, Callable, Optional


# ─────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Alert:
    """Single alert emission. Frozen so rules can't mutate after return."""
    text: str
    severity: str  # INFO | WARN | CRITICAL
    dedup_key: str  # idempotency key, fed to OverseerDedup.should_fire
    rule_name: str  # observability — emitted in alerter log line


@dataclass(frozen=True)
class Rule:
    """Pairs a stable name (for registry/observability) with a check fn."""
    name: str
    check: Callable[[dict[str, Any]], Optional[Alert]]


# ─────────────────────────────────────────────────────────────────────
# Tunable thresholds — kept at module scope so future config wiring is trivial.
# ─────────────────────────────────────────────────────────────────────

CYCLE_GAP_MAX_SEC = 5 * 60          # 5 min between cycle_start events
CONSECUTIVE_LOSS_N = 5              # N straight losses to alert
AUDIT_MEDIAN_THRESHOLD = 5.0        # median overall_score below this → alert
AUDIT_MIN_ROWS = 10                 # need this many rows for a meaningful median
REGIME_WINDOW_SEC = 10 * 60         # flipflop window
REGIME_CHANGES_THRESHOLD = 4        # ≥ this many changes inside window → alert
REVERSE_BLOCK_WINDOW_SEC = 30 * 60  # streak window
REVERSE_BLOCK_THRESHOLD = 3         # ≥ this many blocks inside window → alert
REVERSE_BLOCK_EVENT = "REVERSE_BLOCKED_NOT_PROFITABLE"


# ─────────────────────────────────────────────────────────────────────
# Rules
# ─────────────────────────────────────────────────────────────────────


def rule_bot_unhealthy(state: dict[str, Any]) -> Optional[Alert]:
    """Fires CRITICAL when healthz has failed >= 3 times in a row — fast signal
    that the bot loop is wedged or the process is dead."""
    healthz = state.get("healthz") or {}
    consecutive = int(healthz.get("consecutive_failures", 0))
    if consecutive < 3:
        return None
    last_ok = healthz.get("last_ok_ts")
    last_ok_repr = "never" if last_ok in (None, 0) else str(last_ok)
    text = (
        f"\U0001F6A8 Bot healthcheck FAIL ({consecutive} ardisik). "
        f"Son OK: {last_ok_repr}"
    )
    return Alert(
        text=text,
        severity="CRITICAL",
        dedup_key="bot_unhealthy",
        rule_name="bot_unhealthy",
    )


def rule_cycle_gap(state: dict[str, Any]) -> Optional[Alert]:
    """Fires WARN when the most recent cycle_start log line is older than
    CYCLE_GAP_MAX_SEC — bot loop appears stalled even if healthz hasn't
    flipped yet (e.g. orchestrator stuck inside an exchange call)."""
    cycle_lines = [
        line for line in state.get("log_lines", [])
        if line.get("event") == "cycle_start" and "ts" in line
    ]
    if not cycle_lines:
        return None
    last_ts = max(int(line["ts"]) for line in cycle_lines)
    now = int(state["now_ts"])
    if now - last_ts <= CYCLE_GAP_MAX_SEC:
        return None
    gap = now - last_ts
    text = (
        f"⚠️ Cycle gap detected: {gap}s since last cycle_start "
        f"(threshold {CYCLE_GAP_MAX_SEC}s)."
    )
    return Alert(
        text=text,
        severity="WARN",
        dedup_key=f"cycle_gap:{last_ts}",
        rule_name="cycle_gap",
    )


def rule_consecutive_losses(state: dict[str, Any]) -> Optional[Alert]:
    """Fires WARN when the last CONSECUTIVE_LOSS_N closed trades are all
    realized losses — early warning of strategy drift / regime mismatch.

    Dedup key pinned to the most-recent trade_id so the alert fires once per
    streak even if watch.py re-evaluates rules every minute."""
    journal = state.get("journal_recent") or []
    if len(journal) < CONSECUTIVE_LOSS_N:
        return None
    tail = journal[-CONSECUTIVE_LOSS_N:]
    if not all(float(t.get("realized_pnl", 0.0)) < 0.0 for t in tail):
        return None
    last_id = tail[-1].get("trade_id", "unknown")
    text = (
        f"⚠️ {CONSECUTIVE_LOSS_N} ardisik kayip "
        f"(son trade: {last_id})."
    )
    return Alert(
        text=text,
        severity="WARN",
        dedup_key=f"consec_loss:{last_id}",
        rule_name="consecutive_losses",
    )


def rule_audit_score_dropping(state: dict[str, Any]) -> Optional[Alert]:
    """Fires WARN when the median overall_score across the last AUDIT_MIN_ROWS
    audit entries falls below AUDIT_MEDIAN_THRESHOLD.

    audit_recent is intentionally Optional — when audit infra is disabled or
    not yet populated (audit_recent is None), the rule skips silently so we
    never spam alerts about a feature that isn't running.
    Dedup key includes today's UTC date so the rule fires at most once per day."""
    audits = state.get("audit_recent")
    if audits is None:
        return None
    if len(audits) < AUDIT_MIN_ROWS:
        return None
    tail = audits[-AUDIT_MIN_ROWS:]
    scores = [float(row.get("overall_score", 0.0)) for row in tail]
    med = median(scores)
    if med >= AUDIT_MEDIAN_THRESHOLD:
        return None
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    text = (
        f"⚠️ Audit median dusuyor: {med:.2f} "
        f"(< {AUDIT_MEDIAN_THRESHOLD}) son {AUDIT_MIN_ROWS} kayit."
    )
    return Alert(
        text=text,
        severity="WARN",
        dedup_key=f"audit_drop:date={today_iso}",
        rule_name="audit_score_dropping",
    )


def rule_regime_flipflop(state: dict[str, Any]) -> Optional[Alert]:
    """Fires WARN when a single symbol logs >= REGIME_CHANGES_THRESHOLD regime
    changes inside the last REGIME_WINDOW_SEC seconds — regime detector is
    oscillating and signals derived from it are likely noise.

    Dedup key buckets time by the 10-min window so repeated flapping inside
    the same bucket only alerts once."""
    now = int(state["now_ts"])
    cutoff = now - REGIME_WINDOW_SEC
    by_symbol: dict[str, list[int]] = {}
    for line in state.get("log_lines", []):
        if line.get("event") != "regime_change":
            continue
        ts = line.get("ts")
        symbol = line.get("symbol")
        if ts is None or symbol is None:
            continue
        if int(ts) < cutoff:
            continue
        by_symbol.setdefault(symbol, []).append(int(ts))

    # First symbol that crosses the threshold wins this tick — if two symbols
    # flap simultaneously the others surface on the next eval cycle (their
    # own ts_list keeps growing; dedup window prevents spam).
    for symbol, ts_list in by_symbol.items():
        if len(ts_list) >= REGIME_CHANGES_THRESHOLD:
            last_ts = max(ts_list)
            bucket = last_ts // REGIME_WINDOW_SEC
            text = (
                f"⚠️ Regime flipflop {symbol}: {len(ts_list)} change "
                f"in {REGIME_WINDOW_SEC // 60}min."
            )
            return Alert(
                text=text,
                severity="WARN",
                dedup_key=f"regime_flipflop:{symbol}:{bucket}",
                rule_name="regime_flipflop",
            )
    return None


def rule_reverse_block_streak(state: dict[str, Any]) -> Optional[Alert]:
    """Fires INFO when >= REVERSE_BLOCK_THRESHOLD REVERSE_BLOCKED_NOT_PROFITABLE
    events accumulate inside the last REVERSE_BLOCK_WINDOW_SEC seconds — operator
    visibility into 'reverse signals coming but all rejected by the new
    profit-only-reverse guard from PR #61'.

    Symbol-agnostic by design: a string of blocks across different symbols is
    still a signal worth surfacing.
    Dedup key buckets by the 30-min window."""
    now = int(state["now_ts"])
    cutoff = now - REVERSE_BLOCK_WINDOW_SEC
    matches = [
        int(line["ts"]) for line in state.get("log_lines", [])
        if line.get("event") == REVERSE_BLOCK_EVENT
        and "ts" in line
        and int(line["ts"]) >= cutoff
    ]
    if len(matches) < REVERSE_BLOCK_THRESHOLD:
        return None
    last_ts = max(matches)
    bucket = last_ts // REVERSE_BLOCK_WINDOW_SEC
    text = (
        f"ℹ️ Reverse-block streak: {len(matches)} block "
        f"in {REVERSE_BLOCK_WINDOW_SEC // 60}min."
    )
    return Alert(
        text=text,
        severity="INFO",
        dedup_key=f"reverse_block_streak:{bucket}",
        rule_name="reverse_block_streak",
    )


# ─────────────────────────────────────────────────────────────────────
# Registry — watch.py iterates this list in order.
# ─────────────────────────────────────────────────────────────────────

OVERSEER_RULES: list[Rule] = [
    Rule(name="bot_unhealthy", check=rule_bot_unhealthy),
    Rule(name="cycle_gap", check=rule_cycle_gap),
    Rule(name="consecutive_losses", check=rule_consecutive_losses),
    Rule(name="audit_score_dropping", check=rule_audit_score_dropping),
    Rule(name="regime_flipflop", check=rule_regime_flipflop),
    Rule(name="reverse_block_streak", check=rule_reverse_block_streak),
]
