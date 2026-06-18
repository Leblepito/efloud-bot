-- Migration 009 — Content Approval Queue (P-002 M6 skeleton)
-- Operatör `python3 -m backend.migrate up` ile uygular.

CREATE TABLE IF NOT EXISTS content_drafts (
    draft_id        TEXT PRIMARY KEY,
    body            TEXT NOT NULL,
    lang            TEXT NOT NULL CHECK (lang IN ('en', 'tr', 'ru', 'kz', 'all')),
    post_type       TEXT NOT NULL CHECK (post_type IN ('signal', 'educational', 'performance_recap', 'promo', 'market_update')),
    meta            JSONB NOT NULL DEFAULT '{}'::jsonb,
    status          TEXT NOT NULL CHECK (status IN ('draft', 'pending_review', 'approved', 'rejected', 'sent', 'failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at     TIMESTAMPTZ,
    reviewer_id     TEXT,
    rejection_reason TEXT,
    compliance_report JSONB
);

CREATE INDEX IF NOT EXISTS idx_content_drafts_status ON content_drafts(status);
CREATE INDEX IF NOT EXISTS idx_content_drafts_lang_type ON content_drafts(lang, post_type);
CREATE INDEX IF NOT EXISTS idx_content_drafts_created_at ON content_drafts(created_at DESC);
