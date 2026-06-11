"""T-013 (P-003 W1): monthly statement tests.

Covers the journal->summary adapter, the 30-day window filter, markdown/CSV
rendering, the CLI writer, and the /api/reports/monthly endpoint (401 + 200).
compute_summary() itself is NOT re-tested here (tests/test_daily_aggregate.py
owns it) — the card requires it to be called unchanged, so these tests only
assert the integration surface.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ops.daily_report.monthly import (
    build_monthly_statement,
    main,
    read_journal_closed_trades,
    render_csv,
    render_markdown,
)

NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)


def _journal_line(
    *,
    trade_id: str = "t1",
    symbol: str = "BTC/USDT",
    direction: str = "LONG",
    realized_pnl: float = 10.0,
    realized_pnl_pct: float = 1.0,
    exit_reason: str = "tp1",
    exit_offset_days: float = 1.0,
    include_exit: bool = True,
) -> dict:
    """A journal row using the journal's native keys (NOT the DB-row keys)."""
    exit_ts = (NOW - timedelta(days=exit_offset_days)).isoformat()
    entry_ts = (NOW - timedelta(days=exit_offset_days, hours=4)).isoformat()
    row = {
        "trade_id": trade_id,
        "symbol": symbol,
        "direction": direction,
        "entry_price": 100.0,
        "exit_price": 101.0,
        "position_size": 0.5,
        "realized_pnl": realized_pnl,
        "realized_pnl_pct": realized_pnl_pct,
        "entry_timestamp": entry_ts,
        "confluence_score": 70,
    }
    if include_exit:
        row["exit_timestamp"] = exit_ts
        row["exit_reason"] = exit_reason
    return row


def _write_journal(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )


# ── adapter + window ─────────────────────────────────────────────────────


def test_adapter_maps_journal_keys_to_summary_keys(tmp_path: Path):
    journal = tmp_path / "journal.jsonl"
    _write_journal(journal, [_journal_line(realized_pnl=12.5, exit_reason="tp2")])

    trades = read_journal_closed_trades(journal, now_utc=NOW, window_days=30)

    assert len(trades) == 1
    t = trades[0]
    # compute_summary() contract keys (aggregate.py docstring)
    assert t["pnl_usdt"] == 12.5
    assert t["reason"] == "tp2"
    assert t["symbol"] == "BTC/USDT"
    assert t["direction"] == "LONG"
    assert t["opened_at"] < t["closed_at"]


def test_window_excludes_old_and_open_trades(tmp_path: Path):
    journal = tmp_path / "journal.jsonl"
    _write_journal(journal, [
        _journal_line(trade_id="in-window", exit_offset_days=5),
        _journal_line(trade_id="too-old", exit_offset_days=45),
        _journal_line(trade_id="still-open", include_exit=False),
    ])

    trades = read_journal_closed_trades(journal, now_utc=NOW, window_days=30)

    assert [t["id"] for t in trades] == ["in-window"]


def test_missing_journal_returns_empty(tmp_path: Path):
    trades = read_journal_closed_trades(
        tmp_path / "missing.jsonl", now_utc=NOW, window_days=30
    )
    assert trades == []


def test_corrupt_lines_skipped(tmp_path: Path):
    journal = tmp_path / "journal.jsonl"
    good = json.dumps(_journal_line(trade_id="ok"))
    journal.write_text("not-json\n" + good + "\n{truncated", encoding="utf-8")

    trades = read_journal_closed_trades(journal, now_utc=NOW, window_days=30)
    assert [t["id"] for t in trades] == ["ok"]


def test_garbage_exit_timestamp_dropped(tmp_path: Path):
    """Geçerli JSON ama parse edilemeyen exit_timestamp → satır sessizce düşer."""
    journal = tmp_path / "journal.jsonl"
    bad = _journal_line(trade_id="bad")
    bad["exit_timestamp"] = "garbage"
    _write_journal(journal, [bad, _journal_line(trade_id="ok")])

    trades = read_journal_closed_trades(journal, now_utc=NOW, window_days=30)
    assert [t["id"] for t in trades] == ["ok"]


def test_trades_sorted_chronologically_by_parsed_ts(tmp_path: Path):
    """Sıralama parse edilmiş exit_ts ile — naive + tz'li karışımında bile kronolojik."""
    journal = tmp_path / "journal.jsonl"
    older = _journal_line(trade_id="older", exit_offset_days=10)
    newer = _journal_line(trade_id="newer", exit_offset_days=2)
    # naive isoformat (journal'ın utcnow() emsali) — tz'li satırlarla karışsın
    naive_mid = _journal_line(trade_id="mid", exit_offset_days=5)
    naive_mid["exit_timestamp"] = (
        (NOW - timedelta(days=5)).replace(tzinfo=None).isoformat()
    )
    _write_journal(journal, [newer, naive_mid, older])

    trades = read_journal_closed_trades(journal, now_utc=NOW, window_days=30)
    assert [t["id"] for t in trades] == ["older", "mid", "newer"]


# ── statement (compute_summary integration) ──────────────────────────────


