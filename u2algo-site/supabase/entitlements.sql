-- entitlements: u2algo paid-access tracking (P-003 W2 / T-015)
-- Run in Supabase SQL Editor for the same project as waitlist_leads.
-- Service-role-only write (RLS enforced).
-- UR-003 eki: expires_at timestamptz NULL (abonelik/sepet opsiyonelliği)

create table if not exists public.entitlements (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  product text not null,                           -- 'wave1-premium', 'wave1-pro', vb.
  status text not null default 'pending',          -- pending | granted | revoked | expired
  source text not null default 'manual',           -- lemonsqueezy | manual | migration
  tv_username text,                                -- TradingView kullanıcı adı (grant sonrası)
  order_ref text,                                  -- Lemon Squeezy order ID (unique)
  granted_at timestamptz,
  expires_at timestamptz,                          -- NULL = lifetime; abonelikse T-016 event handler doldurur
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint entitlements_order_ref_key unique (order_ref),
  constraint entitlements_status_check check (status in ('pending', 'granted', 'revoked', 'expired'))
);

-- Index for customer lookup
create index if not exists idx_entitlements_email on public.entitlements (email);
create index if not exists idx_entitlements_status on public.entitlements (status);
create index if not exists idx_entitlements_product on public.entitlements (product);

-- updated_at trigger (reuse existing function)
drop trigger if exists entitlements_set_updated_at on public.entitlements;
create trigger entitlements_set_updated_at
  before update on public.entitlements
  for each row execute function public.set_updated_at();

-- RLS: service-role-only. Enable RLS and create NO permissive policy.
-- The service_role key (SUPABASE_SERVICE_ROLE_KEY, backend-only) BYPASSES RLS,
-- so it keeps full access. With RLS enabled and zero policies, anon/authenticated
-- are default-DENIED (cannot SELECT/INSERT/UPDATE/DELETE) — matching the bot-table
-- security pattern (trades/equity_history/breaker_state) in this project.
-- DO NOT add a `for all using(true)` policy: with no `to <role>` clause it applies
-- to PUBLIC (anon+authenticated) and grants them full access — a security hole that
-- defeats service-role-only. Verified via Supabase security advisor (entitlements
-- shows only INFO `rls_enabled_no_policy`, never WARN `rls_policy_always_true`).
alter table public.entitlements enable row level security;
