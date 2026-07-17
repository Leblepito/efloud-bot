"""
Content Queue persistence — Supabase asyncpg pool.

Tablo: content_drafts (migration 009 ile oluşacak).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from .content_queue import ContentDraft, ContentStatus

logger = logging.getLogger(__name__)


_DDL = """
CREATE TABLE IF NOT EXISTS content_drafts (
    draft_id        TEXT PRIMARY KEY,
    body            TEXT NOT NULL,
    lang            TEXT NOT NULL,
    post_type       TEXT NOT NULL,
    meta            JSONB NOT NULL DEFAULT '{}'::jsonb,
    status          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at     TIMESTAMPTZ,
    reviewer_id     TEXT,
    rejection_reason TEXT,
    compliance_report JSONB
);
CREATE INDEX IF NOT EXISTS idx_content_drafts_status ON content_drafts(status);
CREATE INDEX IF NOT EXISTS idx_content_drafts_lang_type ON content_drafts(lang, post_type);
CREATE INDEX IF NOT EXISTS idx_content_drafts_created_at ON content_drafts(created_at DESC);
"""


async def ensure_schema(pool: asyncpg.Pool) -> None:
    """Migration 009 — content_drafts tablosunu oluştur (idempotent)."""
    async with pool.acquire() as conn:
        await conn.execute(_DDL)


def _row_to_draft(row: asyncpg.Record) -> ContentDraft:
    """DB row → ContentDraft."""
    meta = row["meta"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    compliance = row["compliance_report"]
    if isinstance(compliance, str):
        compliance = json.loads(compliance)
    return ContentDraft(
        draft_id=row["draft_id"],
        body=row["body"],
        lang=row["lang"],
        post_type=row["post_type"],
        meta=meta or {},
        status=ContentStatus(row["status"]),
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
        reviewer_id=row["reviewer_id"],
        rejection_reason=row["rejection_reason"],
        compliance_report=compliance,
    )


def _draft_to_params(draft: ContentDraft) -> dict[str, Any]:
    """ContentDraft → INSERT params."""
    return {
        "draft_id": draft.draft_id,
        "body": draft.body,
        "lang": draft.lang,
        "post_type": draft.post_type,
        "meta": json.dumps(draft.meta),
        "status": draft.status.value,
        "created_at": draft.created_at,
        "reviewed_at": draft.reviewed_at,
        "reviewer_id": draft.reviewer_id,
        "rejection_reason": draft.rejection_reason,
        "compliance_report": json.dumps(draft.compliance_report) if draft.compliance_report else None,
    }


async def save_draft(pool: asyncpg.Pool, draft: ContentDraft) -> None:
    """UPSERT (varsa güncelle, yoksa ekle).

    B-2 fix (2026-07-17): pozisyonel $1..$11 — `$(name)` placeholder sözdizimi
    asyncpg/Postgres'te yok ve `conn.execute(**params)` da geçersiz (execute
    positional-only *args alır). Gerçek DB'ye her yazım TypeError'dı (testler
    AsyncMock'la geçiyordu): approve/reject endpoint'leri 500 dönüyor, publish
    sonrası status persist edilemeyince aynı draft 60 sn'de bir YENİDEN
    yayınlanıyordu (duplicate post).
    """
    p = _draft_to_params(draft)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO content_drafts (
                draft_id, body, lang, post_type, meta, status,
                created_at, reviewed_at, reviewer_id, rejection_reason, compliance_report
            ) VALUES (
                $1, $2, $3, $4, $5::jsonb, $6,
                $7, $8, $9, $10, $11::jsonb
            )
            ON CONFLICT (draft_id) DO UPDATE SET
                body = EXCLUDED.body,
                lang = EXCLUDED.lang,
                post_type = EXCLUDED.post_type,
                meta = EXCLUDED.meta,
                status = EXCLUDED.status,
                reviewed_at = EXCLUDED.reviewed_at,
                reviewer_id = EXCLUDED.reviewer_id,
                rejection_reason = EXCLUDED.rejection_reason,
                compliance_report = EXCLUDED.compliance_report
            """,
            p["draft_id"], p["body"], p["lang"], p["post_type"], p["meta"],
            p["status"], p["created_at"], p["reviewed_at"], p["reviewer_id"],
            p["rejection_reason"], p["compliance_report"],
        )


async def load_draft(pool: asyncpg.Pool, draft_id: str) -> ContentDraft | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM content_drafts WHERE draft_id = $1", draft_id
        )
    return _row_to_draft(row) if row else None


async def list_by_status(
    pool: asyncpg.Pool, status: ContentStatus, limit: int = 50
) -> list[ContentDraft]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM content_drafts WHERE status = $1 ORDER BY created_at DESC LIMIT $2",
            status.value, limit,
        )
    return [_row_to_draft(r) for r in rows]


async def count_by_status(pool: asyncpg.Pool) -> dict[str, int]:
    """SCOREBOARD / metrics için."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT status, COUNT(*) AS c FROM content_drafts GROUP BY status"
        )
    return {r["status"]: int(r["c"]) for r in rows}
