-- 004_enable_rls.sql — Lock down public tables to direct-DB role only.
--
-- Critical security fix: tables were exposed to anon and authenticated roles
-- (Supabase advisor warning, 2026-05-07). With RLS disabled, anyone holding
-- the anon key could read or modify trades, equity history, audit log, etc.
--
-- Bot connects via DATABASE_URL with the postgres superuser role, which
-- bypasses RLS automatically — so this change does NOT affect bot operation.
-- It only blocks anon/authenticated client access (which we never use here).
--
-- Idempotent: ALTER ENABLE ROW LEVEL SECURITY is no-op when already enabled.
-- No policies added on purpose: empty policy list + RLS enabled = deny-all
-- for non-superuser roles, which is what we want.

ALTER TABLE public.trades            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.equity_history    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;

-- breaker_state lives in Supabase but is not (yet) in repo migrations.
-- Guard with conditional so the migration succeeds in fresh environments
-- where this table doesn't exist.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'breaker_state'
    ) THEN
        EXECUTE 'ALTER TABLE public.breaker_state ENABLE ROW LEVEL SECURITY';
    END IF;
END
$$;
