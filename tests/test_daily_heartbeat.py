"""Heartbeat staleness check — reads state/alerter_heartbeat.json."""
from __future__ import annotations

import json
import time
from pathlib import Path

from ops.daily_report.heartbeat import (
    HEARTBEAT_STALE_AFTER_SEC,
    check_alerter_heartbeat,
)


def test_fresh_heartbeat_not_stale(tmp_path: Path):
    hb_path = tmp_path / "alerter_heartbeat.json"
    hb_path.write_text(json.dumps({"alerter_heartbeat_ts": int(time.time())}))
    stale, age = check_alerter_heartbeat(str(hb_path))
    assert stale is False
    assert age is not None
    assert age < 5


def test_old_heartbeat_is_stale(tmp_path: Path):
    """Heartbeat written 3 hours ago > 2h threshold → stale."""
    hb_path = tmp_path / "alerter_heartbeat.json"
    three_hours_ago = int(time.time()) - 3 * 60 * 60
    hb_path.write_text(json.dumps({"alerter_heartbeat_ts": three_hours_ago}))
    stale, age = check_alerter_heartbeat(str(hb_path))
    assert stale is True
    assert age is not None
    assert age >= HEARTBEAT_STALE_AFTER_SEC


def test_missing_file_is_stale(tmp_path: Path):
    """No heartbeat file → alerter never wrote one → treat as stale."""
    hb_path = tmp_path / "does_not_exist.json"
    stale, age = check_alerter_heartbeat(str(hb_path))
    assert stale is True
    assert age is None
