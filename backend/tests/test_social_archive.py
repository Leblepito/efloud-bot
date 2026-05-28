"""Social doctrine archive tests."""

import json


def test_append_doctrine_snapshot_writes_jsonl_with_content_hash_and_dedup(tmp_path):
    from backend.social.archive import append_doctrine_snapshot, load_doctrine_snapshots

    path = tmp_path / "social_doctrine.jsonl"
    item = {
        "id": "tg-1",
        "source": "telegram",
        "author": "Efloud TA & Charts",
        "content": "BTC 1D bullish MSB OTE FVG",
        "timestamp": "2026-05-28T00:00:00Z",
    }
    doctrine = {
        "feed_id": "tg-1",
        "symbols": ["BTC/USDT"],
        "timeframes": ["1d"],
        "bias": "bullish",
        "zones": ["OTE", "FVG"],
    }

    first = append_doctrine_snapshot(path, item, doctrine)
    second = append_doctrine_snapshot(path, item, doctrine)

    assert first["written"] is True
    assert second["written"] is False
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["dedup_key"].startswith("telegram:tg-1:")
    assert len(row["content_hash"]) == 64
    assert row["item"]["content"] == item["content"]
    assert row["doctrine"] == doctrine
    assert load_doctrine_snapshots(path) == [row]


def test_load_doctrine_snapshots_tolerates_missing_file(tmp_path):
    from backend.social.archive import load_doctrine_snapshots

    assert load_doctrine_snapshots(tmp_path / "missing.jsonl") == []
