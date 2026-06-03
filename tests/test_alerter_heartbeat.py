"""Heartbeat — alerter writes {alerter_heartbeat_ts: int_epoch_sec} to a
JSON file. Daily-report (Step 5) reads this same shape.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest import mock


def test_heartbeat_writes_alerter_heartbeat_ts_to_json_file(tmp_path: Path):
    heartbeat_path = tmp_path / "alerter_heartbeat.json"
    dedup_path = tmp_path / "alerter_dedup.sqlite"

    # H2: Alerter() eagerly builds Dedup(DEDUP_DB), which mkdir's the parent.
    # The default DEDUP_DB is "/app/state/..." (the prod Docker WORKDIR), so on a
    # bare CI runner construction raised PermissionError before the heartbeat ran
    # — patching only HEARTBEAT_FILE was insufficient. Redirect BOTH constants to
    # tmp_path so the test is hermetic (no /app dependency, no repo pollution).
    with mock.patch("ops.alerter.alerter.HEARTBEAT_FILE", str(heartbeat_path)), \
         mock.patch("ops.alerter.alerter.DEDUP_DB", str(dedup_path)):
        from ops.alerter.alerter import Alerter
        a = Alerter()
        a._write_heartbeat()

    # Hermeticity guard: construction stayed inside tmp_path (did not touch /app).
    assert dedup_path.exists(), "Alerter() must build its dedup DB under tmp_path, not /app"
    assert heartbeat_path.exists()
    data = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    assert "alerter_heartbeat_ts" in data
    ts = data["alerter_heartbeat_ts"]
    assert isinstance(ts, int)
    # Within 5 seconds of now
    assert abs(int(time.time()) - ts) < 5
