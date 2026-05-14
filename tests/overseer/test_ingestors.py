"""Overseer ingestors — pure I/O reads (log tail, healthz poll, journal tail).

All three components are side-effect-free *readers*: they never write to the
sources they consume. Tests use tmp_path for files and monkeypatch for HTTP so
nothing escapes the test sandbox.
"""
from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────
# JsonLogTail — file position cursor over a JSON-line log file.
# ─────────────────────────────────────────────────────────────────────


def _write_lines(path: Path, lines: list[str]) -> None:
    """Append newline-terminated lines to path (creates file)."""
    with path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def test_log_tail_reads_new_lines_only(tmp_path):
    """Read-then-write-then-read returns only the newly appended lines —
    cursor must advance, not re-read everything from offset 0."""
    from ops.overseer.ingestors.log_tail import JsonLogTail

    log_path = tmp_path / "bot.log"
    _write_lines(log_path, [
        json.dumps({"event": "a", "ts": 1}),
        json.dumps({"event": "b", "ts": 2}),
        json.dumps({"event": "c", "ts": 3}),
    ])

    tail = JsonLogTail(str(log_path))
    first = tail.read_new()
    assert len(first) == 3

    _write_lines(log_path, [
        json.dumps({"event": "d", "ts": 4}),
        json.dumps({"event": "e", "ts": 5}),
    ])

    second = tail.read_new()
    assert len(second) == 2
    assert [r["event"] for r in second] == ["d", "e"]


def test_log_tail_handles_invalid_json(tmp_path):
    """Invalid JSON lines are silently skipped (alerter pattern) — partial
    log corruption shouldn't poison the whole batch."""
    from ops.overseer.ingestors.log_tail import JsonLogTail

    log_path = tmp_path / "bot.log"
    _write_lines(log_path, [
        json.dumps({"event": "good1"}),
        "this is not json {{{",
        json.dumps({"event": "good2"}),
    ])

    tail = JsonLogTail(str(log_path))
    results = tail.read_new()
    assert len(results) == 2
    assert [r["event"] for r in results] == ["good1", "good2"]


def test_log_tail_handles_rotation(tmp_path):
    """When file size shrinks (truncate/rotate), cursor resets to 0 and we
    pick up the new lines from the start of the rotated file."""
    from ops.overseer.ingestors.log_tail import JsonLogTail

    log_path = tmp_path / "bot.log"
    _write_lines(log_path, [
        json.dumps({"event": "old1"}),
        json.dumps({"event": "old2"}),
        json.dumps({"event": "old3"}),
    ])

    tail = JsonLogTail(str(log_path))
    tail.read_new()  # advance past old lines

    # Truncate (rotation simulation)
    log_path.write_text("", encoding="utf-8")
    _write_lines(log_path, [
        json.dumps({"event": "new1"}),
        json.dumps({"event": "new2"}),
    ])

    results = tail.read_new()
    assert len(results) == 2
    assert [r["event"] for r in results] == ["new1", "new2"]


def test_log_tail_returns_empty_for_missing_file(tmp_path):
    """Non-existent file → no exception, just an empty list. Bot may not have
    started writing yet when overseer starts up."""
    from ops.overseer.ingestors.log_tail import JsonLogTail

    tail = JsonLogTail(str(tmp_path / "does_not_exist.log"))
    assert tail.read_new() == []


def test_log_tail_read_recent_returns_ring_buffer(tmp_path):
    """Ring buffer caps at max_buffer; read_recent returns only the last
    `max_buffer` parsed entries — older are dropped to keep memory bounded."""
    from ops.overseer.ingestors.log_tail import JsonLogTail

    log_path = tmp_path / "bot.log"
    _write_lines(
        log_path,
        [json.dumps({"event": f"e{i}", "i": i}) for i in range(1500)],
    )

    tail = JsonLogTail(str(log_path), max_buffer=1000)
    tail.read_new()
    recent = tail.read_recent()
    assert len(recent) == 1000
    # Last 1000 entries → i in [500, 1499]
    assert recent[0]["i"] == 500
    assert recent[-1]["i"] == 1499


# ─────────────────────────────────────────────────────────────────────
# HealthzPoller — urllib-based health check with failure-streak tracking.
# ─────────────────────────────────────────────────────────────────────


class _FakeResponse:
    """Minimal stand-in for urllib's HTTPResponse object."""
    def __init__(self, status: int, body: bytes = b'{"ok": true}'):
        self.status = status
        self.code = status  # urllib.request sets either depending on version
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_healthz_poller_ok_response(monkeypatch):
    """200 → ok=True, status_code=200, network reachable."""
    from ops.overseer.ingestors import healthz_poller as hp_mod
    from ops.overseer.ingestors.healthz_poller import HealthzPoller

    monkeypatch.setattr(
        hp_mod.urllib.request,
        "urlopen",
        lambda *a, **kw: _FakeResponse(200),
    )

    p = HealthzPoller("http://x/healthz")
    result = p.poll_once()
    assert result["ok"] is True
    assert result["status_code"] == 200
    assert isinstance(result["checked_at"], int)


