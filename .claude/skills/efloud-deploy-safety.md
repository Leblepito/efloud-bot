---
name: efloud-deploy-safety
description: Deploy guardrails for efloud-bot on Hetzner / docker-compose.prod.yml. Use whenever a deploy, restart, env change, or migration is being planned or executed. NEVER run production commands without Hermes/Utku approval.
---

# efloud-deploy-safety

Production runs on Hetzner with `docker-compose.prod.yml`. Real money. Treat
every deploy as irreversible until proven safe.

## Pre-flight (before any production action)

- [ ] Change merged to main via PR? (no direct production edits)
- [ ] `efloud-risk-ops-reviewer` PASS verdict on the PR?
- [ ] Hermes/Utku approval recorded in PR thread?
- [ ] Backup of current state taken? (`/state/`, `/logs/`, DB snapshot)

## Compose env changes (CRITICAL)

If you changed `docker-compose.prod.yml` env vars, `.env`, or any service config:

```bash
# WRONG — does NOT pick up env changes
docker restart efloud-bot

# RIGHT — recreates container with new env
docker compose -f docker-compose.prod.yml up -d
```

Verify:
```bash
docker exec efloud-bot env | grep -E '^(EFLOUD|BINANCE)_' | sed 's/=.*/=***/'
```

## Database migrations

New `.sql` file or `backend/migrate.py` change:

```bash
docker exec efloud-bot python3 -m backend.migrate up
```

- Capture stdout + stderr to a log line in the deploy thread.
- If a step fails: STOP. Do not retry blindly. Investigate.
- Rollback plan: previous migration version + DB snapshot timestamp.

## Secrets

- API keys, Telegram tokens, DB URLs live in `.env` — **never** in repo.
- `.gitignore` already excludes `.env`, `.env.local`, `*.key`, `*.pem`.
- `.env.example` is the only env template that ships in the repo.
- `EFLOUD_ALLOW_MAINNET=1` is set **only** on the production VPS, **only** with
  explicit human intent. Never propose flipping this from a Claude session.

## Post-deploy verification

```bash
# Container healthy?
docker compose -f docker-compose.prod.yml ps
docker logs --tail 200 efloud-bot

# HTTP health endpoint?
curl -fsS http://localhost:8080/healthz

# First reconcile cycle complete?
docker logs efloud-bot 2>&1 | grep -E '(reconcile|cycle)' | tail -20

# Open positions match exchange?
# (manual cross-check via Binance UI + /api/positions)
```

If any of the above fails → roll back:
```bash
docker compose -f docker-compose.prod.yml down
git checkout <previous-known-good-tag>
docker compose -f docker-compose.prod.yml up -d
```

## Hard rules
- **Never** run `docker exec ... -- rm`, `docker volume rm`, `git reset --hard origin/main`
  on the production server from a Claude session.
- **Never** flip `dry_run` to `false` or `EFLOUD_ALLOW_MAINNET` to `1` unilaterally.
- **Never** suppress pre-commit / pre-push hooks (`--no-verify`).
- If `docker compose up -d` says "no changes detected" but you changed `.env` —
  use `--force-recreate efloud-bot` (still requires approval).
