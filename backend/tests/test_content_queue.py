"""
Content Approval Queue — hermetic unit tests.
DB testleri mock'lanır (gerçek Supabase dokunulmaz).
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.social.content_queue import (
    ComplianceGateError,
    ContentQueueError,
    ContentStatus,
    InvalidTransitionError,
    approve_draft,
    create_draft,
    make_draft_id,
    mark_failed,
    mark_sent,
    reject_draft,
    revise_rejected,
    submit_for_review,
    validate_draft,
)
from backend.social import queue_storage


# --------------------------------------------------------------------------- #
# Pure: content_queue.py
# --------------------------------------------------------------------------- #

def test_make_draft_id_length():
    assert len(make_draft_id()) >= 16


def test_make_draft_id_unique():
    ids = {make_draft_id() for _ in range(1000)}
    assert len(ids) == 1000


def test_validate_draft_ok():
    validate_draft("hello world", "en", "signal")


def test_validate_draft_empty_body():
    with pytest.raises(ContentQueueError, match="boş"):
        validate_draft("", "en", "signal")
    with pytest.raises(ContentQueueError, match="boş"):
        validate_draft("   ", "en", "signal")


def test_validate_draft_too_long():
    with pytest.raises(ContentQueueError, match="çok uzun"):
        validate_draft("x" * 4001, "en", "signal")


def test_validate_draft_unsupported_lang():
    with pytest.raises(ContentQueueError, match="desteklenmeyen lang"):
        validate_draft("ok", "fr", "signal")


def test_validate_draft_unsupported_type():
    with pytest.raises(ContentQueueError, match="desteklenmeyen post_type"):
        validate_draft("ok", "en", "meme")


def test_create_draft_defaults():
    d = create_draft(
        "BTC update incoming", "en", "signal",
        {"side": "long", "entry": 65000},
    )
    assert d.status == ContentStatus.DRAFT
    assert d.lang == "en"
    assert d.post_type == "signal"
    assert d.meta["side"] == "long"
    assert isinstance(d.created_at, datetime)
    assert d.draft_id and len(d.draft_id) >= 16


def test_create_draft_strips_body():
    d = create_draft("  hello  ", "en", "signal")
    assert d.body == "hello"


def test_submit_for_review_compliance_ok():
    d = create_draft("ok body", "en", "educational")
    report = {"violation_count": 0, "violations": []}
    submit_for_review(d, report)
    assert d.status == ContentStatus.PENDING_REVIEW
    assert d.compliance_report == report


def test_submit_for_review_compliance_fail():
    d = create_draft("ok body", "en", "promo")
    report = {"violation_count": 2, "violations": ["guaranteed profit", "$39"]}
    with pytest.raises(ComplianceGateError, match="2 violations"):
        submit_for_review(d, report)


def test_submit_for_review_invalid_transition():
    d = create_draft("ok body", "en", "educational")
    report = {"violation_count": 0}
    submit_for_review(d, report)
    with pytest.raises(InvalidTransitionError):
        submit_for_review(d, report)


def test_approve_draft_happy_path():
    d = create_draft("ok body", "tr", "signal")
    submit_for_review(d, {"violation_count": 0})
    approve_draft(d, reviewer_id="utku")
    assert d.status == ContentStatus.APPROVED
    assert d.reviewer_id == "utku"
    assert d.reviewed_at is not None


def test_reject_draft_from_pending():
    d = create_draft("ok body", "tr", "promo")
    submit_for_review(d, {"violation_count": 0})
    reject_draft(d, reviewer_id="utku", reason="çok ajitatif")
    assert d.status == ContentStatus.REJECTED
    assert d.rejection_reason == "çok ajitatif"


def test_reject_draft_from_approved():
    d = create_draft("ok body", "tr", "promo")
    submit_for_review(d, {"violation_count": 0})
    approve_draft(d, "utku")
    reject_draft(d, "utku", "revize gerekli")
    assert d.status == ContentStatus.REJECTED


def test_reject_draft_from_draft_fails():
    d = create_draft("ok body", "tr", "promo")
    with pytest.raises(InvalidTransitionError):
        reject_draft(d, "utku", "reason")


def test_mark_sent_terminal_state():
    d = create_draft("ok body", "en", "signal")
    submit_for_review(d, {"violation_count": 0})
    approve_draft(d, "utku")
    mark_sent(d)
    assert d.status == ContentStatus.SENT


def test_mark_failed_from_approved():
    d = create_draft("ok body", "en", "signal")
    submit_for_review(d, {"violation_count": 0})
    approve_draft(d, "utku")
    mark_failed(d, "xurl subprocess timeout")
    assert d.status == ContentStatus.FAILED
    assert d.rejection_reason == "xurl subprocess timeout"


def test_revise_rejected_clears_compliance():
    d = create_draft("ok body", "en", "signal")
    submit_for_review(d, {"violation_count": 0})
    reject_draft(d, "utku", "iyileştir")
    revise_rejected(d, "yeni ve daha temiz body")
    assert d.status == ContentStatus.DRAFT
    assert d.body == "yeni ve daha temiz body"
    assert d.compliance_report is None
    assert d.reviewer_id is None


def test_revise_failed_to_draft():
    d = create_draft("ok body", "en", "signal")
    submit_for_review(d, {"violation_count": 0})
    approve_draft(d, "utku")
    mark_failed(d, "network error")
    revise_rejected(d, "tekrar dene")
    assert d.status == ContentStatus.DRAFT


def test_revise_rejected_empty_body_fails():
    d = create_draft("ok body", "en", "signal")
    submit_for_review(d, {"violation_count": 0})
    reject_draft(d, "utku", "x")
    with pytest.raises(ContentQueueError, match="boş"):
        revise_rejected(d, "   ")


def test_draft_to_dict_roundtrip():
    d = create_draft("ok body", "all", "market_update", {"chart_url": "https://..."})
    d_dict = d.to_dict()
    assert d_dict["lang"] == "all"
    assert d_dict["meta"]["chart_url"] == "https://..."
    # JSON-serializable
    json.dumps(d_dict)


# --------------------------------------------------------------------------- #
# Storage: queue_storage.py (mocked asyncpg.Pool)
# --------------------------------------------------------------------------- #

def _fake_pool_with_conn():
    """asyncpg.Pool mock: acquire() → conn context manager."""
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None
    return pool, conn


@pytest.mark.asyncio
async def test_ensure_schema_runs_ddl():
    pool, conn = _fake_pool_with_conn()
    await queue_storage.ensure_schema(pool)
    conn.execute.assert_called_once()
    ddl = conn.execute.call_args[0][0]
    assert "CREATE TABLE IF NOT EXISTS content_drafts" in ddl


@pytest.mark.asyncio
async def test_save_draft_upsert():
    pool, conn = _fake_pool_with_conn()
    d = create_draft("ok body", "en", "signal", {"side": "long"})
    await queue_storage.save_draft(pool, d)
    conn.execute.assert_called_once()
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO content_drafts" in sql
    assert "ON CONFLICT (draft_id) DO UPDATE" in sql


@pytest.mark.asyncio
async def test_load_draft_found():
    pool, conn = _fake_pool_with_conn()
    conn.fetchrow.return_value = {
        "draft_id": "abc123",
        "body": "ok",
        "lang": "en",
        "post_type": "signal",
        "meta": json.dumps({"k": "v"}),
        "status": "draft",
        "created_at": datetime.now(timezone.utc),
        "reviewed_at": None,
        "reviewer_id": None,
        "rejection_reason": None,
        "compliance_report": None,
    }
    result = await queue_storage.load_draft(pool, "abc123")
    assert result is not None
    assert result.draft_id == "abc123"
    assert result.meta == {"k": "v"}


@pytest.mark.asyncio
async def test_load_draft_not_found():
    pool, conn = _fake_pool_with_conn()
    conn.fetchrow.return_value = None
    result = await queue_storage.load_draft(pool, "missing")
    assert result is None


@pytest.mark.asyncio
async def test_list_by_status():
    pool, conn = _fake_pool_with_conn()
    conn.fetch.return_value = []
    result = await queue_storage.list_by_status(pool, ContentStatus.PENDING_REVIEW, limit=10)
    assert result == []
    sql = conn.fetch.call_args[0][0]
    assert "WHERE status = $1" in sql
    assert "LIMIT $2" in sql


@pytest.mark.asyncio
async def test_count_by_status():
    pool, conn = _fake_pool_with_conn()
    conn.fetch.return_value = [
        {"status": "draft", "c": 5},
        {"status": "pending_review", "c": 2},
    ]
    result = await queue_storage.count_by_status(pool)
    assert result == {"draft": 5, "pending_review": 2}


@pytest.mark.asyncio
async def test_save_draft_passes_serialized_meta():
    # B-2 fix (2026-07-17): asyncpg pozisyonel — meta artık 5. pozisyonel arg.
    # (Eski hali call_args.kwargs["meta"] okuyordu; o API gerçek asyncpg'de
    # TypeError'dı, mock yüzünden kaçmıştı.)
    pool, conn = _fake_pool_with_conn()
    d = create_draft("ok", "tr", "signal", {"nested": {"deep": 1, "list": [1, 2, 3]}})
    await queue_storage.save_draft(pool, d)
    args, kwargs = conn.execute.call_args
    assert kwargs == {}
    meta_arg = args[5]
    assert isinstance(meta_arg, str)
    parsed = json.loads(meta_arg)
    assert parsed["nested"]["deep"] == 1
    assert parsed["nested"]["list"] == [1, 2, 3]


# ── B-2 (2026-07-17): save_draft pozisyonel asyncpg args ────────────────────

@pytest.mark.asyncio
async def test_save_draft_uses_positional_args_not_named_kwargs():
    """`$(name)` + execute(**kwargs) gerçek asyncpg'de TypeError'dı; testler
    AsyncMock'la geçtiği için kaçmıştı. Artık execute pozisyonel $1..$11
    almalı ve named kwargs GEÇMEMELİ."""
    from backend.social.queue_storage import save_draft

    draft = create_draft("hi", "en", "promo")

    pool, conn = _fake_pool_with_conn()
    await save_draft(pool, draft)

    conn.execute.assert_awaited_once()
    args, kwargs = conn.execute.call_args
    # named kwargs (draft_id=…) OLMAMALI — asyncpg positional-only
    assert kwargs == {}
    # SQL + 11 pozisyonel değer
    assert len(args) == 12
    sql = args[0]
    assert "$1" in sql and "$11" in sql
    assert "$(draft_id)" not in sql
    assert args[1] == draft.draft_id  # ilk pozisyonel = draft_id
