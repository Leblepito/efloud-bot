#!/usr/bin/env python3
"""Post-deploy canary for efloud-bot / u2algo — read-only, verdict = exit code.

Checks the public surface after any merge or deploy:
  * u2algo-site (Railway): apex 200 with the PNG share card, www → apex 301,
    /healthz, og-card.png served as image/png;
  * live bot dashboard (VPS, Caddy): /healthz answers status "ok" with no failures;
  * the deleted bot subdomains (bot./v2./scalp.u2algo.com) stay deleted — a
    record reappearing would re-open the subdomain-takeover risk.

Usage:  python scripts/canary.py            # exit 0 = all green, 1 = any red
It never writes anything and needs no credentials.
"""
from __future__ import annotations

import json
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

SITE = "https://u2algo.com"
BOT_HEALTHZ = "https://2-28-139-82.nip.io/healthz"
DELETED_HOSTS = ("bot.u2algo.com", "v2.u2algo.com", "scalp.u2algo.com")
TIMEOUT = 15


@dataclass(frozen=True)
class Resp:
    status: int
    headers: dict
    body: bytes


@dataclass(frozen=True)
class Result:
    name: str
    ok: bool
    detail: str = ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # report 3xx instead of following
        return None


def http_fetch(url: str, timeout: float) -> Resp:
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "efloud-canary/1"})
    try:
        with opener.open(req, timeout=timeout) as r:
            return Resp(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(200_000))
    except urllib.error.HTTPError as e:  # 3xx/4xx/5xx still carry status + headers
        return Resp(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, b"")


def dns_resolve(host: str) -> str:
    return socket.gethostbyname(host)


def _http_check(fetch, name: str, url: str, test: Callable[[Resp], tuple[bool, str]]) -> Result:
    try:
        r = fetch(url, TIMEOUT)
    except Exception as e:  # network errors are red results, never a crash
        return Result(name, False, f"{type(e).__name__}: {e}")
    try:
        ok, detail = test(r)
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e}"
    return Result(name, ok, detail)


def _bot_status(r: Resp) -> tuple[bool, str]:
    data = json.loads(r.body or b"{}")
    ok = r.status == 200 and data.get("status") == "ok" and not data.get("failures")
    return ok, f"{r.status} status={data.get('status')} failures={data.get('failures')}"


def run_checks(fetch=http_fetch, resolve=dns_resolve) -> list[Result]:
    h = lambda r, k: r.headers.get(k, "")  # noqa: E731
    results = [
        _http_check(fetch, "site: apex 200 + PNG og:image", f"{SITE}/", lambda r: (
            r.status == 200 and b"/brand/og-card.png" in r.body, f"{r.status}")),
        _http_check(fetch, "site: www -> apex 301", "https://www.u2algo.com/", lambda r: (
            r.status == 301 and h(r, "location") == f"{SITE}/", f"{r.status} {h(r, 'location')}")),
        _http_check(fetch, "site: healthz", f"{SITE}/healthz", lambda r: (
            r.status == 200, f"{r.status}")),
        _http_check(fetch, "site: og-card.png", f"{SITE}/brand/og-card.png", lambda r: (
            r.status == 200 and h(r, "content-type").startswith("image/png"),
            f"{r.status} {h(r, 'content-type')}")),
        _http_check(fetch, "bot: healthz status ok", BOT_HEALTHZ, _bot_status),
    ]
    for host in DELETED_HOSTS:
        try:
            addr = resolve(host)
            results.append(Result(f"dns: {host} stays deleted", False, f"resolves to {addr}"))
        except OSError:
            results.append(Result(f"dns: {host} stays deleted", True))
    return results


def exit_code(results: list[Result]) -> int:
    return 0 if all(r.ok for r in results) else 1


def main() -> int:
    results = run_checks()
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.name}" + (f"  -> {r.detail}" if r.detail and not r.ok else ""))
    code = exit_code(results)
    print("ALL GREEN" if code == 0 else f"{sum(not r.ok for r in results)} RED")
    return code


if __name__ == "__main__":
    sys.exit(main())
