"""Birleşik panel (panel/main.py) — auth, cache, aksiyon ve XSS-pin testleri.

Bot API'lerine ağ çağrısı YAPILMAZ; _bot_overview/_bot_req monkeypatch'lenir.
"""
from __future__ import annotations

import base64

import pytest
from httpx import ASGITransport, AsyncClient

import panel.main as panel_main


def _basic(user: str, pw: str) -> dict:
    tok = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {tok}"}


@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "panel-test-pw-123456")
    monkeypatch.delenv("DASHBOARD_USERNAME", raising=False)
    # Her test taze cache ile başlasın
    panel_main._overview_cache.update(ts=0.0, data=None)
    panel_main._sessions.clear()
    yield


@pytest.fixture
def client():
    transport = ASGITransport(app=panel_main.app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def stub_overview(monkeypatch):
    """_bot_overview'u ağsız stub'la; çağrı sayacı döndürür."""
    calls = {"n": 0}

    async def fake_overview(client, bot_id):
        calls["n"] += 1
        return {"id": bot_id, "name": panel_main.BOTS[bot_id]["name"],
                "status": {"running": True, "breaker_state": "OPEN"},
                "positions": [], "equity": [], "history": []}

    monkeypatch.setattr(panel_main, "_bot_overview", fake_overview)
    return calls


# ── auth ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_healthz_no_auth(client):
    async with client as ac:
        r = await ac.get("/healthz")
    assert r.status_code == 200 and r.json()["ok"] is True


@pytest.mark.asyncio
async def test_overview_requires_auth(client):
    async with client as ac:
        r = await ac.get("/api/overview")
    assert r.status_code == 401
    assert "Basic" in r.headers.get("www-authenticate", "")


@pytest.mark.asyncio
async def test_missing_password_env_returns_503(client, monkeypatch):
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    async with client as ac:
        r = await ac.get("/api/overview", headers=_basic("x", "whatever"))
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_wrong_password_401(client):
    async with client as ac:
        r = await ac.get("/api/overview", headers=_basic("x", "wrong"))
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_any_username_ok_when_username_not_configured(client, stub_overview):
    async with client as ac:
        r = await ac.get("/api/overview", headers=_basic("anyone", "panel-test-pw-123456"))
    assert r.status_code == 200
    assert set(r.json()["bots"].keys()) == set(panel_main.BOTS.keys())


@pytest.mark.asyncio
async def test_username_enforced_when_configured(client, stub_overview, monkeypatch):
    monkeypatch.setenv("DASHBOARD_USERNAME", "efloud")
    async with client as ac:
        bad = await ac.get("/api/overview", headers=_basic("intruder", "panel-test-pw-123456"))
        ok = await ac.get("/api/overview", headers=_basic("efloud", "panel-test-pw-123456"))
    assert bad.status_code == 401
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_password_env_read_at_call_time(client, stub_overview, monkeypatch):
    """Rotasyon senaryosu: env değişince yeni şifre restart'sız geçerli olmalı."""
    monkeypatch.setenv("DASHBOARD_PASSWORD", "rotated-pw-654321")
    async with client as ac:
        old = await ac.get("/api/overview", headers=_basic("x", "panel-test-pw-123456"))
        new = await ac.get("/api/overview", headers=_basic("x", "rotated-pw-654321"))
    assert old.status_code == 401
    assert new.status_code == 200


# ── cache ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_overview_cached_within_window(client, stub_overview):
    async with client as ac:
        await ac.get("/api/overview", headers=_basic("x", "panel-test-pw-123456"))
        first_calls = stub_overview["n"]
        await ac.get("/api/overview", headers=_basic("x", "panel-test-pw-123456"))
    assert first_calls == len(panel_main.BOTS)
    assert stub_overview["n"] == first_calls  # ikinci istek cache'ten


# ── aksiyonlar ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_action_unknown_bot_or_action_404(client):
    async with client as ac:
        r1 = await ac.post("/api/bot/nope/start", headers=_basic("x", "panel-test-pw-123456"))
        r2 = await ac.post("/api/bot/v1/self-destruct", headers=_basic("x", "panel-test-pw-123456"))
    assert r1.status_code == 404 and r2.status_code == 404


@pytest.mark.asyncio
async def test_restart_action_proxies(client, monkeypatch):
    seen = {}

    async def fake_req(client_, bot_id, method, path):
        seen.update(bot=bot_id, method=method, path=path)
        return {"ok": True}

    monkeypatch.setattr(panel_main, "_bot_req", fake_req)
    async with client as ac:
        r = await ac.post("/api/bot/v2/restart", headers=_basic("x", "panel-test-pw-123456"))
    assert r.status_code == 200
    assert seen == {"bot": "v2", "method": "POST", "path": "/api/bot/restart"}


# ── XSS pinleri ──────────────────────────────────────────────────────
# PAGE inline-JS innerHTML ile render eder; bot API'sinden gelen serbest
# metin (last_error, error, sembol) esc()'ten geçmek ZORUNDA.


def test_page_has_esc_helper():
    assert "function esc(" in panel_main.PAGE


@pytest.mark.parametrize("needle", [
    "esc(b.error)",
    "esc(String(st.last_error)",
    "esc(p.symbol",
    "esc(t.symbol",
])
def test_page_escapes_dynamic_fields(needle):
    assert needle in panel_main.PAGE, f"PAGE içinde beklenen escape yok: {needle}"


def test_page_survives_missing_chartjs():
    """CDN erişilemezse sayfa çökmemeli — typeof Chart guard'ı pinli."""
    assert 'typeof Chart' in panel_main.PAGE


# Bot API'lerinin GERÇEK alan adları — eski panel entryPrice/unrealizedPnl
# bekliyordu, sütunlar hep "—" kalıyordu (2026-08-12 audit HIGH bulgusu).
@pytest.mark.parametrize("needle", [
    "p.unrealized_usdt",   # /api/positions uPnL alanı
    "p.entry ??",          # /api/positions giriş fiyatı alanı
    "t.pnl_usdt",          # /api/history DB-yolu PnL alanı
    "t.closed_at",         # /api/history DB-yolu zaman alanı
])
def test_page_reads_real_bot_api_fields(needle):
    assert needle in panel_main.PAGE, f"PAGE gerçek API alanını okumuyor: {needle}"
