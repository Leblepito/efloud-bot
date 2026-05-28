"""Social research report helper tests."""


def test_build_social_research_snapshot_from_archive(tmp_path):
    from backend.social.archive import append_doctrine_snapshot
    from backend.social.reports import build_social_research_snapshot

    path = tmp_path / "social_doctrine.jsonl"
    append_doctrine_snapshot(
        path,
        {
            "id": "tg-1",
            "source": "telegram",
            "author": "Efloud TA & Charts",
            "content": "BTC 1D bullish MSB OTE FVG",
            "timestamp": "2026-05-28T00:00:00Z",
        },
        {
            "feed_id": "tg-1",
            "symbols": ["BTC/USDT"],
            "timeframes": ["1d"],
            "bias": "bullish",
            "structure_terms": ["MSB"],
            "zones": ["OTE", "FVG"],
            "liquidity_terms": [],
            "risk_terms": [],
        },
    )

    snapshot = build_social_research_snapshot(path)

    assert snapshot["archive_count"] == 1
    assert snapshot["doctrine"][0]["feed_id"] == "tg-1"
    assert snapshot["hypotheses"][0]["risk"] == "research_only"
    assert snapshot["research_only"] is True


def test_build_social_research_snapshot_empty_archive(tmp_path):
    from backend.social.reports import build_social_research_snapshot

    snapshot = build_social_research_snapshot(tmp_path / "missing.jsonl")

    assert snapshot == {
        "archive_count": 0,
        "doctrine": [],
        "hypotheses": [],
        "research_only": True,
    }
