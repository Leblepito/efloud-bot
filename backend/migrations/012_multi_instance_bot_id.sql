-- 012_multi_instance_bot_id.sql — Multi-instance persistence (Bot V2).
--
-- Background: a SECOND bot (V2, profile long, ~$1035 wallet) runs in parallel
-- with V1 (profile mid) on the same VPS and may share one Supabase project. Each
-- instance is identified by EFLOUD_BOT_ID (default 'v1'); backend.db threads it
-- into every write and instance-scoped read. Without this, V1's reconcile could
-- close a V2 trade row (record_trade_close), and the breaker_state SINGLETON
-- (migration 010, id=1) would clobber across bots.
--
-- This migration:
--   1. Adds bot_id TEXT NOT NULL DEFAULT 'v1' to trades / equity_history /
--      audit_log. The DEFAULT backfills every existing row to 'v1', so the
--      current single bot is unaffected (byte-identical reads/writes).
--   2. Converts breaker_state from the id=1 singleton to a per-instance table
--      keyed on bot_id (drops CHECK(id=1) + the id PK, adds a bot_id PK). The
--      existing row backfills to bot_id='v1'.
--   3. Adds bot_id-scoped indexes for the hot queries.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS, DROP CONSTRAINT IF EXISTS, guarded PK
-- add via a DO block. Safe to re-run; the runner records it in schema_migrations.

-- ── 1. bot_id on the append tables ────────────────────────────────
ALTER TABLE trades         ADD COLUMN IF NOT EXISTS bot_id TEXT NOT NULL DEFAULT 'v1';
ALTER TABLE equity_history ADD COLUMN IF NOT EXISTS bot_id TEXT NOT NULL DEFAULT 'v1';
ALTER TABLE audit_log      ADD COLUMN IF NOT EXISTS bot_id TEXT NOT NULL DEFAULT 'v1';

-- ── 2. breaker_state: singleton → per-instance ────────────────────
-- Add bot_id (backfills existing row to 'v1' via DEFAULT).
ALTER TABLE breaker_state ADD COLUMN IF NOT EXISTS bot_id TEXT NOT NULL DEFAULT 'v1';

-- Drop the old singleton guard + primary key (names follow Postgres defaults;
-- IF EXISTS keeps this safe on environments where they were never created).
ALTER TABLE breaker_state DROP CONSTRAINT IF EXISTS breaker_state_id_check;
ALTER TABLE breaker_state DROP CONSTRAINT IF EXISTS breaker_state_pkey;

-- Make the vestigial id column harmless (no longer unique; was PK DEFAULT 1).
-- Drop the DEFAULT too, so new per-instance rows read id=NULL rather than a
-- duplicated 1 (the column is dead; bot_id is the key).
ALTER TABLE breaker_state ALTER COLUMN id DROP NOT NULL;
ALTER TABLE breaker_state ALTER COLUMN id DROP DEFAULT;

-- Add the new primary key on bot_id (guarded — ADD CONSTRAINT has no IF NOT EXISTS).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.breaker_state'::regclass
          AND contype = 'p'
    ) THEN
        ALTER TABLE breaker_state ADD CONSTRAINT breaker_state_pkey PRIMARY KEY (bot_id);
    END IF;
END $$;

-- ── 3. bot_id-scoped indexes ──────────────────────────────────────
-- record_trade_close subquery: WHERE bot_id = $ AND closed_at IS NULL ... ORDER BY opened_at
CREATE INDEX IF NOT EXISTS idx_trades_bot_open
    ON trades (bot_id, opened_at DESC) WHERE closed_at IS NULL;
-- fetch_recent_trades / fetch_trades_since
CREATE INDEX IF NOT EXISTS idx_trades_bot_opened
    ON trades (bot_id, opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_equity_bot_ts
    ON equity_history (bot_id, ts DESC);

-- RLS stays enabled (deny-all for anon/authenticated; bot connects as superuser).
-- breaker_state already had RLS enabled in 010; the new columns inherit it.
ALTER TABLE public.breaker_state ENABLE ROW LEVEL SECURITY;
