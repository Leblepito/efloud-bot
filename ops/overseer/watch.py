"""Main overseer event loop — ingestors → state dict → rules → dedup → sinks.

Cadence:
    LOG_TAIL_INTERVAL_SEC = 1.0     — pull new log lines every second
    HEALTHZ_POLL_INTERVAL_SEC = 30  — health check
    JOURNAL_TAIL_INTERVAL_SEC = 60  — refresh recent-trades cache
    RULE_EVAL_INTERVAL_SEC = 10     — evaluate all rules
    HEARTBEAT_INTERVAL_SEC = 60     — refresh state.heartbeat

`tick()` is the single deterministic unit: it polls every ingestor, assembles
the state dict, evaluates each rule, dedups, dispatches. We collapse the five
cadences into "run all sub-steps per tick" because the rules are cheap pure
functions and the heaviest I/O (healthz) is already a sub-second urllib call.
This keeps the loop trivially testable — one tick == one snapshot.

DRY_RUN mode (env EFLOUD_OVERSEER_DRY_RUN=1 or constructor flag): rules still
fire and dedup still tracks state, but the telegram sink is bypassed and the
alert text is logged instead. Mandatory for the Week 1 observation deploy per
the plan rollout.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Callable, Optional

def _elapsed_or_first(last_ts: Optional[float], interval_sec: float) -> bool:
    """Return True if enough time has elapsed since last_ts, or last_ts is None (first run)."""
    if last_ts is None:
        return True
    return (time.monotonic() - last_ts) >= interval_sec

from ops.overseer.dedup import OverseerDedup
from ops.overseer.ingestors.healthz_poller import HealthzPoller
from ops.overseer.ingestors.journal_tail import JournalTail
from ops.overseer.ingestors.log_tail import JsonLogTail
from ops.overseer.rules import Rule
from ops.overseer.state import OverseerState

log = logging.getLogger("efloud.overseer.watch")

# Cadences (mirrored from ops.alerter.alerter; consumers can override on the
# instance for tests via .tick_sleep_sec)
LOG_TAIL_INTERVAL_SEC = 1.0
HEALTHZ_POLL_INTERVAL_SEC = 30.0
JOURNAL_TAIL_INTERVAL_SEC = 60.0
RULE_EVAL_INTERVAL_SEC = 10.0
HEARTBEAT_INTERVAL_SEC = 60.0


class OverseerWatch:
    """Long-running overseer agent. Designed as a sidecar container, so it
    owns its own asyncio loop (run_forever) but is structured around a pure
    tick() method for deterministic test stepping.
    """

    def __init__(
        self,
        log_path: str,
        healthz_url: str,
        journal_path: str,
        state: OverseerState,
        dedup: OverseerDedup,
        rules: list[Rule],
        sink_telegram: Optional[Callable[[str, str], bool]] = None,
        dry_run: bool = False,
    ):
        """Wire up ingestors against the configured paths/URL. The ingestors
        are stored as plain attributes so tests can swap them for fakes after
        construction without re-implementing the public ctor signature."""
        self.state = state
        self.dedup = dedup
        self.rules = list(rules)
        self.sink_telegram = sink_telegram
        self.dry_run = dry_run

        self.log_tail: Any = JsonLogTail(log_path)
        self.healthz_poller: Any = HealthzPoller(healthz_url)
        self.journal_tail: Any = JournalTail(journal_path)

        # Default sleep between ticks; tests shrink this for fast loops.
        self.tick_sleep_sec: float = RULE_EVAL_INTERVAL_SEC

        # Cadence tracking — monotonic timestamps of last ingestor run.
        self._last_log_ts: Optional[float] = None
        self._last_healthz_ts: Optional[float] = None
        self._last_journal_ts: Optional[float] = None
        self._last_heartbeat_ts: Optional[float] = None
        # Cached journal result so rules see the last read even between refreshes.
        self._journal_cache: list[dict] = []

    async def tick(self) -> dict[str, Any]:
        """One full pass: ingest → state → rules → dispatch. Returns counters
        + error list so tests (and operators tailing logs) can assert behaviour.

        Always writes a heartbeat — liveness must survive even if every rule
        raises, otherwise the alerter would inevitably alert about a dead
        overseer that was actually fine.
        """
        stats: dict[str, Any] = {
            "alerts_fired": 0,
            "alerts_deduped": 0,
            "rules_evaluated": 0,
            "errors": [],
        }

        # 1. Poll ingestors — each only runs at its own cadence.
        now_mono = time.monotonic()
        if _elapsed_or_first(self._last_log_ts, LOG_TAIL_INTERVAL_SEC):
            try:
                self.log_tail.read_new()
                self._last_log_ts = now_mono
            except Exception as e:
                stats["errors"].append(f"log_tail: {e}")

        if _elapsed_or_first(self._last_healthz_ts, HEALTHZ_POLL_INTERVAL_SEC):
            try:
                self.healthz_poller.poll_once()
                self._last_healthz_ts = now_mono
            except Exception as e:
                stats["errors"].append(f"healthz_poll: {e}")

        # 2. Assemble state dict per rules.py docstring contract.
        try:
            log_lines = self.log_tail.read_recent()
        except Exception as e:
            log_lines = []
            stats["errors"].append(f"log_recent: {e}")

        try:
            healthz_state = self.healthz_poller.state()
        except Exception as e:
            healthz_state = {}
            stats["errors"].append(f"healthz_state: {e}")

        if _elapsed_or_first(self._last_journal_ts, JOURNAL_TAIL_INTERVAL_SEC):
            try:
                self._journal_cache = self.journal_tail.read_recent()
                self._last_journal_ts = now_mono
            except Exception as e:
                stats["errors"].append(f"journal_tail: {e}")
        journal_recent = self._journal_cache

        state_dict: dict[str, Any] = {
            "now_ts": int(time.time()),
            "log_lines": log_lines,
            "healthz": healthz_state,
            "journal_recent": journal_recent,
            # audit_recent: wired in Task D; for now graceful None so the
            # audit_score_dropping rule short-circuits silently.
            "audit_recent": None,
            "overseer_heartbeat_path": os.environ.get(
                "EFLOUD_OVERSEER_HEARTBEAT_FILE"
            ),
        }

        # 3. Evaluate each rule. A throwing rule is logged + counted but does
        #    NOT abort the loop — one buggy rule cannot silence the rest.
        for rule in self.rules:
            stats["rules_evaluated"] += 1
            try:
                alert = rule.check(state_dict)
            except Exception as e:
                stats["errors"].append(f"{rule.name}: {e}")
                log.warning(f"rule {rule.name} raised: {e}")
                continue
            if alert is None:
                continue

            # 4. Dedup gate. Same key inside the dedup window → silenced.
            try:
                should = self.dedup.should_fire(alert.dedup_key)
            except Exception as e:
                stats["errors"].append(f"dedup({rule.name}): {e}")
                continue
            if not should:
                stats["alerts_deduped"] += 1
                continue

            # 5. Dispatch (or DRY_RUN log).
            if self.dry_run:
                log.info(f"[DRY_RUN] alert: {alert.text}")
                stats["alerts_fired"] += 1
            elif self.sink_telegram is not None:
                try:
                    ok = self.sink_telegram(alert.text, alert.severity)
                except Exception as e:
                    stats["errors"].append(f"sink({rule.name}): {e}")
                    continue
                if ok:
                    stats["alerts_fired"] += 1
            else:
                # No sink wired (mis-config) — count as fired so operator sees
                # the rule activity in stats; rely on the warning log to flag
                # the missing transport.
                log.warning(
                    f"no sink_telegram configured — alert '{rule.name}' dropped"
                )
                stats["alerts_fired"] += 1

        # 6. Heartbeat — mandatory, even if everything above blew up. Wrapped
        #    in try so an unhealthy SQLite doesn't kill the loop entirely.
        try:
            self.state.write_heartbeat()
        except Exception as e:
            stats["errors"].append(f"heartbeat: {e}")

        # Mirror to the optional JSON heartbeat file (no-op when env unset).
        try:
            self.state.write_heartbeat_file()
        except Exception as e:
            stats["errors"].append(f"heartbeat_file: {e}")

        return stats

    async def run_forever(self, shutdown_event: asyncio.Event) -> None:
        """Drive tick() in a loop until shutdown_event is set.

        Uses asyncio.wait_for on the event with a per-tick timeout so we get
        prompt shutdown without busy-polling: the wait wakes either when the
        sleep elapses (normal tick) or when shutdown_event is set (clean exit).
        """
        log.info("overseer watch loop starting")
        while not shutdown_event.is_set():
            try:
                await self.tick()
            except Exception as e:  # pragma: no cover — defensive net
                log.exception(f"tick raised unexpectedly: {e}")
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=self.tick_sleep_sec,
                )
            except asyncio.TimeoutError:
                # Expected — timeout means another tick should run.
                continue
        log.info("overseer watch loop exiting (shutdown event)")
