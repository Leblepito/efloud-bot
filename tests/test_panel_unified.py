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
        r1 = await ac.post("/api/bot/nope/start", headers={**_basic("x", "panel-test-pw-123456"), **PANEL_HDR})
        r2 = await ac.post("/api/bot/v1/self-destruct", headers={**_basic("x", "panel-test-pw-123456"), **PANEL_HDR})
    assert r1.status_code == 404 and r2.status_code == 404


@pytest.mark.asyncio
async def test_restart_action_proxies(client, monkeypatch):
    seen = {}

    async def fake_req(client_, bot_id, method, path):
        seen.update(bot=bot_id, method=method, path=path)
        return {"ok": True}

    monkeypatch.setattr(panel_main, "_bot_req", fake_req)
    async with client as ac:
        r = await ac.post("/api/bot/v2/restart", headers={**_basic("x", "panel-test-pw-123456"), **PANEL_HDR})
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


# ── CSRF + brute-force (T-20261107-06, security audit T-20261106-06) ─────
# Browsers attach cached HTTP Basic credentials to cross-site form POSTs too,
# so state-changing actions must prove same-origin (custom header → a
# cross-site request needs a CORS preflight the panel never grants).

PW = "panel-test-pw-123456"
PANEL_HDR = {"X-Efloud-Panel": "1"}


@pytest.fixture
def stub_action(monkeypatch):
    seen = []

    async def fake_req(client_, bot_id, method, path):
        seen.append((bot_id, method, path))
        return {"ok": True}

    monkeypatch.setattr(panel_main, "_bot_req", fake_req)
    return seen


@pytest.fixture(autouse=True)
def reset_auth_failures():
    panel_main._auth_failures.clear()
    yield
    panel_main._auth_failures.clear()


@pytest.mark.asyncio
async def test_action_without_panel_header_is_rejected(client, stub_action):
    async with client as ac:
        r = await ac.post("/api/bot/v1/breaker-reset", headers=_basic("x", PW))
    assert r.status_code == 403
    assert stub_action == []


@pytest.mark.asyncio
async def test_cross_site_action_is_rejected_even_with_header(client, stub_action):
    async with client as ac:
        r = await ac.post("/api/bot/v1/start",
                          headers={**_basic("x", PW), **PANEL_HDR, "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert stub_action == []


@pytest.mark.asyncio
@pytest.mark.parametrize("site", [None, "same-origin"])
async def test_same_origin_action_with_header_proxies(client, stub_action, site):
    hdrs = {**_basic("x", PW), **PANEL_HDR}
    if site:
        hdrs["Sec-Fetch-Site"] = site
    async with client as ac:
        r = await ac.post("/api/bot/v2/restart", headers=hdrs)
    assert r.status_code == 200
    assert stub_action == [("v2", "POST", "/api/bot/restart")]


def test_page_sends_panel_header_on_actions():
    assert '"X-Efloud-Panel"' in panel_main.PAGE


@pytest.mark.asyncio
async def test_repeated_wrong_passwords_get_429(client):
    xff = {"X-Forwarded-For": "203.0.113.50"}
    async with client as ac:
        codes = [(await ac.get("/api/overview", headers={**_basic("x", "wrong"), **xff})).status_code
                 for _ in range(12)]
        # correct password from the locked client is also refused during lockout
        locked = await ac.get("/api/overview", headers={**_basic("x", PW), **xff})
    assert codes[:10] == [401] * 10
    assert codes[10:] == [429, 429]
    assert locked.status_code == 429


@pytest.mark.asyncio
async def test_lockout_is_per_client_and_missing_header_is_not_counted(client, stub_overview):
    async with client as ac:
        for _ in range(15):  # browser's first unauthenticated request → normal 401 challenge
            assert (await ac.get("/api/overview", headers={"X-Forwarded-For": "198.51.100.1"})).status_code == 401
        for _ in range(10):
            await ac.get("/api/overview", headers={**_basic("x", "wrong"), "X-Forwarded-For": "203.0.113.60"})
        ok_first = await ac.get("/api/overview", headers={**_basic("x", PW), "X-Forwarded-For": "198.51.100.1"})
        ok_other = await ac.get("/api/overview", headers={**_basic("x", PW), "X-Forwarded-For": "192.0.2.7"})
    assert ok_first.status_code == 200 and ok_other.status_code == 200


@pytest.mark.asyncio
async def test_spoofed_leftmost_forwarded_for_does_not_evade_lockout(client):
    async with client as ac:
        for i in range(10):
            await ac.get("/api/overview",
                         headers={**_basic("x", "wrong"), "X-Forwarded-For": f"10.0.0.{i}, 203.0.113.70"})
        r = await ac.get("/api/overview",
                         headers={**_basic("x", "wrong"), "X-Forwarded-For": "10.9.9.9, 203.0.113.70"})
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_global_failure_cap_locks_all_clients(client):
    async with client as ac:
        for n in range(5):
            for _ in range(10):
                await ac.get("/api/overview", headers={**_basic("x", "wrong"), "X-Forwarded-For": f"203.0.113.{100 + n}"})
        r = await ac.get("/api/overview", headers={**_basic("x", PW), "X-Forwarded-For": "192.0.2.200"})
    assert r.status_code == 429
    assert r.headers.get("retry-after") == str(panel_main.AUTH_FAIL_WINDOW_SEC)


@pytest.mark.asyncio
async def test_lockout_expires_after_window(client, stub_overview, monkeypatch):
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(panel_main.time, "time", lambda: clock["t"])
    xff = {"X-Forwarded-For": "203.0.113.80"}
    async with client as ac:
        for _ in range(10):
            await ac.get("/api/overview", headers={**_basic("x", "wrong"), **xff})
        assert (await ac.get("/api/overview", headers={**_basic("x", PW), **xff})).status_code == 429
        clock["t"] += panel_main.AUTH_FAIL_WINDOW_SEC + 1
        assert (await ac.get("/api/overview", headers={**_basic("x", PW), **xff})).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("site,expected", [("same-site", 403), ("none", 200)])
async def test_sec_fetch_site_values(client, stub_action, site, expected):
    async with client as ac:
        r = await ac.post("/api/bot/v1/stop", headers={**_basic("x", PW), **PANEL_HDR, "Sec-Fetch-Site": site})
    assert r.status_code == expected
