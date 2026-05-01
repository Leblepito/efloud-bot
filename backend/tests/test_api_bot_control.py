"""API tests for bot control endpoints — /api/bot/start, /stop, /restart.

Lifespan bypass + module-level runner state manipulated for deterministic asserts.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "test-password-123")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-long-enough!")
    monkeypatch.setenv("EFLOUD_CONFIG_PATH", "configs/__nonexistent__.yaml")
    monkeypatch.setenv("ENV", "dev")
    yield


@pytest.fixture
async def client():
    from backend.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def reset_runner():
    """Module singleton runner'ı test öncesi bilinen state'e getir."""
    from backend.bot_runner import runner
    runner.running = False
    runner.stopped = False
    runner.cycle_count = 0
    runner.last_error = None
    yield runner
    # Cleanup
    runner.running = False
    runner.stopped = False


async def _login(client):
    r = await client.post("/api/login", json={"password": "test-password-123"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_bot_start_requires_auth(client, reset_runner):
    r = await client.post("/api/bot/start")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_bot_stop_requires_auth(client, reset_runner):
    r = await client.post("/api/bot/stop")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_bot_restart_requires_auth(client, reset_runner):
    r = await client.post("/api/bot/restart")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_bot_start_with_missing_config_returns_running_false(client, reset_runner):
    """Config bulunamadığında start endpoint 200 döner ama running:false ve last_error dolu."""
    await _login(client)
    r = await client.post("/api/bot/start")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["running"] is False
    assert body["last_error"] is not None
    assert "config" in body["last_error"].lower()


@pytest.mark.asyncio
async def test_bot_start_idempotent_when_already_running(client, reset_runner):
    """Bot zaten running iken /api/bot/start → already_running:true döner."""
    reset_runner.running = True
    reset_runner.stopped = False
    await _login(client)
    r = await client.post("/api/bot/start")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body.get("already_running") is True


@pytest.mark.asyncio
async def test_bot_stop_returns_ok(client, reset_runner):
    """Bot stop endpoint her zaman 200 döner (idempotent)."""
    await _login(client)
    r = await client.post("/api/bot/stop")
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.asyncio
async def test_bot_restart_returns_ok(client, reset_runner):
    """Restart = stop + start. Config-not-found ortamında running:false döner."""
    await _login(client)
    r = await client.post("/api/bot/restart")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["running"] is False  # config yok


@pytest.mark.asyncio
async def test_status_includes_last_error_after_failed_start(client, reset_runner):
    """Failed start sonrası /api/status last_error field'ını taşımalı."""
    await _login(client)
    await client.post("/api/bot/start")
    r = await client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert "last_error" in body
    assert body["last_error"] is not None
