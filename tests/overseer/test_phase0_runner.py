"""Overseer Phase0Runner — subprocess wrapper for scripts/extract_sl_evidence.py.

All subprocess.run calls are monkeypatched so the test suite never executes
the actual script (which would hit a real DB). Coverage: arg construction,
default since/symbols, output-dir creation, stdout/stderr tail capture,
failure paths (CalledProcessError, TimeoutExpired, generic Exception)."""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


# ─────────────────────────────────────────────────────────────────────
# Helpers — record subprocess.run invocations without actually executing.
# ─────────────────────────────────────────────────────────────────────


class _RunRecorder:
    """Callable replacement for subprocess.run. Captures kwargs and returns
    a configurable CompletedProcess (or raises if asked)."""

    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str = "ok",
        stderr: str = "",
        raise_exc: Exception | None = None,
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.raise_exc = raise_exc
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *args, **kwargs):
        # subprocess.run signature: run(args, ..., capture_output=, text=, timeout=, check=)
        self.calls.append({"args": args, "kwargs": kwargs})
        if self.raise_exc is not None:
            raise self.raise_exc
        return subprocess.CompletedProcess(
            args=args[0] if args else kwargs.get("args"),
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def _extract_cmd(call: dict[str, Any]) -> list[str]:
    """The subprocess.run command is the first positional or the 'args' kwarg."""
    if call["args"]:
        return list(call["args"][0])
    return list(call["kwargs"]["args"])


# ─────────────────────────────────────────────────────────────────────
# Dry-run path.
# ─────────────────────────────────────────────────────────────────────


def test_phase0_runner_dry_run_returns_command_without_executing(monkeypatch, tmp_path):
    """dry_run=True must build the command but never call subprocess.run —
    cron-driven jobs use this to print the plan in staging before flipping on."""
    from ops.overseer.phase0_runner import Phase0Runner

    rec = _RunRecorder()
    monkeypatch.setattr(subprocess, "run", rec)

    r = Phase0Runner()
    result = r.run(out_dir=str(tmp_path), dry_run=True)

    assert result["status"] == "dry_run"
    assert rec.calls == []


# ─────────────────────────────────────────────────────────────────────
# Argument construction.
# ─────────────────────────────────────────────────────────────────────


def test_phase0_runner_builds_correct_subprocess_args(monkeypatch, tmp_path):
    """Command must include the script path + every required CLI flag the
    underlying extract_sl_evidence.py defines (--since, --symbols, --out, --summary)."""
    from ops.overseer.phase0_runner import Phase0Runner

    rec = _RunRecorder()
    monkeypatch.setattr(subprocess, "run", rec)

    r = Phase0Runner(script_path="scripts/extract_sl_evidence.py")
    r.run(out_dir=str(tmp_path))

    assert len(rec.calls) == 1
    cmd = _extract_cmd(rec.calls[0])
    assert "scripts/extract_sl_evidence.py" in cmd
    # All four required flags must appear; values follow as the next token.
    for flag in ("--since", "--symbols", "--out", "--summary"):
        assert flag in cmd, f"missing CLI flag {flag} in {cmd}"


def test_phase0_runner_default_since_is_7_days_ago(monkeypatch, tmp_path):
    """Default lookback = 7d ago in ISO Z — matches Phase 0 evidence window."""
    from ops.overseer.phase0_runner import Phase0Runner

    rec = _RunRecorder()
    monkeypatch.setattr(subprocess, "run", rec)

    r = Phase0Runner()
    r.run(out_dir=str(tmp_path))

    cmd = _extract_cmd(rec.calls[0])
    idx = cmd.index("--since")
    since_val = cmd[idx + 1]
    # ISO 8601 with trailing Z; parsing must succeed.
    parsed = datetime.fromisoformat(since_val.replace("Z", "+00:00"))
    expected = datetime.now(timezone.utc) - timedelta(days=7)
    delta = abs((parsed - expected).total_seconds())
    assert delta < 3600, f"since {since_val} more than 1h off from 7d-ago"


def test_phase0_runner_default_symbols_includes_phase0_set(monkeypatch, tmp_path):
    """The Phase 0 evidence set is fixed (OP/FIL/BTC/ETH/ADA/SUI/LTC) — the
    runner must default to that exact universe so cron output stays stable."""
    from ops.overseer.phase0_runner import Phase0Runner

    rec = _RunRecorder()
    monkeypatch.setattr(subprocess, "run", rec)

    r = Phase0Runner()
    r.run(out_dir=str(tmp_path))

    cmd = _extract_cmd(rec.calls[0])
    idx = cmd.index("--symbols")
    symbols_val = cmd[idx + 1]
    for sym in ("OP/USDT", "FIL/USDT", "BTC/USDT", "ETH/USDT", "ADA/USDT", "SUI/USDT", "LTC/USDT"):
        assert sym in symbols_val, f"missing default symbol {sym} in {symbols_val}"


def test_phase0_runner_explicit_since_and_symbols_override_defaults(monkeypatch, tmp_path):
    """Caller can override defaults — important for ad-hoc backfills."""
    from ops.overseer.phase0_runner import Phase0Runner

    rec = _RunRecorder()
    monkeypatch.setattr(subprocess, "run", rec)

    r = Phase0Runner()
    r.run(
        since="2026-04-01T00:00:00Z",
        symbols=["BTC/USDT"],
        out_dir=str(tmp_path),
    )

    cmd = _extract_cmd(rec.calls[0])
    assert cmd[cmd.index("--since") + 1] == "2026-04-01T00:00:00Z"
    assert cmd[cmd.index("--symbols") + 1] == "BTC/USDT"


# ─────────────────────────────────────────────────────────────────────
# Output directory handling.
# ─────────────────────────────────────────────────────────────────────


def test_phase0_runner_creates_output_directory(monkeypatch, tmp_path):
    """The dated subdir must exist before the script writes into it —
    extract_sl_evidence.py would crash if the parent dir didn't exist."""
    from ops.overseer.phase0_runner import Phase0Runner

    rec = _RunRecorder()
    monkeypatch.setattr(subprocess, "run", rec)

    out_dir = tmp_path / "phase0"
    r = Phase0Runner()
    result = r.run(out_dir=str(out_dir))

    assert result["status"] == "ok"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert (out_dir / today_str).is_dir()


def test_phase0_runner_paths_include_dated_subdir(monkeypatch, tmp_path):
    """csv_path and summary_path point under {out_dir}/YYYY-MM-DD/ — keeps
    historical runs separable for trend analysis."""
    from ops.overseer.phase0_runner import Phase0Runner

    rec = _RunRecorder()
    monkeypatch.setattr(subprocess, "run", rec)

    out_dir = tmp_path / "phase0"
    r = Phase0Runner()
    result = r.run(out_dir=str(out_dir))

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert today_str in result["csv_path"]
    assert today_str in result["summary_path"]
    assert result["csv_path"].endswith(".csv")
    assert result["summary_path"].endswith(".md")


# ─────────────────────────────────────────────────────────────────────
# Stdout / stderr tail capture.
# ─────────────────────────────────────────────────────────────────────


def test_phase0_runner_captures_stdout_stderr_tail(monkeypatch, tmp_path):
    """Tails are capped to ≤1KB — full script output can be very long, but
    the overseer report only needs the tail for diagnostics."""
    from ops.overseer.phase0_runner import Phase0Runner

    big_out = "X" * 1500
    big_err = "Y" * 1500
    rec = _RunRecorder(stdout=big_out, stderr=big_err)
    monkeypatch.setattr(subprocess, "run", rec)

    r = Phase0Runner()
    result = r.run(out_dir=str(tmp_path))

    assert len(result["stdout_tail"]) <= 1024
    assert len(result["stderr_tail"]) <= 1024
    # Tail (not head) — last char must come from the end of the original buffer.
    assert result["stdout_tail"].endswith("X")
    assert result["stderr_tail"].endswith("Y")


# ─────────────────────────────────────────────────────────────────────
# Failure paths — must NEVER raise.
# ─────────────────────────────────────────────────────────────────────


def test_phase0_runner_subprocess_failure_returns_failed_status(monkeypatch, tmp_path):
    """Non-zero exit captured but does NOT raise — caller treats result dict
    as the source of truth, never relies on exceptions for control flow."""
    from ops.overseer.phase0_runner import Phase0Runner

    rec = _RunRecorder(returncode=2, stderr="DB error\n")
    monkeypatch.setattr(subprocess, "run", rec)

    r = Phase0Runner()
    result = r.run(out_dir=str(tmp_path))

    assert result["status"] == "failed"
    assert result["exit_code"] == 2
    assert "DB error" in result["stderr_tail"]


def test_phase0_runner_timeout_returns_failed(monkeypatch, tmp_path):
    """TimeoutExpired must surface as status='failed' (with a non-zero
    exit_code marker) so a hung extract job doesn't wedge the cron container."""
    from ops.overseer.phase0_runner import Phase0Runner

    timeout_exc = subprocess.TimeoutExpired(cmd=["python3"], timeout=1)
    rec = _RunRecorder(raise_exc=timeout_exc)
    monkeypatch.setattr(subprocess, "run", rec)

    r = Phase0Runner()
    result = r.run(out_dir=str(tmp_path))

    assert result["status"] == "failed"
    # exit_code must be non-zero — caller will compare != 0 to flag failure.
    assert result["exit_code"] != 0


def test_phase0_runner_never_raises_on_subprocess_exception(monkeypatch, tmp_path):
    """Generic OSError (e.g. file-not-found) must NOT bubble — same contract
    as the other failure paths so the watchdog can rely on result['status']."""
    from ops.overseer.phase0_runner import Phase0Runner

    rec = _RunRecorder(raise_exc=OSError("python3 not found"))
    monkeypatch.setattr(subprocess, "run", rec)

    r = Phase0Runner()
    result = r.run(out_dir=str(tmp_path))  # must NOT raise

    assert result["status"] == "failed"


def test_phase0_runner_records_duration(monkeypatch, tmp_path):
    """Caller will report this in the daily ops log — assert key exists +
    is non-negative even on a zero-cost mock invocation."""
    from ops.overseer.phase0_runner import Phase0Runner

    rec = _RunRecorder()
    monkeypatch.setattr(subprocess, "run", rec)

    r = Phase0Runner()
    result = r.run(out_dir=str(tmp_path))

    assert "duration_sec" in result
    assert result["duration_sec"] >= 0.0
