from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "extract_sl_evidence.py"


@pytest.fixture()
def sample_rows():
    return [
        {
            "trade_id": "trade-1",
            "symbol": "OP/USDT",
            "direction": "LONG",
            "entry": "2.0000",
            "sl": "1.9000",
            "exit": "1.9100",
            "reason": "SL",
            "pnl": "-5.5",
            "pnl_pct": "-1.2",
            "size": "10",
            "opened_at": "2026-05-10T00:00:00+00:00",
            "closed_at": "2026-05-10T01:00:00+00:00",
            "entry_score": "6.5",
            "sl_score": "3.0",
            "rr_score": "5.5",
            "overall_score": "4.9",
            "outcome": "SL",
            "notes": {"atr_14h": 0.05, "trace_id_used": True},
        },
        {
            "trade_id": "trade-2",
            "symbol": "FIL/USDT",
            "direction": "SHORT",
            "entry": "5.0000",
            "sl": "5.2500",
            "exit": "4.7500",
            "reason": "TP1",
            "pnl": "8.0",
            "pnl_pct": "1.6",
            "size": "4",
            "opened_at": "2026-05-10T02:00:00+00:00",
            "closed_at": "2026-05-10T04:00:00+00:00",
            "entry_score": "7.0",
            "sl_score": "8.0",
            "rr_score": "6.0",
            "overall_score": "7.1",
            "outcome": "TP1",
            "notes": {"atr_14h": 0.1},
        },
    ]


def test_cli_help_works_without_db():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0
    assert "--since" in result.stdout
    assert "--symbols" in result.stdout
    assert "--out" in result.stdout


def test_dry_run_writes_no_files(tmp_path):
    out = tmp_path / "evidence.csv"
    summary = tmp_path / "summary.md"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--since",
            "2026-05-01T00:00:00Z",
            "--symbols",
            "OP/USDT,FIL/USDT",
            "--out",
            str(out),
            "--summary",
            str(summary),
            "--dry-run",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "DRY RUN" in result.stdout
    assert not out.exists()
    assert not summary.exists()


def test_sql_uses_bound_parameters_and_select_only_guard():
    from scripts._sl_evidence import db

    sql, args = db.build_trade_query("2026-05-01T00:00:00Z", ["OP/USDT", "FIL/USDT"])
    assert "SELECT" in sql.upper()
    assert "$1" in sql and "$2" in sql
    assert "OP/USDT" not in sql
    assert "FIL/USDT" not in sql
    assert args == ["2026-05-01T00:00:00Z", ["OP/USDT", "FIL/USDT"]]
    db.assert_select_only(sql)
    for bad_sql in [
        "UPDATE trades SET pnl=0",
        "delete from trades",
        "DROP TABLE trades",
        "ALTER TABLE trades ADD x int",
        "INSERT INTO trades DEFAULT VALUES",
    ]:
        with pytest.raises(ValueError):
            db.assert_select_only(bad_sql)


def test_csv_null_handling_and_column_order(tmp_path, sample_rows):
    from scripts._sl_evidence.render import CSV_COLUMNS, write_csv

    rows = [dict(sample_rows[0], atr14=None, mae_pct=None, mfe_pct=None, journal_present=False)]
    out = tmp_path / "evidence.csv"
    write_csv(rows, out)

    with out.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CSV_COLUMNS
        got = list(reader)
    assert got[0]["atr14"] == ""
    assert got[0]["mae_pct"] == ""
    assert got[0]["journal_present"] == "false"


def test_journal_parser_tolerates_missing_file(tmp_path):
    from scripts._sl_evidence.journal import load_journal

    entries, warnings = load_journal(tmp_path / "missing.jsonl")
    assert entries == {}
    assert len(warnings) == 1
    assert "missing" in warnings[0].lower()


def test_journal_parser_tolerates_malformed_lines(tmp_path):
    from scripts._sl_evidence.journal import load_journal

    journal = tmp_path / "trade_journal.jsonl"
    journal.write_text(
        json.dumps({"trade_id": "trade-1", "max_adverse_excursion_pct": 1.25, "max_favorable_excursion_pct": 2.5})
        + "\nnot-json\n"
        + json.dumps({"trade_id": "trade-2", "mae_pct": 0.5, "mfe_pct": 1.0})
        + "\n",
        encoding="utf-8",
    )

    entries, warnings = load_journal(journal)
    assert entries["trade-1"].mae_pct == 1.25
    assert entries["trade-2"].mfe_pct == 1.0
    assert any("malformed" in w.lower() for w in warnings)


def test_summary_markdown_renders_required_sections(sample_rows):
    from scripts._sl_evidence.render import render_summary

    md = render_summary(sample_rows, warnings=["journal missing"])
    for section in [
        "# Phase 0 SL Evidence Summary",
        "## Per-symbol aggregates",
        "## H1 indicator — protection failure",
        "## H2 indicator — SL price logic",
        "## H3 indicator — strategy expectancy",
        "## H4 indicator — reconcile mismatch",
        "## Decision matrix",
    ]:
        assert section in md
    assert "OP/USDT" in md and "FIL/USDT" in md
    assert "| Hypothesis | Evidence | Utku verdict |" in md
    assert "TBD by Utku" in md


def test_no_secrets_in_outputs(tmp_path, monkeypatch, sample_rows, capsys):
    from scripts._sl_evidence.render import render_summary, write_csv
    from scripts._sl_evidence.secrets import assert_no_secrets

    secret = "postgres://user:supersecret@example/db"
    monkeypatch.setenv("DATABASE_URL", secret)
    out = tmp_path / "evidence.csv"
    write_csv(sample_rows, out)
    summary = render_summary(sample_rows, warnings=[])
    print("wrote evidence")
    captured = capsys.readouterr()

    combined = out.read_text(encoding="utf-8") + summary + captured.out + captured.err
    assert secret not in combined
    assert_no_secrets(combined)


def test_idempotent_csv_and_summary_output(tmp_path, sample_rows):
    from scripts._sl_evidence.render import render_summary, write_csv

    out1 = tmp_path / "a.csv"
    out2 = tmp_path / "b.csv"
    write_csv(sample_rows, out1)
    write_csv(list(reversed(sample_rows)), out2)
    md1 = render_summary(sample_rows, warnings=[])
    md2 = render_summary(list(reversed(sample_rows)), warnings=[])

    assert hashlib.sha256(out1.read_bytes()).hexdigest() == hashlib.sha256(out2.read_bytes()).hexdigest()
    assert hashlib.sha256(md1.encode()).hexdigest() == hashlib.sha256(md2.encode()).hexdigest()


def test_import_guard_forbidden_exchange_and_safety_modules():
    script_text = SCRIPT.read_text(encoding="utf-8")
    forbidden = ["BinanceClient", "ccxt", "engine.safety", "engine.lifecycle", "engine.safe_orchestrator", "exchange"]
    assert not any(token in script_text for token in forbidden)
