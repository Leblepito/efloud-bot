"""CLI entrypoint — `python -m ops.overseer <subcommand>`.

Verifies argparse routing + exit codes for each subcommand. The watch
subcommand is the only long-running one; tests for it stub the env so
main() raises before entering the asyncio loop (we don't want a real
loop in unit tests).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest


def test_main_help_works(capsys):
    """`python -m ops.overseer --help` → SystemExit(0). argparse always
    emits help to stdout/stderr then exits cleanly."""
    from ops.overseer.__main__ import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    # argparse exits 0 on --help.
    assert exc_info.value.code == 0


def test_main_unknown_subcommand_exits_nonzero(capsys):
    """A bogus subcommand → non-zero exit (argparse defaults to 2)."""
    from ops.overseer.__main__ import main

    with pytest.raises(SystemExit) as exc_info:
        main(["bogus-subcommand"])
    assert exc_info.value.code != 0


def test_main_self_check_exits_zero(tmp_path, monkeypatch):
    """`self-check` imports all overseer modules + initialises state and
    exits 0 if nothing raises. Acts as the readiness probe inside cron jobs."""
    from ops.overseer.__main__ import main

    db_path = tmp_path / "state.sqlite"
    monkeypatch.setenv("EFLOUD_OVERSEER_STATE_DB", str(db_path))

    rc = main(["self-check"])
    assert rc == 0
    # State DB must have been bootstrapped — exit 0 implies SQLite open succeeded.
    assert db_path.exists()


def test_main_watch_requires_log_file_env(tmp_path, monkeypatch, capsys):
    """`watch` must fail loudly if EFLOUD_LOG_FILE / EFLOUD_HEALTHZ_URL /
    EFLOUD_OVERSEER_JOURNAL_PATH are missing — we don't want the sidecar
    to silently no-op on a mis-configured prod deploy.
    """
    from ops.overseer.__main__ import main

    monkeypatch.delenv("EFLOUD_LOG_FILE", raising=False)
    monkeypatch.delenv("EFLOUD_HEALTHZ_URL", raising=False)
    monkeypatch.delenv("EFLOUD_OVERSEER_JOURNAL_PATH", raising=False)
    monkeypatch.setenv("EFLOUD_OVERSEER_STATE_DB", str(tmp_path / "x.sqlite"))

    rc = main(["watch"])
    assert rc != 0


def test_main_extract_phase0_dry_run_outputs_json(tmp_path, monkeypatch, capsys):
    """`extract-phase0` writes a JSON status dict to stdout in dry-run mode
    so cron logs can be machine-parsed. Dry-run is the safe default for
    smoke tests; production cron passes a runtime flag to disable it
    (or we just always honour EFLOUD_OVERSEER_DRY_RUN here too)."""
    from ops.overseer.__main__ import main

    monkeypatch.setenv("EFLOUD_OVERSEER_STATE_DB", str(tmp_path / "state.sqlite"))
    # The Phase0Runner has its own dry_run param; the CLI honours the env flag.
    monkeypatch.setenv("EFLOUD_OVERSEER_DRY_RUN", "1")

    rc = main(["extract-phase0"])
    assert rc == 0

    captured = capsys.readouterr()
    # Parse stdout as JSON.
    payload = json.loads(captured.out.strip())
    # Expected keys from Phase0Runner.run() contract.
    for key in ("status", "exit_code", "csv_path", "summary_path", "command"):
        assert key in payload
    assert payload["status"] == "dry_run"


def test_main_summarize_missing_env_fails_loud(tmp_path, monkeypatch, capsys):
    """`summarize` requires EFLOUD_LOG_FILE + EFLOUD_OVERSEER_JOURNAL_PATH.

    Misconfig must fail with exit 1 so cron alerts on missing env rather
    than silently no-opping.
    """
    from ops.overseer.__main__ import main

    monkeypatch.setenv("EFLOUD_OVERSEER_STATE_DB", str(tmp_path / "state.sqlite"))
    monkeypatch.delenv("EFLOUD_LOG_FILE", raising=False)
    monkeypatch.delenv("EFLOUD_OVERSEER_JOURNAL_PATH", raising=False)
    rc = main(["summarize"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "EFLOUD_LOG_FILE" in captured.err
    assert "EFLOUD_OVERSEER_JOURNAL_PATH" in captured.err


def test_main_summarize_with_env_offline_succeeds(tmp_path, monkeypatch, capsys):
    """With env set + LLM offline, summarize emits placeholder and exits 0.

    `EFLOUD_OVERSEER_LLM_OFFLINE=1` makes Summarizer return `<LLM offline>`
    without calling Anthropic — the test runs end-to-end with no SDK.
    """
    from ops.overseer.__main__ import main

    log_path = tmp_path / "bot.log"
    journal_path = tmp_path / "trade_journal.jsonl"
    log_path.write_text("", encoding="utf-8")
    journal_path.write_text("", encoding="utf-8")

    monkeypatch.setenv("EFLOUD_OVERSEER_STATE_DB", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("EFLOUD_LOG_FILE", str(log_path))
    monkeypatch.setenv("EFLOUD_OVERSEER_JOURNAL_PATH", str(journal_path))
    monkeypatch.setenv("EFLOUD_OVERSEER_LLM_OFFLINE", "1")

    rc = main(["summarize"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "<LLM offline>" in captured.out


def test_main_report_missing_env_fails_loud(tmp_path, monkeypatch, capsys):
    """`report` requires EFLOUD_OVERSEER_JOURNAL_PATH. Misconfig → exit 1."""
    from ops.overseer.__main__ import main

    monkeypatch.setenv("EFLOUD_OVERSEER_STATE_DB", str(tmp_path / "state.sqlite"))
    monkeypatch.delenv("EFLOUD_OVERSEER_JOURNAL_PATH", raising=False)
    rc = main(["report"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "EFLOUD_OVERSEER_JOURNAL_PATH" in captured.err


def test_main_report_with_env_offline_succeeds(tmp_path, monkeypatch, capsys):
    """With env set + LLM offline, report emits placeholder and exits 0."""
    from ops.overseer.__main__ import main

    journal_path = tmp_path / "trade_journal.jsonl"
    journal_path.write_text("", encoding="utf-8")

    monkeypatch.setenv("EFLOUD_OVERSEER_STATE_DB", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("EFLOUD_OVERSEER_JOURNAL_PATH", str(journal_path))
    monkeypatch.setenv("EFLOUD_OVERSEER_LLM_OFFLINE", "1")

    rc = main(["report"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "<LLM offline>" in captured.out
