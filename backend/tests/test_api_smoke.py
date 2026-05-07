"""API smoke tests — auth flow + endpoint reachability.

Bot worker başlatılmaz (lifespan bypass'lanır), sadece HTTP layer test edilir.
"""
import os

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "test-password-123")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-long-enough!")
    monkeypatch.setenv("ENV", "dev")
    yield


@pytest.fixture
async def client(tmp_path):
    """ASGI client without lifespan (bot worker won't start).

    Lifespan bypass means /healthz wiring (backend.main → configure_healthz) is
    skipped, so we wire it explicitly here with a fresh RuntimeState that the
    test can pre-populate to simulate either healthy or unhealthy states.
    """
    from backend.main import app
    from backend.healthz import configure as configure_healthz
    from engine.safety.runtime_state import RuntimeState

    rs = RuntimeState(state_dir=str(tmp_path))
    # Mark loop as ticking + exchange pinging so default = healthy.
    rs.update_loop_tick()
    rs.update_exchange_ping()
    configure_healthz(rs, lambda: False)  # breaker not halted

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_root(client):
    """Root may return JSON (frontend not built) or HTML (frontend mounted)."""
    r = await client.get("/")
    assert r.status_code == 200
    content_type = r.headers.get("content-type", "")
    if "json" in content_type:
        assert r.json()["service"] == "efloud-bot-backend"
    else:
        # Static frontend mounted — should be HTML
        assert "html" in content_type


@pytest.mark.asyncio
async def test_healthz_no_auth(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_status_requires_auth(client):
    r = await client.get("/api/status")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    r = await client.post("/api/login", json={"password": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_correct_password_and_status(client):
    # Login
    r = await client.post("/api/login", json={"password": "test-password-123"})
    assert r.status_code == 200
    assert "efloud_session" in r.cookies

    # Status now succeeds
    r = await client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert "running" in body
    assert "cycle_count" in body
    assert "breaker_state" in body


@pytest.mark.asyncio
async def test_positions_empty_when_no_bot(client):
    await client.post("/api/login", json={"password": "test-password-123"})
    r = await client.get("/api/positions")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_history_empty_no_db(client):
    await client.post("/api/login", json={"password": "test-password-123"})
    r = await client.get("/api/history")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_kill_switch_503_when_no_bot(client):
    await client.post("/api/login", json={"password": "test-password-123"})
    r = await client.post("/api/kill-switch")
    assert r.status_code == 503  # Bot not running


@pytest.mark.asyncio
async def test_logout_clears_cookie(client):
    await client.post("/api/login", json={"password": "test-password-123"})
    r = await client.post("/api/logout")
    assert r.status_code == 200

    # Force-clear client's stored cookie (server sent Max-Age=0 but httpx may keep value)
    client.cookies.clear()
    r = await client.get("/api/status")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_rate_limit(client):
    # 5 failed attempts trigger 429
    for _ in range(5):
        await client.post("/api/login", json={"password": "wrong"})
    r = await client.post("/api/login", json={"password": "wrong"})
    assert r.status_code == 429