def test_statement_summary_via_compute_summary(tmp_path: Path):
    journal = tmp_path / "journal.jsonl"
    _write_journal(journal, [
        _journal_line(trade_id="w1", realized_pnl=10.0),
        _journal_line(trade_id="w2", realized_pnl=5.0),
        _journal_line(trade_id="l1", realized_pnl=-3.0),
    ])
    trades = read_journal_closed_trades(journal, now_utc=NOW, window_days=30)

    statement = build_monthly_statement(trades, now_utc=NOW, window_days=30)

    s = statement["summary"]
    assert s["trade_count"] == 3
    assert s["wins"] == 2 and s["losses"] == 1
    assert s["win_rate_pct"] == pytest.approx(66.67)
    assert statement["window"]["days"] == 30
    assert statement["window"]["until"].startswith("2026-06-11")


def test_statement_marks_dbless_equity_explicitly(tmp_path: Path):
    """UR-003 pin: DB-less prod'da equity_start/end None — statement bunu
    sessizce gizlemek yerine açıkça işaretlemeli."""
    statement = build_monthly_statement([], now_utc=NOW, window_days=30)

    assert statement["summary"]["equity_start"] is None
    assert statement["equity_note"]  # non-empty explanation
    md = render_markdown(statement)
    assert "n/a" in md  # equity shown as n/a, not blank/0


# ── renderers ────────────────────────────────────────────────────────────


def test_render_markdown_contains_core_fields(tmp_path: Path):
    journal = tmp_path / "journal.jsonl"
    _write_journal(journal, [_journal_line(realized_pnl=10.0)])
    trades = read_journal_closed_trades(journal, now_utc=NOW, window_days=30)
    statement = build_monthly_statement(trades, now_utc=NOW, window_days=30)

    md = render_markdown(statement)

    assert "2026-06" in md
    assert "Trade sayısı" in md or "trade_count" in md
    assert "100.0" in md or "100.00" in md  # win rate %100 (tek kazanan)


def test_render_csv_one_row_per_trade(tmp_path: Path):
    journal = tmp_path / "journal.jsonl"
    _write_journal(journal, [
        _journal_line(trade_id="a", realized_pnl=10.0),
        _journal_line(trade_id="b", realized_pnl=-2.0, direction="SHORT"),
    ])
    trades = read_journal_closed_trades(journal, now_utc=NOW, window_days=30)

    csv_text = render_csv(trades)
    lines = csv_text.strip().splitlines()

    assert len(lines) == 3  # header + 2 trades
    assert lines[0].startswith("closed_at,")
    assert any(",SHORT," in ln for ln in lines[1:])


# ── CLI ──────────────────────────────────────────────────────────────────


def test_cli_writes_md_and_csv(tmp_path: Path, monkeypatch):
    journal = tmp_path / "journal.jsonl"
    _write_journal(journal, [_journal_line()])
    out_dir = tmp_path / "reports"

    rc = main([
        "--journal", str(journal),
        "--out-dir", str(out_dir),
        "--window-days", "30",
    ])

    assert rc == 0
    written = sorted(p.name for p in out_dir.iterdir())
    assert len(written) == 2
    assert any(n.endswith(".md") for n in written)
    assert any(n.endswith(".csv") for n in written)


def test_cli_empty_journal_still_succeeds(tmp_path: Path):
    """Boş ay = hata değil; ' 0 trade' statement'ı üretilir (cron güvenliği)."""
    rc = main([
        "--journal", str(tmp_path / "missing.jsonl"),
        "--out-dir", str(tmp_path / "reports"),
    ])
    assert rc == 0


# ── endpoint ─────────────────────────────────────────────────────────────


@pytest.fixture
def api_app():
    from fastapi import FastAPI
    from backend.api import router

    app = FastAPI()
    app.include_router(router)
    return app


def test_endpoint_requires_auth(api_app):
    from fastapi.testclient import TestClient

    r = TestClient(api_app).get("/api/reports/monthly")
    assert r.status_code == 401


def test_endpoint_returns_statement_when_authed(api_app, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.auth import require_auth

    journal = tmp_path / "journal.jsonl"
    _write_journal(journal, [_journal_line(realized_pnl=7.0)])
    monkeypatch.setenv("EFLOUD_TRADE_JOURNAL", str(journal))

    api_app.dependency_overrides[require_auth] = lambda: None
    r = TestClient(api_app).get("/api/reports/monthly?window_days=30")

    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["trade_count"] == 1
    assert body["window"]["days"] == 30


def test_endpoint_clamps_window(api_app, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.auth import require_auth

    monkeypatch.setenv("EFLOUD_TRADE_JOURNAL", str(tmp_path / "none.jsonl"))
    api_app.dependency_overrides[require_auth] = lambda: None

    r = TestClient(api_app).get("/api/reports/monthly?window_days=9999")
    assert r.status_code == 200
    assert r.json()["window"]["days"] <= 92

    r = TestClient(api_app).get("/api/reports/monthly?window_days=0")
    assert r.status_code == 200
    assert r.json()["window"]["days"] == 1
