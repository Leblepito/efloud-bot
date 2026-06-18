#!/usr/bin/env python3
"""T-021 (P-003 W-R): UptimeRobot monitors + status page, as-code.

Declarative monitor config lives in ``ops/uptimerobot/monitors.yaml``; this
script applies it idempotently against the UptimeRobot v2 API:

  * monitors are matched by ``friendly_name`` — existing ones are EDITED in
    place, missing ones are CREATED. Re-running is a no-op-shaped convergence,
    never a duplicate.
  * the API key is read from ``$UPTIMEROBOT_API_KEY`` (never committed).
  * ``--dry-run`` prints the intended plan and makes ZERO network calls, so it
    works (and is tested) without a key.

Why a *keyword* monitor and not a plain HTTP monitor: ``/api/healthz`` returns
HTTP 200 for both ``"status":"ok"`` (trading) and ``"status":"suspended"``
(breaker halted). The keyword monitor goes DOWN when ``"status":"ok"`` is
absent, so a safety suspension is NOT reported as "operational".
See docs/runbooks/healthz-contract.md and docs/runbooks/uptimerobot-as-code.md.

Usage:
    UPTIMEROBOT_API_KEY=u123... python scripts/setup_uptimerobot.py
    python scripts/setup_uptimerobot.py --dry-run        # no key needed
    python scripts/setup_uptimerobot.py --config path/to/monitors.yaml
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

API_BASE = "https://api.uptimerobot.com/v2"
API_KEY_ENV = "UPTIMEROBOT_API_KEY"
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "ops" / "uptimerobot" / "monitors.yaml"

# UptimeRobot v2 enum encodings (https://uptimerobot.com/api/).
MONITOR_TYPE = {"http": 1, "keyword": 2, "ping": 3, "port": 4, "heartbeat": 5}
# keyword_type: 1 = "exists" (DOWN when keyword found), 2 = "not exists"
# (DOWN when keyword missing). We want DOWN when '"status":"ok"' is missing.
KEYWORD_TYPE = {"present": 1, "absent": 2}
# keyword_case_type: 0 = case sensitive, 1 = case insensitive.
KEYWORD_CASE = {True: 0, False: 1}

# HTTP transport: (url, form_data) -> parsed JSON dict. Injectable for tests.
PostFn = Callable[[str, dict[str, Any]], dict[str, Any]]


class UptimeRobotError(RuntimeError):
    """Raised when the UptimeRobot API returns stat != "ok"."""


# ── Config ──────────────────────────────────────────────────────────────────
def load_config(path: Path) -> dict[str, Any]:
    """Load monitors.yaml, returning a dict with defaults applied per monitor."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults") or {}
    monitors = []
    for mon in raw.get("monitors") or []:
        merged = {**defaults, **mon}
        monitors.append(merged)
    return {
        "monitors": monitors,
        "status_pages": raw.get("status_pages") or [],
        "defaults": defaults,
    }


def build_monitor_payload(mon: dict[str, Any]) -> dict[str, Any]:
    """Translate one config monitor into UptimeRobot newMonitor/editMonitor form fields."""
    mtype = str(mon.get("type", "http")).lower()
    if mtype not in MONITOR_TYPE:
        raise ValueError(f"unknown monitor type {mtype!r} (allowed: {sorted(MONITOR_TYPE)})")

    payload: dict[str, Any] = {
        "friendly_name": mon["friendly_name"],
        "url": mon["url"],
        "type": MONITOR_TYPE[mtype],
        "interval": int(mon.get("interval_seconds", 300)),
    }

    if mtype == "keyword":
        if not mon.get("keyword"):
            raise ValueError(f"keyword monitor {mon['friendly_name']!r} needs a 'keyword'")
        alert_when = str(mon.get("keyword_alert_when", "absent")).lower()
        if alert_when not in KEYWORD_TYPE:
            raise ValueError(
                f"keyword_alert_when must be one of {sorted(KEYWORD_TYPE)}, got {alert_when!r}"
            )
        payload["keyword_type"] = KEYWORD_TYPE[alert_when]
        payload["keyword_value"] = mon["keyword"]
        payload["keyword_case_type"] = KEYWORD_CASE[bool(mon.get("keyword_case_sensitive", False))]

    contacts = mon.get("alert_contact_ids") or []
    if contacts:
        # UptimeRobot format: "id_threshold_recurrence-..." dash-joined.
        # Bare IDs default to threshold 0 / recurrence 0 (alert immediately, once).
        payload["alert_contacts"] = "-".join(f"{cid}_0_0" for cid in contacts)

    return payload


