-- Migration: waitlist_leads consent tracking (P-003 W0 / T-011)
-- Adds KVKK/GDPR consent fields. Existing rows get consent=NULL (retroaktif varsayım yok).
-- Run AFTER entitlements table is created.

alter table public.waitlist_leads
  add column if not exists consent boolean default null,
  add column if not exists consent_at timestamptz default null;

comment on column public.waitlist_leads.consent is 'KVKK/GDPR marketing consent — null for pre-migration records';
comment on column public.waitlist_leads.consent_at is 'Timestamp when consent was given';