def test_healthz_poller_500_response(monkeypatch):
    """500 → ok=False, status preserved, failure streak increments."""
    from ops.overseer.ingestors import healthz_poller as hp_mod
    from ops.overseer.ingestors.healthz_poller import HealthzPoller

    monkeypatch.setattr(
        hp_mod.urllib.request,
        "urlopen",
        lambda *a, **kw: _FakeResponse(500),
    )

    p = HealthzPoller("http://x/healthz")
    result = p.poll_once()
    assert result["ok"] is False
    assert result["status_code"] == 500
    assert p.state()["consecutive_failures"] == 1


def test_healthz_poller_network_error(monkeypatch):
    """URLError → ok=False, status_code=0 (no HTTP response received)."""
    from ops.overseer.ingestors import healthz_poller as hp_mod
    from ops.overseer.ingestors.healthz_poller import HealthzPoller

    def boom(*_a, **_kw):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(hp_mod.urllib.request, "urlopen", boom)

    p = HealthzPoller("http://x/healthz")
    result = p.poll_once()
    assert result["ok"] is False
    assert result["status_code"] == 0
    assert p.state()["consecutive_failures"] == 1


def test_healthz_poller_consecutive_failures_increment(monkeypatch):
    """3 fails in a row → state.consecutive_failures == 3 — feeds rule_bot_unhealthy."""
    from ops.overseer.ingestors import healthz_poller as hp_mod
    from ops.overseer.ingestors.healthz_poller import HealthzPoller

    monkeypatch.setattr(
        hp_mod.urllib.request,
        "urlopen",
        lambda *a, **kw: _FakeResponse(503),
    )

    p = HealthzPoller("http://x/healthz")
    p.poll_once()
    p.poll_once()
    p.poll_once()
    assert p.state()["consecutive_failures"] == 3


def test_healthz_poller_resets_on_success(monkeypatch):
    """fail, fail, ok sequence → consec=0 + last_ok_ts populated. Counter
    resets so transient failures don't cause stale alerts."""
    from ops.overseer.ingestors import healthz_poller as hp_mod
    from ops.overseer.ingestors.healthz_poller import HealthzPoller

    responses = [_FakeResponse(500), _FakeResponse(500), _FakeResponse(200)]

    def fake_urlopen(*_a, **_kw):
        return responses.pop(0)

    monkeypatch.setattr(hp_mod.urllib.request, "urlopen", fake_urlopen)

    p = HealthzPoller("http://x/healthz")
    p.poll_once()
    p.poll_once()
    p.poll_once()
    state = p.state()
    assert state["consecutive_failures"] == 0
    assert state["last_ok_ts"] is not None
    assert isinstance(state["last_ok_ts"], int)


# ─────────────────────────────────────────────────────────────────────
# JournalTail — read-only tail of trade_journal.jsonl.
# ─────────────────────────────────────────────────────────────────────


def test_journal_tail_reads_jsonl(tmp_path):
    """5 valid TradeSnapshot lines → read_recent returns 5 dicts."""
    from ops.overseer.ingestors.journal_tail import JournalTail

    j_path = tmp_path / "trade_journal.jsonl"
    with j_path.open("w", encoding="utf-8") as f:
        for i in range(5):
            f.write(json.dumps({
                "trade_id": f"T{i}",
                "symbol": "BTC/USDT",
                "realized_pnl": 10.0 if i % 2 == 0 else -5.0,
            }) + "\n")

    tail = JournalTail(str(j_path))
    results = tail.read_recent()
    assert len(results) == 5
    assert results[0]["trade_id"] == "T0"
    assert results[-1]["trade_id"] == "T4"


def test_journal_tail_missing_file_returns_empty(tmp_path):
    """Non-existent journal → empty list (bot may not have closed any trade yet)."""
    from ops.overseer.ingestors.journal_tail import JournalTail

    tail = JournalTail(str(tmp_path / "nope.jsonl"))
    assert tail.read_recent() == []


def test_journal_tail_max_recent_limits_result(tmp_path):
    """100 trades, max_recent=10 → only last 10 returned (memory-bounded)."""
    from ops.overseer.ingestors.journal_tail import JournalTail

    j_path = tmp_path / "trade_journal.jsonl"
    with j_path.open("w", encoding="utf-8") as f:
        for i in range(100):
            f.write(json.dumps({"trade_id": f"T{i}", "realized_pnl": 1.0}) + "\n")

    tail = JournalTail(str(j_path), max_recent=10)
    results = tail.read_recent()
    assert len(results) == 10
    assert results[0]["trade_id"] == "T90"
    assert results[-1]["trade_id"] == "T99"


def test_journal_tail_handles_corrupted_line(tmp_path):
    """Mix of valid + invalid JSON → valid lines returned, invalid skipped silently."""
    from ops.overseer.ingestors.journal_tail import JournalTail

    j_path = tmp_path / "trade_journal.jsonl"
    with j_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"trade_id": "ok1"}) + "\n")
        f.write("{ this is broken\n")
        f.write(json.dumps({"trade_id": "ok2"}) + "\n")

    tail = JournalTail(str(j_path))
    results = tail.read_recent()
    assert len(results) == 2
    assert [r["trade_id"] for r in results] == ["ok1", "ok2"]
