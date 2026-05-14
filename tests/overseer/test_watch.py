"""Overseer watch loop — orchestrates ingestors → rules → dedup → sinks.

tick() is the deterministic unit: builds a state dict, evaluates all rules,
dedups + dispatches. run_forever wraps tick() in an asyncio sleep loop with
a shutdown event for clean exit.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

import pytest


# ─────────────────────────────────────────────────────────────────────
# Test doubles — minimal stand-ins for the three ingestors + state + dedup.
# ─────────────────────────────────────────────────────────────────────


class _FakeLogTail:
    def __init__(self, recent=None):
        self._recent = recent or []

    def read_new(self):
        return self._recent

    def read_recent(self):
        return self._recent


class _FakeHealthzPoller:
    def __init__(self, state=None):
        self._state = state or {
            "status_code": 200,
            "last_ok_ts": 1_700_000_000,
            "consecutive_failures": 0,
        }
        self.poll_count = 0

    def poll_once(self):
        self.poll_count += 1
        return {
            "status_code": self._state["status_code"],
            "ok": self._state["status_code"] == 200,
            "checked_at": int(time.time()),
        }

    def state(self):
        return dict(self._state)


class _FakeJournalTail:
    def __init__(self, recent=None):
        self._recent = recent or []

    def read_recent(self):
        return list(self._recent)


class _FakeState:
    def __init__(self):
        self.heartbeat_count = 0
        self.heartbeat_file_count = 0

    def write_heartbeat(self):
        self.heartbeat_count += 1

    def write_heartbeat_file(self):
        self.heartbeat_file_count += 1


class _FakeDedup:
    """Tracks which keys have fired so duplicate keys return False on 2nd call."""
    def __init__(self, allow_keys: Optional[set] = None):
        self.seen: set = set()
        # If allow_keys is None, every NEW key fires once; if explicitly set,
        # only those keys ever fire (rest silently dedupe).
        self.allow_keys = allow_keys

    def should_fire(self, key, window_sec=None):
        if self.allow_keys is not None and key not in self.allow_keys:
            return False
        if key in self.seen:
            return False
        self.seen.add(key)
        return True


def _make_watch(
    log_tail=None,
    healthz_poller=None,
    journal_tail=None,
    state=None,
    dedup=None,
    rules=None,
    sink_telegram=None,
    dry_run=False,
):
    """Construct an OverseerWatch with sensible fake defaults; tests override
    only what they exercise."""
    from ops.overseer.watch import OverseerWatch

    w = OverseerWatch(
        log_path="/dev/null",
        healthz_url="http://x/healthz",
        journal_path="/dev/null",
        state=state or _FakeState(),
        dedup=dedup or _FakeDedup(),
        rules=rules or [],
        sink_telegram=sink_telegram,
        dry_run=dry_run,
    )
    # Swap real ingestors out for test doubles after construction; this keeps
    # the public ctor parametric on paths/URL (matching the production call site)
    # while still letting tests inject deterministic readers.
    w.log_tail = log_tail or _FakeLogTail()
    w.healthz_poller = healthz_poller or _FakeHealthzPoller()
    w.journal_tail = journal_tail or _FakeJournalTail()
    return w


# ─────────────────────────────────────────────────────────────────────
# tick() — state dict assembly + rule loop.
# ─────────────────────────────────────────────────────────────────────


async def test_watch_tick_builds_state_dict_with_required_keys():
    """tick() captures a state snapshot with the 6 keys rules.py docstring spec."""
    captured: dict = {}

    def _capture_rule_check(state):
        captured.update(state)
        return None

    from ops.overseer.rules import Rule
    rule = Rule(name="capture", check=_capture_rule_check)

    w = _make_watch(rules=[rule])
    await w.tick()

    required = {
        "now_ts", "log_lines", "healthz", "journal_recent",
        "audit_recent", "overseer_heartbeat_path",
    }
    assert required.issubset(captured.keys())


async def test_watch_tick_fires_alert_through_sink():
    """When a rule returns an Alert and dedup permits, sink is called with
    (text, severity) — proves end-to-end alert dispatch wiring."""
    from ops.overseer.rules import Alert, Rule

    def always_fire(_state):
        return Alert(
            text="test alert",
            severity="WARN",
            dedup_key="t1",
            rule_name="t1",
        )

    sink_calls: list[tuple] = []

    def fake_sink(text, severity):
        sink_calls.append((text, severity))
        return True

    w = _make_watch(
        rules=[Rule(name="t1", check=always_fire)],
        sink_telegram=fake_sink,
    )
    stats = await w.tick()

    assert len(sink_calls) == 1
    assert sink_calls[0] == ("test alert", "WARN")
    assert stats["alerts_fired"] == 1


async def test_watch_tick_dedups_repeated_alerts():
    """Same dedup_key fired twice → sink called once, alerts_deduped counter
    bumps on the 2nd attempt."""
    from ops.overseer.rules import Alert, Rule

    def always_fire(_state):
        return Alert(
            text="dup alert",
            severity="INFO",
            dedup_key="dup_key",
            rule_name="dup",
        )

    sink_calls: list[tuple] = []

    def fake_sink(text, severity):
        sink_calls.append((text, severity))
        return True

    w = _make_watch(
        rules=[Rule(name="dup", check=always_fire)],
        sink_telegram=fake_sink,
    )
    await w.tick()
    stats2 = await w.tick()

    assert len(sink_calls) == 1
    assert stats2["alerts_deduped"] == 1


async def test_watch_tick_dry_run_skips_sink_call():
    """dry_run=True → sink NEVER invoked, but alerts_fired counter still
    increments (so we know rule would have fired). Critical for Week 1
    observation deploy."""
    from ops.overseer.rules import Alert, Rule

    def always_fire(_state):
        return Alert(
            text="dryrun alert",
            severity="CRITICAL",
            dedup_key="dr1",
            rule_name="dr1",
        )

    sink_calls: list[tuple] = []

    def fake_sink(text, severity):
        sink_calls.append((text, severity))
        return True

    w = _make_watch(
        rules=[Rule(name="dr1", check=always_fire)],
        sink_telegram=fake_sink,
        dry_run=True,
    )
    stats = await w.tick()

    assert sink_calls == []
    assert stats["alerts_fired"] == 1  # would-have-fired still counts


async def test_watch_tick_rule_exception_isolates():
    """A throwing rule is caught + recorded in errors[] — other rules keep
    running. One broken rule must not silence the whole pipeline."""
    from ops.overseer.rules import Alert, Rule

    def boom(_state):
        raise RuntimeError("rule blew up")

    def calm(_state):
        return Alert(
            text="calm alert",
            severity="INFO",
            dedup_key="calm",
            rule_name="calm",
        )

    sink_calls: list[tuple] = []

    def fake_sink(text, severity):
        sink_calls.append((text, severity))
        return True

    w = _make_watch(
        rules=[
            Rule(name="boom", check=boom),
            Rule(name="calm", check=calm),
        ],
        sink_telegram=fake_sink,
    )
    stats = await w.tick()

    assert any("boom" in e for e in stats["errors"])
    assert stats["alerts_fired"] == 1
    assert sink_calls == [("calm alert", "INFO")]


async def test_watch_tick_writes_heartbeat():
    """Every tick must call state.write_heartbeat() — confirms liveness signal
    fires regardless of whether any rule matched."""
    state = _FakeState()
    w = _make_watch(state=state, rules=[])
    await w.tick()
    assert state.heartbeat_count == 1


async def test_watch_run_forever_respects_shutdown_event():
    """run_forever exits within 2s of shutdown_event.set() — clean shutdown
    on SIGTERM is mandatory for sidecar deployment."""
    w = _make_watch(rules=[])
    # Use a very short tick interval so the loop revisits the event quickly
    w.tick_sleep_sec = 0.05

    shutdown = asyncio.Event()
    task = asyncio.create_task(w.run_forever(shutdown))

    await asyncio.sleep(0.2)  # let it run a few ticks
    shutdown.set()

    try:
        await asyncio.wait_for(task, timeout=2.0)
    except asyncio.TimeoutError:
        task.cancel()
        pytest.fail("run_forever did not exit within 2s of shutdown_event")
