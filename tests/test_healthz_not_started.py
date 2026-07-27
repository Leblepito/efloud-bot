"""healthz must not answer 503 while the operator has simply not pressed Start.

WHY THIS TEST EXISTS
--------------------
Measured on production 2026-07-27. The compose healthcheck hits /healthz with
`start_period: 600s, interval: 30s, retries: 3`, the containers carry
`labels: autoheal=true`, and they run with `EFLOUD_AUTOSTART=0` — so a fresh
container has no trading loop until a human opens the dashboard and presses
Start. `last_loop_tick_ms` therefore stayed None, healthz scored
`loop_tick_never` and returned 503, autoheal restarted the container, and the
600s start_period clock reset from zero. That is a closed cycle with a period of
about twelve minutes, and `docker logs efloud-autoheal` recorded it verbatim:

    08:00:30 Container /efloud-bot-scalp found to be unhealthy - Restarting
    08:12:41 Container /efloud-bot-scalp found to be unhealthy - Restarting
    08:24:52 Container /efloud-bot-scalp found to be unhealthy - Restarting
    08:37:02 Container /efloud-bot-scalp found to be unhealthy - Restarting
    09:08:14 Container /efloud-bot        found to be unhealthy - Restarting

Restarting a container cannot press Start, so 503 was never an answer autoheal
could act on. This is the same category the module already handles for
crash-loop suspension and breaker HALTED: intentional state, not transient
fault, therefore 200 + status "suspended".

WHAT MUST NOT REGRESS
---------------------
Narrowing autoheal's mandate is only safe if a genuinely dead bot still gets
restarted. BotRunner sets `running = True` at the end of a successful start and
sets it False only inside `stop()`; `_run_loop` catches Exception, records
`fatal_exception_state` and keeps looping without touching the flag. So a bot
that died mid-run still reports trading_started=True, and the tests below pin
that it still receives its 503.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.healthz import configure, evaluate_healthz, health_router
from engine.safety.runtime_state import RuntimeState

NOW = 10_000_000


@pytest.fixture
def state(tmp_path: Path) -> RuntimeState:
    return RuntimeState(state_dir=str(tmp_path))


def _clean(state: RuntimeState, now_ms: int = NOW) -> None:
    """A bot that is ticking and reaching the exchange."""
    state.last_loop_tick_ms = now_ms - 5_000
    state.last_exchange_ping_ms = now_ms - 5_000


# --- pure function ----------------------------------------------------------

class TestNotStartedBranch:

    def test_never_started_is_suspended_not_unhealthy(self, state):
        """The production case: fresh container, EFLOUD_AUTOSTART=0, nobody has
        pressed Start yet. No tick, no ping, and that is expected."""
        code, payload = evaluate_healthz(
            state, breaker_halted=False, now_ms=NOW, trading_started=False
        )
        assert code == 200, "503 here is what autoheal restart-looped on"
        assert payload["status"] == "suspended"
        assert payload["failures"] == ["trading_not_started"]

    def test_operator_stopped_a_healthy_bot_is_suspended(self, state):
        """Start pressed, bot ran fine, then Stop pressed. Ticks are still fresh
        at this instant; the point is that stopping is deliberate."""
        _clean(state)
        code, payload = evaluate_healthz(
            state, breaker_halted=False, now_ms=NOW, trading_started=False
        )
        assert code == 200
        assert payload["failures"] == ["trading_not_started"]

    def test_stopped_bot_with_fatal_flag_still_suspended(self, state):
        """A stopped bot that had errored earlier must not be restarted either —
        restarting still cannot press Start. The sticky fatal flag is reported by
        the alerter through `checks`, which stays populated."""
        _clean(state)
        state.fatal_exception_state = True
        state.fatal_exception_set_at_ms = NOW - 1_000
        code, payload = evaluate_healthz(
            state, breaker_halted=False, now_ms=NOW, trading_started=False
        )
        assert code == 200
        assert payload["failures"] == ["trading_not_started"]
        assert payload["checks"]["fatal_exception_state"] is True


class TestStartedBotStillGets503:
    """The whole safety argument for the new branch. If these go red, autoheal
    has been disarmed for real faults."""

    def test_started_but_never_ticked_is_503(self, state):
        code, payload = evaluate_healthz(
            state, breaker_halted=False, now_ms=NOW, trading_started=True
        )
        assert code == 503
        assert "loop_tick_never" in payload["failures"]

    def test_started_then_tick_went_stale_is_503(self, state):
        """Bot died mid-run. `running` stays True because _run_loop's except
        clause never clears it, so this is the path autoheal must keep."""
        _clean(state)
        state.last_loop_tick_ms = NOW - 91_000  # threshold is 90s
        code, payload = evaluate_healthz(
            state, breaker_halted=False, now_ms=NOW, trading_started=True
        )
        assert code == 503
        assert any("loop_tick_stale" in f for f in payload["failures"])

    def test_started_with_fatal_exception_is_503(self, state):
        _clean(state)
        state.fatal_exception_state = True
        state.fatal_exception_set_at_ms = NOW - 1_000
        code, payload = evaluate_healthz(
            state, breaker_halted=False, now_ms=NOW, trading_started=True
        )
        assert code == 503
        assert "fatal_exception" in payload["failures"]


class TestDefaultAndPrecedence:

    def test_default_is_started_so_old_callers_are_unchanged(self, state):
        """Omitting the argument must be byte-identical to trading_started=True.
        Three existing test modules and any embedder rely on this."""
        omitted = evaluate_healthz(state, breaker_halted=False, now_ms=NOW)
        explicit = evaluate_healthz(
            state, breaker_halted=False, now_ms=NOW, trading_started=True
        )
        assert omitted == explicit
        assert omitted[0] == 503

    def test_crash_loop_outranks_not_started(self, state):
        """Both are suspensions, but crash-loop is the more actionable label for
        the alerter, and it is checked first."""
        state.crash_count = 5
        state.last_crash_ms = int(__import__("time").time() * 1000)
        code, payload = evaluate_healthz(
            state, breaker_halted=False, now_ms=NOW, trading_started=False
        )
        assert code == 200
        assert payload["failures"] == ["crash_loop_suspended"]

    def test_breaker_halted_outranks_not_started(self, state):
        _clean(state)
        code, payload = evaluate_healthz(
            state, breaker_halted=True, now_ms=NOW, trading_started=False
        )
        assert code == 200
        assert payload["failures"] == ["breaker_halted"]


# --- endpoint wiring --------------------------------------------------------

def _app(rs: RuntimeState, halted=False, started_getter="unset"):
    if started_getter == "unset":
        configure(rs, lambda: halted)
    else:
        configure(rs, lambda: halted, started_getter)
    app = FastAPI()
    app.include_router(health_router)
    return TestClient(app)


class TestEndpointWiring:

    def test_getter_false_returns_200_suspended(self, state):
        client = _app(state, started_getter=lambda: False)
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["failures"] == ["trading_not_started"]

    def test_getter_true_and_no_tick_returns_503(self, state):
        client = _app(state, started_getter=lambda: True)
        r = client.get("/healthz")
        assert r.status_code == 503
        assert "loop_tick_never" in r.json()["failures"]

    def test_two_arg_configure_keeps_legacy_behaviour(self, state):
        """backend/tests and tests/test_healthz_endpoint.py call configure with
        two arguments. That must keep meaning 'assume started'."""
        client = _app(state)  # no third argument at all
        r = client.get("/healthz")
        assert r.status_code == 503
        assert "loop_tick_never" in r.json()["failures"]

    def test_raising_getter_fails_safe_towards_503(self, state):
        """Fail-safe direction matters: 'suspended' disables autoheal, so a
        broken getter must never be able to produce it."""
        def boom() -> bool:
            raise RuntimeError("status_snapshot blew up")

        client = _app(state, started_getter=boom)
        r = client.get("/healthz")
        assert r.status_code == 503
        assert "loop_tick_never" in r.json()["failures"]

    def test_started_and_clean_is_still_ok(self, state):
        state.update_loop_tick()
        state.update_exchange_ping()
        client = _app(state, started_getter=lambda: True)
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_autoheal_cycle_does_not_reproduce(state):
    """Replay of the 2026-07-27 incident, one probe per healthcheck attempt.

    Container comes up at t=0 with EFLOUD_AUTOSTART=0. Compose probes every 30s;
    the first 20 land inside start_period and are advisory, attempts 21-23 are
    the three retries that decided the container was unhealthy. Under the old
    code every one of these was a 503 and the 23rd handed the container to
    autoheal. None may be 503 now.
    """
    started = {"v": False}
    client = _app(state, started_getter=lambda: started["v"])

    for attempt in range(23):
        r = client.get("/healthz")
        assert r.status_code == 200, f"probe {attempt} returned 503 -> autoheal restarts"
        assert r.json()["failures"] == ["trading_not_started"]

    # Operator finally presses Start; the first cycle ticks.
    started["v"] = True
    state.update_loop_tick()
    state.update_exchange_ping()
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
