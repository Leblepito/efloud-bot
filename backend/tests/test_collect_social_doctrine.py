"""Collection job: feeds -> doctrine -> archive.

Covers the 'Next integration slice' item #1 in
docs/handoff/2026-05-28_unified-social-learning-hedge-integration.md.

The script must stay research-only: no live config touched, no network
calls in tests, all writes confined to the supplied archive path.
"""
from __future__ import annotations

import json
import sys
import types

import pytest

from scripts import collect_social_doctrine as collector


@pytest.fixture
def fake_feed() -> dict[str, list[dict]]:
    return {
        "telegram": [
            {
                "id": "tg-fb1",
                "source": "telegram",
                "author": "Efloud TA & Charts",
                "content": (
                    "BTC Güncelleme: 1D grafikte market yapısı bullish (MSB). "
                    "OTE bölgesinden FVG ile 103k hedefine doğru."
                ),
                "timestamp": "2026-05-26T14:30:00Z",
            }
        ],
        "twitter": [
            {
                "id": "tw-1",
                "source": "twitter",
                "author": "@EfloudTheSurfer",
                "content": "MSB ilk şarttır. HTF trend uyumu olmadan giriş yok.",
                "timestamp": "2026-05-27T08:12:00Z",
            }
        ],
    }


def _patch_fetch(monkeypatch, feed: dict) -> None:
    async def _fake_fetch(*_args, **_kwargs):
        return feed

    monkeypatch.setattr(collector, "fetch_social_feeds", _fake_fetch)


def test_collector_appends_each_feed_item(tmp_path, monkeypatch, fake_feed):
    _patch_fetch(monkeypatch, fake_feed)
    archive = tmp_path / "social_doctrine.jsonl"

    summary = collector.run(archive_path=archive)

    assert summary["written"] == 2
    assert summary["skipped"] == 0
    assert archive.exists()
    rows = [json.loads(line) for line in archive.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 2
    for row in rows:
        assert "doctrine" in row and "item" in row
        assert row["doctrine"]["feed_id"] in {"tg-fb1", "tw-1"}


def test_collector_dedups_repeated_items(tmp_path, monkeypatch, fake_feed):
    _patch_fetch(monkeypatch, fake_feed)
    archive = tmp_path / "social_doctrine.jsonl"

    first = collector.run(archive_path=archive)
    second = collector.run(archive_path=archive)

    assert first["written"] == 2
    assert second["written"] == 0
    assert second["skipped"] == 2


def test_collector_dry_run_does_not_write(tmp_path, monkeypatch, fake_feed):
    _patch_fetch(monkeypatch, fake_feed)
    archive = tmp_path / "social_doctrine.jsonl"

    summary = collector.run(archive_path=archive, dry_run=True)

    assert summary["written"] == 0
    assert summary["would_write"] == 2
    assert not archive.exists()


def test_collector_refuses_protected_archive_paths(tmp_path, monkeypatch, fake_feed):
    _patch_fetch(monkeypatch, fake_feed)
    for forbidden in ("config.yaml", "config.phase2_1k.yaml", ".env"):
        with pytest.raises(ValueError):
            collector.run(archive_path=tmp_path / forbidden)


def test_collector_main_entrypoint_accepts_archive_flag(tmp_path, monkeypatch, fake_feed):
    _patch_fetch(monkeypatch, fake_feed)
    archive = tmp_path / "social_doctrine.jsonl"

    rc = collector.main(["--archive", str(archive)])

    assert rc == 0
    assert archive.exists()


def test_collector_main_dry_run_flag(tmp_path, monkeypatch, fake_feed, capsys):
    _patch_fetch(monkeypatch, fake_feed)
    archive = tmp_path / "social_doctrine.jsonl"

    rc = collector.main(["--archive", str(archive), "--dry-run"])

    assert rc == 0
    assert not archive.exists()
    captured = capsys.readouterr()
    assert "would_write" in captured.out.lower() or "would write" in captured.out.lower()
