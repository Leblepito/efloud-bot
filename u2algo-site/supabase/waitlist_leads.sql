-- u2algo public site waitlist table
-- Run in Supabase SQL Editor for the Supabase project used by Railway variables.

create extension if not exists pgcrypto;

create table if not exists public.waitlist_leads (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  source text not null default 'u2algo-site',
  user_agent text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists waitlist_leads_set_updated_at on public.waitlist_leads;
create trigger waitlist_leads_set_updated_at
before update on public.waitlist_leads
for each row execute function public.set_updated_at();

alter table public.waitlist_leads enable row level security;

-- No public SELECT/INSERT policy is required because the Railway backend writes
-- with SUPABASE_SERVICE_ROLE_KEY. Keep browser clients away from direct table access.
