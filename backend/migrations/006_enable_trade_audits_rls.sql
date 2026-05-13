-- 006_enable_trade_audits_rls.sql — Retrofit RLS on public.trade_audits.
--
-- Migration 004 enabled RLS on public.trades / equity_history / audit_log /
-- schema_migrations on 2026-05-07. trade_audits was created in 005 AFTER
-- 004 ran, so it never went through the RLS lockdown. Supabase advisor
-- re-flagged this on 2026-05-13: with RLS disabled, anyone holding the
-- anon key can read or modify every audit row.
--
-- Same pattern as 004:
--   - Bot connects via DATABASE_URL with the postgres superuser role,
--     which bypasses RLS automatically. Bot operation unaffected.
--   - Empty policy list + RLS enabled = deny-all for non-superuser roles,
--     which is exactly what we want for a backend-only table.
--   - Idempotent: ALTER ENABLE ROW LEVEL SECURITY is no-op when already
--     enabled.
--
-- Guarded so the migration succeeds in fresh environments where the
-- table doesn't yet exist (the runner applies migrations in order, so
-- 005 will have created it — but defensive in case of partial state).

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'trade_audits'
    ) THEN
        EXECUTE 'ALTER TABLE public.trade_audits ENABLE ROW LEVEL SECURITY';
    END IF;
END
$$;
