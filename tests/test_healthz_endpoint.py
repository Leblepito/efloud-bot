"""Healthz endpoint integration tests — verify wiring + status code semantics."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.safety.runtime_state import RuntimeState


@pytest.fixture
def configured_app(tmp_path: Path):
    """Build a FastAPI app with healthz wired to a fresh RuntimeState we control."""
    from fastapi import FastAPI
    from backend.healthz import health_router, configure

    rs = RuntimeState(state_dir=str(tmp_path))

    breaker_halted = {"v": False}  # mutable wrapper; tests flip it

    def get_halted() -> bool:
        return breaker_halted["v"]

    configure(rs, get_halted)

    app = FastAPI()
    app.include_router(health_router)
    return app, rs, breaker_halted


def test_healthz_endpoint_returns_200_when_clean(configured_app):
    app, rs, _ = configured_app
    # Simulate clean state: recent tick + ping
    rs.update_loop_tick()
    rs.update_exchange_ping()

    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["failures"] == []


def test_healthz_endpoint_returns_503_when_unhealthy(configured_app):
    app, rs, breaker = configured_app
    # Don't call update_loop_tick — last_loop_tick_ms remains None
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unhealthy"
    assert "loop_tick_never" in body["failures"]


def test_healthz_payload_shape(configured_app):
    app, rs, _ = configured_app
    rs.update_loop_tick()
    rs.update_exchange_ping()
    client = TestClient(app)
    r = client.get("/healthz")
    body = r.json()
    # Required keys
    for key in ("status", "checks", "now_ms", "failures"):
        assert key in body, f"missing key: {key}"
    # Checks sub-shape
    for key in ("last_loop_tick_ms", "last_exchange_ping_ms",
                "fatal_exception_state", "crash_count"):
        assert key in body["checks"], f"missing checks key: {key}"
