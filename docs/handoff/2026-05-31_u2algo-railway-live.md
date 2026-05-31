# u2algo Railway live deploy handoff — 2026-05-31

## What is live

Public landing service is deployed on Railway project `perpetual-tenderness`, service `u2algo-site`.

Live Railway URL:

- https://u2algo-site-production.up.railway.app

Verified:

- `GET /healthz` -> 200 `{ ok: true, service: "u2algo-site" }`
- `GET /` -> 200 HTML
- content contains required compliance phrases: `yatırım tavsiyesi değildir`, `Risk bildirimi`, `DYOR`
- Railway deployment status: `SUCCESS`

## Files added/changed

Under `u2algo-site/`:

- `package.json` — Node/Nixpacks package, `start`, `smoke`, `build`, workspace compatibility.
- `package-lock.json` — locked Node deps.
- `server.js` — static file server + `/healthz` + waitlist API endpoints.
- `railway.json` — Railway deploy config, `/healthz` healthcheck.
- `nixpacks.toml` — Node 20 build, smoke test, start command.
- `scripts/smoke.js` — compliance/asset smoke gate.
- `web/package.json` — compatibility with old Railway service build command `npm run build --workspace=web`.
- `supabase/waitlist_leads.sql` — Supabase SQL table setup for waitlist.

## Important: custom domain not yet attached to new service

Current DNS/HTTP state:

- `u2algo.com` resolves to Railway edge but returns Railway fallback 404.
- `www.u2algo.com` CNAME points to an old Railway app and has SSL SNI/cert mismatch.
- New live service currently has only Railway domain: `u2algo-site-production.up.railway.app`.

Railway CLI custom domain mutation failed with:

```text
Unauthorized. Please run `railway login` again.
```

Read/deploy commands work, but `railway domain u2algo.com --service u2algo-site --port 3000` fails. Finish domain binding in Railway dashboard or after refreshing CLI auth.

Required Railway dashboard action:

1. Open project `perpetual-tenderness`.
2. Open service `u2algo-site`.
3. Settings -> Domains.
4. Add custom domain `u2algo.com` on port `3000`.
5. Add custom domain `www.u2algo.com` on port `3000`.
6. Apply Railway-provided DNS records in Manus/domain DNS manager.
7. Wait for SSL issuance.
8. Verify:
   - `https://u2algo.com/healthz` -> 200
   - `https://www.u2algo.com/healthz` -> 200
   - both hostnames show the u2algo landing page, no Railway fallback 404, no SNI mismatch.

## Waitlist backend status

Backend endpoints exist:

- `GET /api/waitlist/health`
- `POST /api/waitlist` with JSON `{ "email": "user@example.com" }`

Current status:

- Supabase env vars are present on Railway service `u2algo-site` via references:
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`
- `GET /api/waitlist/health` currently returns 503 because Supabase query is not ready/reachable.
- `POST /api/waitlist` currently returns 500 `waitlist_insert_failed`.

Required Supabase action:

Run this SQL in the Supabase SQL Editor for the project referenced by Railway env vars:

```sql
-- see u2algo-site/supabase/waitlist_leads.sql
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
```

After SQL, verify:

```bash
curl https://u2algo-site-production.up.railway.app/api/waitlist/health
curl -X POST https://u2algo-site-production.up.railway.app/api/waitlist \
  -H 'content-type: application/json' \
  -d '{"email":"test@example.com"}'
```

Expected:

- health -> 200 `{ "ok": true, "database": "ready" }`
- post -> 200 `{ "ok": true }`

## Safety notes

- No Hetzner VPS / live trading bot changes were made.
- No Binance/mainnet config was touched.
- The public site is separate from the trading execution infrastructure.
- The landing copy passed compliance smoke gate; it avoids profit guarantees and includes risk disclosures.
