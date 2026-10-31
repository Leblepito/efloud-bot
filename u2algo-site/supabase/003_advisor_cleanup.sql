-- 003_advisor_cleanup.sql — Supabase security-advisor cleanup (2026-06-17)
-- Applied live to project kjaicqpqfwnfbioofdib via MCP apply_migration
-- (advisor_cleanup_revoke_event_trigger_exec_and_pin_search_path). Tracked here
-- for repo↔DB parity / re-provisioning. Idempotent. Zero functional impact.

-- (1) rls_auto_enable() is an EVENT TRIGGER function (auto-enables RLS on new
--     public tables — the reason every table has RLS on). PostgreSQL refuses ALL
--     direct calls ("trigger functions can only be called as triggers", verified
--     live), so the anon/authenticated EXECUTE grant was meaningless and NOT
--     exploitable. The event trigger fires via the DDL-event machinery, not via
--     EXECUTE-granted calls, so revoking EXECUTE does NOT affect auto-RLS (verified:
--     a table created after the revoke still had RLS auto-enabled). Clears advisor
--     WARN anon_security_definer_function_executable / authenticated_*.
revoke execute on function public.rls_auto_enable() from public, anon, authenticated;

-- (2) set_updated_at(): pin search_path. Body only uses now() (pg_catalog, always
--     resolvable) + NEW record fields, so '' is safe. Clears function_search_path_mutable.
alter function public.set_updated_at() set search_path = '';

-- (3) waitlist_leads "Allow public insert" WITH CHECK (true): INTENTIONAL — the
--     public signup form requires anon INSERT. Left UNCHANGED by design (tightening
--     it would break live signup). Accepted advisor WARN rls_policy_always_true.
--     No DDL here; documented for the record.
