"""Gap report between social-doctrine tags and SMC v2 engine modules.

Covers Task 9 of docs/superpowers/plans/2026-05-28-social-learning-
backtest-frontend.md. The script must never edit engine code; its only
output is a markdown report under reports/social_research/.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import report_doctrine_engine_gap as gap


def _write_archive(path: Path, doctrines: list[dict]) -> None:
    rows = [
        {
            "archived_at": "2026-05-28T12:00:00Z",
            "dedup_key": f"src:item-{i}:hash{i}",
            "content_hash": f"hash{i}",
            "item": {"id": f"item-{i}", "source": "telegram", "content": "x"},
            "doctrine": doctrine,
        }
        for i, doctrine in enumerate(doctrines)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def test_collect_tag_usage_aggregates_across_doctrines(tmp_path):
    archive = tmp_path / "social_doctrine.jsonl"
    _write_archive(
        archive,
        [
            {
                "zones": ["FVG", "OTE"],
                "structure_terms": ["MSB"],
                "liquidity_terms": [],
                "risk_terms": ["risk_management"],
            },
            {
                "zones": ["FVG"],
                "structure_terms": ["BOS"],
                "liquidity_terms": ["liquidity_sweep"],
                "risk_terms": [],
            },
        ],
    )

    usage = gap.collect_tag_usage(archive)

    assert usage["FVG"] == 2
    assert usage["OTE"] == 1
    assert usage["MSB"] == 1
    assert usage["BOS"] == 1
    assert usage["liquidity_sweep"] == 1
    assert usage["risk_management"] == 1


def test_classify_tags_flags_implemented_vs_missing(tmp_path):
    engine_root = tmp_path / "engine" / "smc_v2"
    engine_root.mkdir(parents=True)
    (engine_root / "zones.py").write_text("# stub", encoding="utf-8")
    (engine_root / "swing_anchor.py").write_text("# stub", encoding="utf-8")
    # liquidity_pools.py intentionally absent.

    usage = {
        "FVG": 3,
        "OTE": 2,
        "MSB": 1,
        "liquidity_sweep": 4,
        "MPA": 1,
    }

    classified = gap.classify_tags(usage, repo_root=tmp_path)

    fvg = next(row for row in classified if row["tag"] == "FVG")
    assert fvg["status"] == "implemented"
    assert "engine/smc_v2/zones.py" in fvg["module"]

    sweep = next(row for row in classified if row["tag"] == "liquidity_sweep")
    assert sweep["status"] == "missing"
    assert "engine/smc_v2/liquidity_pools.py" in sweep["module"]

    mpa = next(row for row in classified if row["tag"] == "MPA")
    assert mpa["status"] == "unmapped"


def test_render_markdown_lists_implemented_missing_unmapped():
    classified = [
        {"tag": "FVG", "count": 3, "status": "implemented", "module": "engine/smc_v2/zones.py"},
        {"tag": "liquidity_sweep", "count": 4, "status": "missing", "module": "engine/smc_v2/liquidity_pools.py"},
        {"tag": "MPA", "count": 1, "status": "unmapped", "module": None},
    ]

    md = gap.render_markdown(classified)

    assert "# Doctrine ↔ Engine Gap Report" in md
    assert "## Implemented" in md
    assert "FVG" in md and "engine/smc_v2/zones.py" in md
    assert "## Missing modules" in md
    assert "liquidity_sweep" in md and "engine/smc_v2/liquidity_pools.py" in md
    assert "## Unmapped tags" in md
    assert "MPA" in md
    assert "Research only" in md


def test_render_markdown_handles_empty_classification():
    md = gap.render_markdown([])
    assert "# Doctrine ↔ Engine Gap Report" in md
    assert "No doctrine snapshots" in md


def test_main_writes_report_file(tmp_path, monkeypatch):
    archive = tmp_path / "state" / "social_doctrine.jsonl"
    _write_archive(
        archive,
        [
            {
                "zones": ["FVG"],
                "structure_terms": ["MSB"],
                "liquidity_terms": ["liquidity_sweep"],
                "risk_terms": [],
            }
        ],
    )

    engine_root = tmp_path / "engine" / "smc_v2"
    engine_root.mkdir(parents=True)
    (engine_root / "zones.py").write_text("# stub", encoding="utf-8")
    (engine_root / "swing_anchor.py").write_text("# stub", encoding="utf-8")

    out_path = tmp_path / "reports" / "social_research" / "latest_gap_report.md"

    rc = gap.main([
        "--archive", str(archive),
        "--repo-root", str(tmp_path),
        "--out", str(out_path),
    ])

    assert rc == 0
    assert out_path.exists()
    body = out_path.read_text(encoding="utf-8")
    assert "FVG" in body
    assert "liquidity_sweep" in body


def test_main_missing_archive_returns_nonzero(tmp_path, capsys):
    rc = gap.main([
        "--archive", str(tmp_path / "does_not_exist.jsonl"),
        "--repo-root", str(tmp_path),
        "--out", str(tmp_path / "out.md"),
    ])
    assert rc != 0
    captured = capsys.readouterr()
    assert "not found" in captured.err.lower() or "no such" in captured.err.lower()
