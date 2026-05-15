"""OverseerHeartbeatStaleRule — alerter-side watchdog over the overseer.

Mirrors the existing healthz-driven rule pattern (match_health(payload, history))
so the alerter's main loop already invokes it on every healthz tick without any
new dispatch wiring. The rule itself ignores `payload` — its trigger is the
mtime/contents of EFLOUD_OVERSEER_HEARTBEAT_FILE.

Schemas accepted (back-compat):
    {"ts": <epoch_sec>}                       ← overseer writes this today
    {"alerter_heartbeat_ts": <epoch_sec>}     ← alerter writes this; same shape

Threshold: 10 minutes (CRITICAL severity). Dedup key buckets ts_diff_min by
10-min windows so a long stale period doesn't spam alerts.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest import mock


def test_rule_fires_when_heartbeat_file_missing(tmp_path: Path):
    """No file at the configured path → CRITICAL alert (overseer never started
    or its disk volume is unmounted)."""
    from ops.alerter.rules import OverseerHeartbeatStaleRule

    missing = tmp_path / "does_not_exist.json"
    with mock.patch.dict(
        "os.environ",
        {"EFLOUD_OVERSEER_HEARTBEAT_FILE": str(missing)},
        clear=False,
    ):
        rule = OverseerHeartbeatStaleRule()
        out = rule.match_health(payload={}, history={})
    assert out is not None
    assert "stale" in out.lower() or "overseer" in out.lower()
    assert rule.severity == "CRITICAL"


def test_rule_silent_when_fresh(tmp_path: Path):
    """ts within the last 10 min → no alert."""
    from ops.alerter.rules import OverseerHeartbeatStaleRule

    heartbeat = tmp_path / "overseer_heartbeat.json"
    heartbeat.write_text(json.dumps({"ts": int(time.time())}), encoding="utf-8")

    with mock.patch.dict(
        "os.environ",
        {"EFLOUD_OVERSEER_HEARTBEAT_FILE": str(heartbeat)},
        clear=False,
    ):
        rule = OverseerHeartbeatStaleRule()
        out = rule.match_health(payload={}, history={})
    assert out is None


def test_rule_fires_when_stale_more_than_10min(tmp_path: Path):
    """ts older than 10 min → CRITICAL alert."""
    from ops.alerter.rules import OverseerHeartbeatStaleRule

    heartbeat = tmp_path / "overseer_heartbeat.json"
    stale_ts = int(time.time()) - 15 * 60  # 15 min ago
    heartbeat.write_text(json.dumps({"ts": stale_ts}), encoding="utf-8")

    with mock.patch.dict(
        "os.environ",
        {"EFLOUD_OVERSEER_HEARTBEAT_FILE": str(heartbeat)},
        clear=False,
    ):
        rule = OverseerHeartbeatStaleRule()
        out = rule.match_health(payload={}, history={})
    assert out is not None
    assert "stale" in out.lower() or "overseer" in out.lower()


def test_rule_accepts_both_schema_keys(tmp_path: Path):
    """Both {"ts": ...} (overseer.state.write_heartbeat_file) and
    {"alerter_heartbeat_ts": ...} (legacy alerter) must satisfy the freshness check."""
    from ops.alerter.rules import OverseerHeartbeatStaleRule

    now = int(time.time())
    hb_ts = tmp_path / "ts_schema.json"
    hb_ts.write_text(json.dumps({"ts": now}), encoding="utf-8")
    hb_legacy = tmp_path / "legacy_schema.json"
    hb_legacy.write_text(
        json.dumps({"alerter_heartbeat_ts": now}), encoding="utf-8"
    )

    rule = OverseerHeartbeatStaleRule()
    with mock.patch.dict(
        "os.environ", {"EFLOUD_OVERSEER_HEARTBEAT_FILE": str(hb_ts)}, clear=False
    ):
        assert rule.match_health({}, {}) is None
    with mock.patch.dict(
        "os.environ", {"EFLOUD_OVERSEER_HEARTBEAT_FILE": str(hb_legacy)}, clear=False
    ):
        assert rule.match_health({}, {}) is None


def test_rule_dedup_key_buckets_by_10min(tmp_path: Path):
    """Dedup key should be stable for stale ts inside the same 10-min bucket.

    We don't have the dedup_key on the return type (it's a free-form text
    return per alerter pattern), so we assert the rule's dedup_window_sec is
    set high enough to silence repeat fires inside a 10-min window.
    """
    from ops.alerter.rules import OverseerHeartbeatStaleRule

    rule = OverseerHeartbeatStaleRule()
    # Window must be at least 10 min — fire-once-per-bucket semantics.
    assert rule.dedup_window_sec >= 10 * 60
    assert rule.alert_key == "overseer.heartbeat_stale"


def test_rule_silent_when_env_unset(tmp_path: Path, monkeypatch):
    """If EFLOUD_OVERSEER_HEARTBEAT_FILE is not set, rule must be a no-op
    (cannot fail loudly on rollouts where overseer isn't deployed yet)."""
    from ops.alerter.rules import OverseerHeartbeatStaleRule

    monkeypatch.delenv("EFLOUD_OVERSEER_HEARTBEAT_FILE", raising=False)
    rule = OverseerHeartbeatStaleRule()
    assert rule.match_health({}, {}) is None
