"""Synthetic tests for the read-only journal analyzer; no production data."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys

from scripts.analyze_trade_journal import analyze

NOW = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "analyze_trade_journal.py"


def row(trade_id, exit_time, reason="SL", **overrides):
    result = {"trade_id": trade_id, "exit_timestamp": exit_time,
              "entry_timestamp": "2026-10-25T10:00:00Z", "exit_reason": reason,
              "entry_price": 100, "sl_initial": 98, "realized_pnl": -1,
              "pnl_source": "estimated"}
    result.update(overrides)
    return result


def report(*rows):
    return analyze([json.dumps(value) + "\n" for value in rows], NOW)


def test_utc_boundaries_mixed_offsets_and_pnl():
    r = report(
        row("start", "2026-10-25T15:00:00+03:00", realized_pnl=1.5),
        row("later", "2026-10-26T12:00:00", realized_pnl=-0.3, entry_price=200, sl_initial=210),
        row("end", "2026-11-01T12:00:00Z", reason="TP2", realized_pnl=2),
        row("old", "2026-10-25T11:59:59Z", realized_pnl=100),
        row("future", "2026-11-01T12:00:01Z", realized_pnl=100))
    assert r["closed_rows_included"] == 3
    assert Decimal(r["pnl_usdt"]["sum_of_available"]) == Decimal("3.2")
    assert Decimal(r["sl_distance_pct"]["mean"]) == 3
    assert r["stop_streak"]["max_confirmed_in_observed_window"] == 2
    assert r["quality"]["future_exit_timestamp"] == 1
    assert r["window_utc"]["from_inclusive"] == "2026-10-25T12:00:00+00:00"


def test_reason_not_inferred_from_pnl_and_poll_stop_counts():
    r = report(row("a", "2026-10-27T00:00:00Z", "SL", realized_pnl=5),
               row("b", "2026-10-28T00:00:00Z", "SL_POLL", realized_pnl=0),
               row("c", "2026-10-29T00:00:00Z", "RECONCILED", realized_pnl=-20),
               row("d", "2026-10-30T00:00:00Z", "SL", realized_pnl=-1),
               row("e", "2026-10-31T00:00:00Z", None, realized_pnl=-10))
    assert r["exit_reason_categories"] == {"stop": 3, "known_non_stop": 0, "reconciled_unknown": 1, "other_or_missing_unknown": 1}
    assert r["stop_streak"] == {"max_confirmed_in_observed_window": 2, "ending_confirmed_in_observed_window": 0}


def test_missing_and_bad_data_never_counted_as_zero():
    lines = [
        json.dumps(row("a", "2026-10-30T00:00:00Z", realized_pnl=None, entry_price=0, entry_timestamp="bad")),
        json.dumps(row("b", "2026-10-30T01:00:00Z", realized_pnl=True, sl_initial=0, entry_timestamp="2026-10-31T00:00:00Z")),
        json.dumps(row("c", "not-a-date")),
        json.dumps({"trade_id": "open", "exit_timestamp": None, "exit_reason": None, "exit_price": None}),
        json.dumps({"trade_id": "undated", "exit_timestamp": None, "exit_reason": "SL"}),
        '{broken', '[]', '{"v": NaN}', '\ufffd', '',
    ]
    r = analyze(lines, NOW)
    assert r["closed_rows_included"] == 2
    assert r["pnl_usdt"]["sum_of_available"] is None
    assert r["sl_distance_pct"]["mean"] is None
    assert r["holding_hours"]["mean"] is None
    assert r["quality"]["window_missing_or_invalid_pnl"] == 2
    assert r["quality"]["window_missing_or_invalid_sl_distance"] == 2
    assert r["quality"]["window_missing_or_invalid_duration"] == 2
    assert r["quality"]["invalid_exit_timestamp"] == 1
    assert r["quality"]["malformed_lines"] == 4
    assert r["quality"]["open_or_undated"] == 1
    assert r["quality"]["undated_apparently_closed"] == 1
    assert r["quality"]["empty_lines"] == 1


def test_duplicates_are_excluded_not_deduped_arbitrarily():
    r = report(row("dup", "2026-10-28T00:00:00Z"),
               row("dup", "2026-10-29T00:00:00Z"),
               row("only", "2026-10-30T00:00:00Z", "TP1"))
    assert r["closed_rows_included"] == 1
    assert r["quality"]["duplicate_ids"] == 1
    assert r["quality"]["duplicate_rows_in_window_excluded"] == 2
    assert r["pnl_usdt"]["sum_of_available"] == "-1"


def test_simultaneous_mixed_reasons_do_not_invent_sequence():
    r = report(row("one", "2026-10-27T00:00:00Z"),
               row("two", "2026-10-28T00:00:00Z"),
               row("three", "2026-10-28T00:00:00Z", "TP2"),
               row("four", "2026-10-29T00:00:00Z"))
    assert r["stop_streak"]["max_confirmed_in_observed_window"] == 1
    assert r["stop_streak"]["ending_confirmed_in_observed_window"] == 1
    assert r["quality"]["mixed_timestamp_groups"] == 1


def test_cli_stdin_emits_only_aggregate_and_rejects_naive_now(tmp_path):
    record = row("SECRET_FAKE_ID", "2026-10-30T00:00:00Z", entry_timestamp="2026-10-29T22:30:00Z")
    result = subprocess.run([sys.executable, str(SCRIPT), "--journal", "-", "--now", "2026-11-01T12:00:00Z"],
                            input=json.dumps(record), text=True, capture_output=True, check=True)
    assert "SECRET_FAKE_ID" not in result.stdout
    assert Decimal(json.loads(result.stdout)["holding_hours"]["mean"]) == Decimal("1.5")
    bad = subprocess.run([sys.executable, str(SCRIPT), "--now", "2026-11-01T12:00:00"], text=True, capture_output=True)
    assert bad.returncode != 0
    missing = subprocess.run([sys.executable, str(SCRIPT), "--journal", str(tmp_path / "missing")], text=True, capture_output=True)
    assert missing.returncode != 0 and not missing.stdout


def test_file_invalid_utf8_isolated_per_line(tmp_path):
    path = tmp_path / "journal.jsonl"
    path.write_bytes(b'{"x":"\xff"}\n' + json.dumps(row("ok", "2026-10-30T00:00:00Z")).encode() + b'\n')
    result = subprocess.run([sys.executable, str(SCRIPT), "--journal", str(path), "--now", "2026-11-01T12:00:00Z"],
                            text=True, capture_output=True, check=True)
    parsed = json.loads(result.stdout)
    assert parsed["quality"]["malformed_lines"] == 1
    assert parsed["closed_rows_included"] == 1
