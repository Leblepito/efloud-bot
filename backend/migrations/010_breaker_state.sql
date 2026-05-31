-- 010_breaker_state.sql — Circuit-breaker halt-state mirror table.
--
-- Background: migration 004 had to guard `ALTER TABLE public.breaker_state
-- ENABLE ROW LEVEL SECURITY` with an IF EXISTS conditional, because the table
-- lived in Supabase (created out-of-band) but was never defined in repo
-- migrations. Fresh environments (the 2026-05-15 VPS rebuild) therefore came up
-- WITHOUT the table at all. This migration closes that gap: it creates the
-- table idempotently so every environment — fresh or existing — converges on
-- the same schema, and 004's conditional guard becomes a no-op rather than a
-- silent skip.
--
-- Role of this table: a best-effort SUMMARY MIRROR of the circuit breaker. The
-- file-based StateStore (state/breaker.json) remains the PRIMARY, full-fidelity
-- persistence used on restart. This row exists so the halt status survives a
-- total loss of the state volume and is queryable for observability/alerting.
-- Written by backend.db.Database.upsert_breaker_state on every breaker change.
--
-- Singleton: a single logical breaker → one row pinned at id = 1
-- (CHECK keeps it that way; the writer UPSERTs ON CONFLICT (id)).
--
-- Idempotent: CREATE TABLE / INDEX IF NOT EXISTS. The runner records the
-- version in schema_migrations so it is applied once, but re-running is safe.

CREATE TABLE IF NOT EXISTS breaker_state (
    id            SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    daily_loss    NUMERIC,                 -- daily PnL %, nullable (unknown while tripped)
    weekly_loss   NUMERIC,                 -- weekly drawdown %, nullable
    halted        BOOLEAN NOT NULL DEFAULT FALSE,
    halted_reason TEXT,                    -- populated while TRIPPED/HALTED, else NULL
    halted_at     TIMESTAMPTZ,             -- when the breaker tripped/halted
    reset_at      TIMESTAMPTZ,             -- cooldown resume time (TRIPPED), else NULL
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_breaker_state_updated_at ON breaker_state (updated_at DESC);

-- RLS lockdown — same deny-all pattern as 004/006.
--   - Bot connects via DATABASE_URL with the postgres superuser role, which
--     bypasses RLS automatically. Bot operation unaffected.
--   - Empty policy list + RLS enabled = deny-all for anon/authenticated roles,
--     which is exactly what we want for a backend-only table.
--   - Idempotent: ALTER ENABLE ROW LEVEL SECURITY is a no-op when already
--     enabled (e.g. an environment where 004's conditional already ran).
ALTER TABLE public.breaker_state ENABLE ROW LEVEL SECURITY;
