"""Tests for scripts/desk/agent_verdict_edge.py — edge of AgentTeam verdicts from the journal.

The team runs in observation mode (gating false); each opened trade's verdict is
written to its journal row as agent_review.team_verdict. This report groups CLOSED
trades by verdict so the operator can decide, with evidence, whether the team
deserves a gating role.
"""
from __future__ import annotations

import json

import pytest

from scripts.desk import agent_verdict_edge as ave


def row(tid, pnl, verdict=None, closed=True, entry="2026-11-04T10:00:00+00:00", pct=None):
    r = {"trade_id": tid, "symbol": "BTC/USDT", "entry_timestamp": entry,
         "exit_timestamp": "2026-11-04T12:00:00+00:00" if closed else None,
         "realized_pnl": pnl, "realized_pnl_pct": pct if pct is not None else pnl / 10,
         "pnl_source": "exchange"}
    if verdict is not None:
        r["agent_review"] = {"team_verdict": verdict, "score": 0.5}
    return r


def write(tmp_path, rows, extra_lines=()):
    p = tmp_path / "trade_journal.jsonl"
    p.write_text("\n".join([*(json.dumps(r) for r in rows), *extra_lines]) + "\n")
    return p


def test_groups_closed_trades_by_verdict(tmp_path):
    p = write(tmp_path, [
        row("a", 10, "ACCEPT"), row("b", -5, "ACCEPT"), row("c", -8, "REJECT"),
        row("d", 4, "REJECT"), row("e", 3), row("f", 99, "ACCEPT", closed=False),
    ])
    rep = ave.report(ave.load(p))
    g = rep["groups"]
    assert g["ACCEPT"]["n"] == 2 and g["ACCEPT"]["wins"] == 1 and g["ACCEPT"]["total_pnl"] == 5
    assert g["REJECT"]["n"] == 2 and g["REJECT"]["total_pnl"] == -4
    assert g["NO_REVIEW"]["n"] == 1
    assert rep["closed"] == 5 and rep["open_skipped"] == 1


def test_what_if_skipping_rejects(tmp_path):
    p = write(tmp_path, [row("a", 10, "ACCEPT"), row("c", -8, "REJECT"), row("d", -2, "REJECT")])
    rep = ave.report(ave.load(p))
    assert rep["total_pnl"] == 0
    assert rep["what_if_skip_reject"]["total_pnl"] == 10
    assert rep["what_if_skip_reject"]["delta"] == 10


def test_last_row_per_trade_wins_and_bad_lines_are_counted(tmp_path):
    p = write(tmp_path, [row("a", 1, "NEUTRAL"), row("a", 7, "ACCEPT")], extra_lines=["{not json", ""])
    trades, bad = ave.load(p, with_errors=True)
    assert len(trades) == 1 and trades[0]["realized_pnl"] == 7
    assert bad == 1


def test_since_filter_uses_entry_timestamp(tmp_path):
    p = write(tmp_path, [row("old", 5, "ACCEPT", entry="2026-10-01T00:00:00+00:00"),
                         row("new", 3, "ACCEPT")])
    rep = ave.report(ave.load(p), since="2026-11-01T00:00:00+00:00")
    assert rep["closed"] == 1 and rep["groups"]["ACCEPT"]["total_pnl"] == 3


def test_since_accepts_a_plain_date_as_utc(tmp_path):
    p = write(tmp_path, [row("old", 5, "ACCEPT", entry="2026-10-01T00:00:00Z"),
                         row("new", 3, "ACCEPT")])
    rep = ave.report(ave.load(p), since="2026-11-01")
    assert rep["closed"] == 1


def test_small_samples_are_flagged(tmp_path):
    p = write(tmp_path, [row("a", 1, "ACCEPT")])
    rep = ave.report(ave.load(p))
    assert rep["groups"]["ACCEPT"]["small_sample"] is True


def test_cli_json(tmp_path, capsys):
    p = write(tmp_path, [row("a", 2, "ACCEPT"), row("b", -1, "REJECT")])
    assert ave.main(["--journal", str(p), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["groups"]["ACCEPT"]["n"] == 1


def test_cli_text_mentions_observation_mode(tmp_path, capsys):
    p = write(tmp_path, [row("a", 2, "ACCEPT")])
    assert ave.main(["--journal", str(p)]) == 0
    assert "observation" in capsys.readouterr().out.lower()


@pytest.mark.parametrize("missing", ["nope.jsonl"])
def test_missing_journal_is_refused(tmp_path, missing, capsys):
    assert ave.main(["--journal", str(tmp_path / missing)]) == 2
