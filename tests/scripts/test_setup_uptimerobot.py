"""Tests for scripts/setup_uptimerobot.py (T-021 UptimeRobot as-code).

Every test runs with ZERO network access: the UptimeRobot HTTP transport is
injected as a fake ``post_fn``, and the env key is never read in --dry-run.
"""
from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "setup_uptimerobot.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("setup_uptimerobot", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ur = _load_module()


# ── Fake transport ────────────────────────────────────────────────────────--
class FakeAPI:
    """Records (action, data) calls and replays canned responses per action."""

    def __init__(self, responses: dict[str, object]):
        self._responses = responses
        self.calls: list[tuple[str, dict]] = []

    def post(self, url: str, data: dict) -> dict:
        action = url.rsplit("/", 1)[-1]
        self.calls.append((action, data))
        resp = self._responses.get(action)
        if resp is None:
            return {"stat": "ok"}
        if callable(resp):
            return resp(self.calls)
        # allow a list = sequence of responses across repeated calls
        if isinstance(resp, list):
            idx = sum(1 for a, _ in self.calls if a == action) - 1
            return resp[min(idx, len(resp) - 1)]
        return resp

    def actions(self) -> list[str]:
        return [a for a, _ in self.calls]


def _write_config(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "monitors.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


KEYWORD_CONFIG = """
    defaults:
      interval_seconds: 300
      keyword_case_sensitive: false
      alert_contact_ids: []
    monitors:
      - friendly_name: "efloud-bot healthz"
        type: keyword
        url: "https://bot.ualgotrade.com/api/healthz"
        keyword: '"status":"ok"'
        keyword_alert_when: absent
    status_pages:
      - friendly_name: "efloud-bot Status"
        monitors:
          - "efloud-bot healthz"
        custom_domain: ""
"""


# ── load_config ──────────────────────────────────────────────────────────--
def test_load_config_merges_defaults(tmp_path):
    cfg = ur.load_config(_write_config(tmp_path, KEYWORD_CONFIG))
    assert len(cfg["monitors"]) == 1
    mon = cfg["monitors"][0]
    # default merged into the monitor
    assert mon["interval_seconds"] == 300
    assert mon["keyword_case_sensitive"] is False
    assert len(cfg["status_pages"]) == 1


# ── build_monitor_payload ─────────────────────────────────────────────────--
def test_build_keyword_payload_encodes_enums():
    mon = {
        "friendly_name": "efloud-bot healthz",
        "type": "keyword",
        "url": "https://bot.ualgotrade.com/api/healthz",
        "keyword": '"status":"ok"',
        "keyword_alert_when": "absent",
        "keyword_case_sensitive": False,
        "interval_seconds": 300,
    }
    p = ur.build_monitor_payload(mon)
    assert p["type"] == 2  # keyword
    assert p["keyword_type"] == 2  # "absent" => DOWN when keyword missing
    assert p["keyword_case_type"] == 1  # case-insensitive
    assert p["keyword_value"] == '"status":"ok"'
    assert p["interval"] == 300
    assert "alert_contacts" not in p  # none configured


def test_build_payload_case_sensitive_flips_enum():
    mon = {
        "friendly_name": "x", "type": "keyword", "url": "https://x",
        "keyword": "ok", "keyword_case_sensitive": True,
    }
    assert ur.build_monitor_payload(mon)["keyword_case_type"] == 0


def test_build_payload_alert_contacts_formatting():
    mon = {
        "friendly_name": "x", "type": "keyword", "url": "https://x",
        "keyword": "ok", "alert_contact_ids": [123, 456],
    }
    assert ur.build_monitor_payload(mon)["alert_contacts"] == "123_0_0-456_0_0"


def test_build_payload_rejects_unknown_type():
    with pytest.raises(ValueError, match="unknown monitor type"):
        ur.build_monitor_payload({"friendly_name": "x", "type": "bogus", "url": "https://x"})


def test_build_payload_keyword_requires_keyword():
    with pytest.raises(ValueError, match="needs a 'keyword'"):
        ur.build_monitor_payload({"friendly_name": "x", "type": "keyword", "url": "https://x"})


def test_build_payload_rejects_bad_alert_when():
    mon = {"friendly_name": "x", "type": "keyword", "url": "https://x",
           "keyword": "ok", "keyword_alert_when": "sometimes"}
    with pytest.raises(ValueError, match="keyword_alert_when"):
        ur.build_monitor_payload(mon)


# ── apply_monitors (create-or-update) ─────────────────────────────────────--
def test_apply_creates_when_absent(tmp_path):
    cfg = ur.load_config(_write_config(tmp_path, KEYWORD_CONFIG))
    fake = FakeAPI({
        "getMonitors": {"stat": "ok", "monitors": []},
        "newMonitor": {"stat": "ok", "monitor": {"id": 777}},
    })
    client = ur.UptimeRobotClient("KEY", post_fn=fake.post)
    actions = ur.apply_monitors(client, cfg)
    assert actions == [{"action": "created", "friendly_name": "efloud-bot healthz", "id": 777}]
    assert "newMonitor" in fake.actions()
    assert "editMonitor" not in fake.actions()


def test_apply_updates_when_present(tmp_path):
    cfg = ur.load_config(_write_config(tmp_path, KEYWORD_CONFIG))
    fake = FakeAPI({
        "getMonitors": {"stat": "ok", "monitors": [
            {"id": 42, "friendly_name": "efloud-bot healthz"}
        ]},
        "editMonitor": {"stat": "ok", "monitor": {"id": 42}},
    })
    client = ur.UptimeRobotClient("KEY", post_fn=fake.post)
    actions = ur.apply_monitors(client, cfg)
    assert actions == [{"action": "updated", "friendly_name": "efloud-bot healthz", "id": 42}]
    # edit was called with the existing id
    edit_call = next(d for a, d in fake.calls if a == "editMonitor")
    assert edit_call["id"] == 42
    assert "newMonitor" not in fake.actions()


def test_apply_is_idempotent_across_two_runs(tmp_path):
    """Second run sees the monitor created by the first -> edit, no duplicate."""
    cfg = ur.load_config(_write_config(tmp_path, KEYWORD_CONFIG))
    # getMonitors: empty first, then populated
    fake = FakeAPI({
        "getMonitors": [
            {"stat": "ok", "monitors": []},
            {"stat": "ok", "monitors": [{"id": 9, "friendly_name": "efloud-bot healthz"}]},
        ],
        "newMonitor": {"stat": "ok", "monitor": {"id": 9}},
        "editMonitor": {"stat": "ok", "monitor": {"id": 9}},
    })
    client = ur.UptimeRobotClient("KEY", post_fn=fake.post)
    first = ur.apply_monitors(client, cfg)
    second = ur.apply_monitors(client, cfg)
    assert first[0]["action"] == "created"
    assert second[0]["action"] == "updated"
    assert fake.actions().count("newMonitor") == 1  # never duplicated


def test_api_error_raises(tmp_path):
    cfg = ur.load_config(_write_config(tmp_path, KEYWORD_CONFIG))
    fake = FakeAPI({"getMonitors": {"stat": "fail", "error": {"message": "bad key"}}})
    client = ur.UptimeRobotClient("KEY", post_fn=fake.post)
    with pytest.raises(ur.UptimeRobotError, match="getMonitors failed"):
        ur.apply_monitors(client, cfg)


def test_api_key_sent_on_every_call(tmp_path):
    cfg = ur.load_config(_write_config(tmp_path, KEYWORD_CONFIG))
    fake = FakeAPI({
        "getMonitors": {"stat": "ok", "monitors": []},
        "newMonitor": {"stat": "ok", "monitor": {"id": 1}},
    })
    client = ur.UptimeRobotClient("SECRET", post_fn=fake.post)
    ur.apply_monitors(client, cfg)
    assert all(data.get("api_key") == "SECRET" for _, data in fake.calls)


def test_client_requires_api_key():
    with pytest.raises(ValueError, match="api_key is required"):
        ur.UptimeRobotClient("")


# ── status pages ────────────────────────────────────────────────────────--
def test_apply_status_page_creates_with_resolved_ids(tmp_path):
    cfg = ur.load_config(_write_config(tmp_path, KEYWORD_CONFIG))
    fake = FakeAPI({
        "getMonitors": {"stat": "ok", "monitors": [
            {"id": 55, "friendly_name": "efloud-bot healthz"}
        ]},
        "getPSPs": {"stat": "ok", "psps": []},
        "newPSP": {"stat": "ok", "psp": {"id": 900}},
    })
    client = ur.UptimeRobotClient("KEY", post_fn=fake.post)
    actions = ur.apply_status_pages(client, cfg)
    assert actions == [{"action": "created", "friendly_name": "efloud-bot Status", "id": 900}]
    psp_call = next(d for a, d in fake.calls if a == "newPSP")
    assert psp_call["monitors"] == "55"  # friendly_name resolved to monitor id


def test_status_page_unknown_monitor_raises(tmp_path):
    cfg = ur.load_config(_write_config(tmp_path, KEYWORD_CONFIG))
    fake = FakeAPI({
        "getMonitors": {"stat": "ok", "monitors": []},  # name not present
        "getPSPs": {"stat": "ok", "psps": []},
    })
    client = ur.UptimeRobotClient("KEY", post_fn=fake.post)
    with pytest.raises(ur.UptimeRobotError, match="unknown monitor"):
        ur.apply_status_pages(client, cfg)


# ── main / CLI ──────────────────────────────────────────────────────────--
def test_main_dry_run_no_key(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv(ur.API_KEY_ENV, raising=False)
    cfg = _write_config(tmp_path, KEYWORD_CONFIG)
    rc = ur.main(["--dry-run", "--config", str(cfg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY RUN" in out
    assert "efloud-bot healthz" in out
    assert "keyword_type=2" in out


def test_main_missing_key_returns_2(tmp_path, monkeypatch):
    monkeypatch.delenv(ur.API_KEY_ENV, raising=False)
    cfg = _write_config(tmp_path, KEYWORD_CONFIG)
    rc = ur.main(["--config", str(cfg)])
    assert rc == 2


def test_main_config_not_found_returns_2(tmp_path):
    rc = ur.main(["--dry-run", "--config", str(tmp_path / "nope.yaml")])
    assert rc == 2


def test_main_invalid_config_raises(tmp_path):
    bad = _write_config(tmp_path, """
        monitors:
          - friendly_name: "x"
            type: keyword
            url: "https://x"
    """)  # keyword monitor with no keyword
    with pytest.raises(ValueError, match="needs a 'keyword'"):
        ur.main(["--dry-run", "--config", str(bad)])


# ── guard the shipped config ────────────────────────────────────────────--
def test_shipped_config_is_valid():
    """The real ops/uptimerobot/monitors.yaml must load and plan cleanly."""
    cfg = ur.load_config(ur.DEFAULT_CONFIG)
    plan = ur.plan_monitors(cfg)
    assert any(p["friendly_name"] == "efloud-bot healthz" for p in plan)
    healthz = next(p for p in plan if p["friendly_name"] == "efloud-bot healthz")
    # The critical contract: keyword monitor, DOWN when '"status":"ok"' absent.
    assert healthz["payload"]["type"] == 2
    assert healthz["payload"]["keyword_type"] == 2
    assert healthz["payload"]["keyword_value"] == '"status":"ok"'