# ── API client ────────────────────────────────────────────────────────────--
def _httpx_post(url: str, data: dict[str, Any]) -> dict[str, Any]:
    """Default transport — POST form-encoded, parse JSON. Imported lazily so
    --dry-run and the test suite never need httpx installed at import time."""
    import httpx

    resp = httpx.post(
        url,
        data={**data, "format": "json"},
        headers={"cache-control": "no-cache", "content-type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


class UptimeRobotClient:
    """Thin wrapper over the UptimeRobot v2 form API. ``post_fn`` is injectable
    so tests can run with zero network access."""

    def __init__(self, api_key: str, *, post_fn: Optional[PostFn] = None) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._post = post_fn or _httpx_post

    def _call(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = {"api_key": self._api_key, **payload}
        resp = self._post(f"{API_BASE}/{action}", data)
        if resp.get("stat") != "ok":
            err = resp.get("error", resp)
            raise UptimeRobotError(f"{action} failed: {err}")
        return resp

    def get_monitors(self) -> list[dict[str, Any]]:
        return self._call("getMonitors", {}).get("monitors", [])

    def new_monitor(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("newMonitor", payload)

    def edit_monitor(self, monitor_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("editMonitor", {"id": monitor_id, **payload})

    def get_psps(self) -> list[dict[str, Any]]:
        return self._call("getPSPs", {}).get("psps", [])

    def new_psp(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("newPSP", payload)

    def edit_psp(self, psp_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("editPSP", {"id": psp_id, **payload})


# ── Reconciliation ──────────────────────────────────────────────────────────
def plan_monitors(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure: intended monitor payloads + human descriptions. No API, no key —
    drives both --dry-run output and the create-or-update apply step."""
    plan = []
    for mon in config["monitors"]:
        payload = build_monitor_payload(mon)
        plan.append({"friendly_name": mon["friendly_name"], "payload": payload})
    return plan


def apply_monitors(
    client: UptimeRobotClient, config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Idempotent create-or-update. Returns one action record per monitor."""
    existing = {m.get("friendly_name"): m for m in client.get_monitors()}
    actions = []
    for item in plan_monitors(config):
        name = item["friendly_name"]
        payload = item["payload"]
        if name in existing:
            monitor_id = existing[name]["id"]
            client.edit_monitor(monitor_id, payload)
            actions.append({"action": "updated", "friendly_name": name, "id": monitor_id})
        else:
            resp = client.new_monitor(payload)
            new_id = (resp.get("monitor") or {}).get("id")
            actions.append({"action": "created", "friendly_name": name, "id": new_id})
    return actions


def _resolve_monitor_ids(names: list[str], existing: dict[str, dict]) -> str:
    ids = []
    for name in names:
        if name not in existing:
            raise UptimeRobotError(
                f"status page references unknown monitor {name!r}; create it first"
            )
        ids.append(str(existing[name]["id"]))
    return "-".join(ids)


def apply_status_pages(
    client: UptimeRobotClient, config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Idempotent create-or-update for public status pages (PSPs)."""
    status_pages = config.get("status_pages") or []
    if not status_pages:
        return []
    monitors_by_name = {m.get("friendly_name"): m for m in client.get_monitors()}
    existing = {p.get("friendly_name"): p for p in client.get_psps()}
    actions = []
    for page in status_pages:
        name = page["friendly_name"]
        payload: dict[str, Any] = {
            "type": 1,  # 1 = homepage / aggregated status page
            "friendly_name": name,
            "monitors": _resolve_monitor_ids(page.get("monitors") or [], monitors_by_name),
        }
        if page.get("custom_domain"):
            payload["custom_domain"] = page["custom_domain"]
        if name in existing:
            psp_id = existing[name]["id"]
            client.edit_psp(psp_id, payload)
            actions.append({"action": "updated", "friendly_name": name, "id": psp_id})
        else:
            resp = client.new_psp(payload)
            new_id = (resp.get("psp") or {}).get("id")
            actions.append({"action": "created", "friendly_name": name, "id": new_id})
    return actions


# ── CLI ───────────────────────────────────────────────────────────────────--
def _print_dry_run(config: dict[str, Any]) -> None:
    print("DRY RUN -- no API calls. Intended plan:\n")
    for item in plan_monitors(config):
        p = item["payload"]
        bits = [f"type={p['type']}", f"interval={p['interval']}s", f"url={p['url']}"]
        if "keyword_value" in p:
            bits.append(f"keyword={p['keyword_value']!r}")
            bits.append(f"keyword_type={p['keyword_type']}")
        if "alert_contacts" in p:
            bits.append(f"alert_contacts={p['alert_contacts']}")
        else:
            bits.append("alert_contacts=NONE (no routing -- fill alert_contact_ids)")
        print(f"  monitor  {item['friendly_name']!r}: " + ", ".join(bits))
    for page in config.get("status_pages") or []:
        mons = ", ".join(page.get("monitors") or [])
        dom = page.get("custom_domain") or "(hosted *.statuspage.com)"
        print(f"  status   {page['friendly_name']!r}: monitors=[{mons}] domain={dom}")
    print("\nRe-run without --dry-run (and with $UPTIMEROBOT_API_KEY set) to apply.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Apply UptimeRobot monitors as-code (T-021).")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="monitors.yaml path")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan, make no API calls (no key needed)"
    )
    parser.add_argument(
        "--skip-status-pages", action="store_true", help="apply monitors only, skip status pages"
    )
    args = parser.parse_args(argv)

    if not args.config.exists():
        print(f"ERROR: config not found: {args.config}", file=sys.stderr)
        return 2

    config = load_config(args.config)
    if not config["monitors"]:
        print(f"ERROR: no monitors defined in {args.config}", file=sys.stderr)
        return 2

    # Validate payloads early (raises ValueError on bad config) — even in dry-run.
    plan_monitors(config)

    if args.dry_run:
        _print_dry_run(config)
        return 0

    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(
            f"ERROR: {API_KEY_ENV} is not set. Export it or use --dry-run.\n"
            f"  Get a key: UptimeRobot dashboard -> My Settings -> API -> Main API Key.\n"
            f"  See docs/runbooks/uptimerobot-as-code.md",
            file=sys.stderr,
        )
        return 2

    client = UptimeRobotClient(api_key)
    for rec in apply_monitors(client, config):
        print(f"  monitor  {rec['action']:>7}: {rec['friendly_name']!r} (id={rec['id']})")
    if not args.skip_status_pages:
        for rec in apply_status_pages(client, config):
            print(f"  status   {rec['action']:>7}: {rec['friendly_name']!r} (id={rec['id']})")
    print("Done. Verify in the UptimeRobot dashboard (allow one interval for first check).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
