"""Post-deploy canary (T-20261107-20): read-only checks, verdict = exit code."""
from __future__ import annotations

import importlib.util
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def canary():
    spec = importlib.util.spec_from_file_location("canary", ROOT / "scripts" / "canary.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["canary"] = mod
    spec.loader.exec_module(mod)
    return mod


class _Resp:
    def __init__(self, status, headers=None, body=b""):
        self.status, self.headers, self.body = status, headers or {}, body


def _fake_fetch(table):
    def fetch(url, timeout):
        return table[url]
    return fetch


def _healthy_table(c):
    page = b'<meta property="og:image" content="https://u2algo.com/brand/og-card.png" />'
    return {
        "https://u2algo.com/": _Resp(200, {"content-type": "text/html"}, page),
        "https://www.u2algo.com/": _Resp(301, {"location": "https://u2algo.com/"}),
        "https://u2algo.com/healthz": _Resp(200, {"content-type": "application/json"}, b'{"ok": true}'),
        "https://u2algo.com/brand/og-card.png": _Resp(200, {"content-type": "image/png"}, b"\x89PNG"),
        c.BOT_HEALTHZ: _Resp(200, {"content-type": "application/json"}, b'{"status":"ok","failures":[]}'),
    }


def _no_dns(host):
    raise socket.gaierror("not found")


def test_all_green_exits_zero(canary):
    results = canary.run_checks(fetch=_fake_fetch(_healthy_table(canary)), resolve=_no_dns)
    assert all(r.ok for r in results), [r for r in results if not r.ok]
    assert canary.exit_code(results) == 0


def test_www_not_redirecting_fails(canary):
    t = _healthy_table(canary)
    t["https://www.u2algo.com/"] = _Resp(200, {"content-type": "text/html"})
    results = canary.run_checks(fetch=_fake_fetch(t), resolve=_no_dns)
    assert canary.exit_code(results) == 1
    assert [r.name for r in results if not r.ok] == ["site: www -> apex 301"]


def test_bot_healthz_not_ok_fails(canary):
    t = _healthy_table(canary)
    t[canary.BOT_HEALTHZ] = _Resp(200, {}, b'{"status":"suspended","failures":["breaker_halted"]}')
    results = canary.run_checks(fetch=_fake_fetch(t), resolve=_no_dns)
    bad = [r for r in results if not r.ok]
    assert [r.name for r in bad] == ["bot: healthz status ok"]
    assert "breaker_halted" in bad[0].detail


def test_deleted_subdomain_resolving_again_fails(canary):
    def resolve(host):
        if host == "bot.u2algo.com":
            return "1.2.3.4"
        raise socket.gaierror("nx")
    results = canary.run_checks(fetch=_fake_fetch(_healthy_table(canary)), resolve=resolve)
    assert [r.name for r in results if not r.ok] == ["dns: bot.u2algo.com stays deleted"]


def test_network_error_is_a_failure_not_a_crash(canary):
    def fetch(url, timeout):
        raise OSError("connection refused")
    results = canary.run_checks(fetch=fetch, resolve=_no_dns)
    assert canary.exit_code(results) == 1
    assert all("connection refused" in r.detail for r in results if r.name.startswith(("site", "bot")))
