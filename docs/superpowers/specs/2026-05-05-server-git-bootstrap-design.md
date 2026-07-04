# Server Git Bootstrap — Design

**Date:** 2026-05-05
**Topic:** Convert `/opt/efloud-bot` on the production Hetzner server into a git-tracked clone of the `Leblepito/efloud-bot` master branch, so future deploys can use the existing `deploy/deploy.sh` flow as designed.
**Scope:** One-time infrastructure fix. NOT a feature, NOT recurring work.

## Context

### Why this is needed

The Hetzner production server (<VPS_IP>, `bot.ualgotrade.com`) hosts the live trading bot at `/opt/efloud-bot`. Inspection on 2026-05-05 revealed:

- Files exist at `/opt/efloud-bot` (mtime 2 May 2026), owned by `efloud:efloud`
- The directory is **NOT a git repository** (`fatal: not a git repository`)
- The repo includes `deploy/deploy.sh` whose first line is `git fetch origin && git checkout master && git pull --ff-only origin master` — meaning the **intended** deploy flow is git-based
- The repo also includes `deploy/setup-server.sh` line 56: `git clone <REPO_URL> /opt/efloud-bot` — the documented bootstrap
- Either the original deploy bypassed `git clone` (manual scp/rsync of files), or git history was deleted post-deploy

Result: the server cannot run `bash deploy/deploy.sh` as-is. Any future code change requires manual file transfer + container rebuild, which is fragile, error-prone, and breaks the source-of-truth assumption (server should match origin/master exactly).

### Triggering event

A small fix to `engine/safety/position_guard.py` (epsilon `1e-6` → `1e-2`) was merged to `origin/master` at commit `78680b0`. Deploying it requires getting that commit onto the server. Doing it via scp is a one-off; doing it via the documented `git pull` flow requires the server to be a git repo. Bootstrapping the git repo is the right one-time fix.

### Goal

After this work:
- `/opt/efloud-bot` is a git repo aligned with `origin/master`
- All tracked files match the repo content
- Untracked files (`.env.production` with secrets, runtime state directories) are preserved
- `deploy/deploy.sh` works as documented for all future deploys
- No data loss, minimal downtime (~30s for docker rebuild)

## Architecture

Three-stage one-shot bootstrap:

1. **Backup stage** — copy `.env.production` to `/tmp/.env.production.bak.YYYYMMDD-HHMMSS` (paranoia guard, even though git reset shouldn't touch it)
2. **Git bootstrap stage** — initialize git, set remote, fetch, hard-reset to origin/master, restore ownership
3. **Deploy stage** — run the standard `deploy/deploy.sh` (which itself does git fetch + pull + docker compose build + up + healthcheck)

Stage 1 protects against unexpected file overwrites. Stage 2 aligns source. Stage 3 is the standard flow that will be used for all future deploys.

## Implementation steps

Run as `root` on the production server (`ssh root@<VPS_IP>`):

```bash
set -e

# Stage 1: Backup
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
cp /opt/efloud-bot/.env.production /tmp/env.production.bak.${TIMESTAMP}
echo "Backup: /tmp/env.production.bak.${TIMESTAMP}"

# Stage 2: Git bootstrap
cd /opt/efloud-bot
git init -b master
git remote add origin https://github.com/Leblepito/efloud-bot.git
git fetch --depth=50 origin master    # shallow fetch — full history not needed for deploy
git reset --hard origin/master
git log --oneline -1                  # inline confirmation: should show 78680b0 fix(safety): widen FP epsilon...
chown -R efloud:efloud /opt/efloud-bot

# Stage 3: Deploy
sudo -u efloud bash deploy/deploy.sh
```

Verification after stage 3:

```bash
ssh root@<VPS_IP> "cd /opt/efloud-bot && git log --oneline -3 && grep -n '+ 1e-2\|+ 1e-6' engine/safety/position_guard.py"
curl -sI https://bot.ualgotrade.com/healthz   # expect HTTP/2 200
ssh root@<VPS_IP> "docker ps --format 'table {{.Names}}\t{{.Status}}' && docker logs --tail 30 efloud-bot 2>&1 | grep -E 'cycle|breaker|Watchlist'"
```

## Components

### What gets touched

| Path on server | Before | After | Mechanism |
|----------------|--------|-------|-----------|
| `/opt/efloud-bot/.git/` | absent | present, master @ 78680b0 | `git init`, `git fetch` |
| `/opt/efloud-bot/engine/safety/position_guard.py` | epsilon 1e-6 | epsilon 1e-2 | `git reset --hard origin/master` |
| `/opt/efloud-bot/.env.production` | secrets (unchanged) | secrets (unchanged) | Untracked → reset --hard does not touch |
| `/opt/efloud-bot/state_1k/`, `logs/` | runtime data | runtime data | Untracked OR docker volume — preserved |
| Docker image `efloud-bot:latest` | built from old source | rebuilt from new source | `docker compose build` inside `deploy.sh` |
| Container `efloud-bot` | running on old image | running on new image, ~30s restart | `docker compose up -d` inside `deploy.sh` |
| Container `efloud-caddy` | running | running, untouched | Not part of `deploy.sh` |

### What does NOT change

- `.env.production` content (secrets stay)
- Runtime state (positions, equity history, audit log) — Supabase persistence handles this; restart restores from there
- Open Binance positions — protected by exchange-side SL/TP orders (placed via `OrderManager.place_oco` at position open time)
- Caddy reverse proxy and TLS certificates — separate container, not redeployed
- Server firewall, fail2ban, system packages — not in scope

## Data flow

```
[GitHub origin/master @ 78680b0]
        │
        │ git fetch + reset --hard
        ▼
[/opt/efloud-bot tracked files] ──── (preserved: .env.production, runtime dirs)
        │
        │ docker compose build
        ▼
[efloud-bot:latest image]
        │
        │ docker compose up -d
        ▼
[efloud-bot container running]
        │
        │ healthcheck via docker exec
        ▼
[200 OK on /healthz → success]
```

## Error handling

| Failure point | Symptom | Recovery |
|---------------|---------|----------|
| `git fetch` fails (network/auth) | Stage 2 exits non-zero, server unchanged | Investigate network/SSH; rerun |
| `.env.production` accidentally deleted | (unlikely; reset --hard does not touch untracked) | Restore from `/tmp/env.production.bak.*` |
| `docker compose build` fails | `deploy.sh` exits 1; old container keeps running | Read logs, fix issue, rerun deploy |
| `docker compose up -d` fails to start new container | Old container still running | Manual rollback: `docker compose up -d --no-build` (uses prior image) |
| Healthcheck fails after restart | `deploy.sh` prints last 80 log lines and exits 1 | Investigate logs; rollback by checking out previous commit + redeploy |
| Bot opens unexpected positions on restart | Reconciliation log on startup says "Found N saved positions — reconcile with exchange recommended" | Bot's startup reconciliation matches Supabase records against live Binance positions |

## Testing / validation

### Pre-deploy

- Confirm `origin/master` HEAD is `78680b0` (already pushed): `git ls-remote https://github.com/Leblepito/efloud-bot master`
- Confirm SSH access to `root@<VPS_IP>` works
- Confirm Phase A backtest is NOT running on the production server (it runs on the dev worktree, not production — verified)

### Post-deploy

- `git log --oneline -3` on server matches `origin/master`
- `grep '+ 1e-2' engine/safety/position_guard.py` returns the new line (and `1e-6` returns nothing)
- `https://bot.ualgotrade.com/healthz` returns 200
- `docker ps` shows `efloud-bot` status `Up X seconds (healthy)` after ~40s health-check warmup
- Container logs show:
  - `🚀 Bot runner started` or equivalent boot message
  - `Watchlist (10): BTC/USDT, ETH/USDT, ...`
  - At least one cycle log within 60s

### Acceptance criteria

- All post-deploy checks pass
- No unexpected error logs in the first 5 minutes
- Bot resumes scanning + position management without manual intervention

## Risks

### Low probability, high impact

- **`.env.production` overwritten by reset --hard.** Probability: very low (file is untracked, git reset --hard does not touch untracked). Mitigation: stage 1 backup. Recovery: `cp /tmp/env.production.bak.* /opt/efloud-bot/.env.production` and rerun deploy.

- **Hot-patched files on server lost.** Probability: low (no documented hot-patches). Impact: if someone applied an undocumented fix on the server, it disappears. Mitigation: this is the desired behavior — server should match origin. If there are intentional server-only files, they should be in `.gitignore` or moved to a separate dir.

### Medium probability, low impact

- **Brief downtime (~30s for docker rebuild + healthcheck warmup).** Probability: certain. Impact: bot does not run cycles during this window. Mitigation: open positions are protected by Binance-side SL/TP orders.

- **Docker image rebuild takes longer than 30s.** Probability: medium (first build with new dependencies could be 3-5 min). Impact: longer downtime. Mitigation: image layers cache; only changed layers rebuild.

### Out of scope

- GitHub Actions CI/CD: deferred (Approach B in brainstorm). The user chose A explicitly. Future task if multiple servers or auto-deploy is wanted.
- Test environment / staging server: deferred. Bot is single-environment for now.
- Rollback automation: deferred. Manual rollback via `git checkout <previous-sha> && bash deploy/deploy.sh` is sufficient for solo developer.

## Out of scope

- Modifying `deploy/deploy.sh` or `deploy/setup-server.sh` — they already work as designed
- Adding tests for the bootstrap script — single-use, manual verification
- Documenting backup/restore strategy — covered by Supabase persistence (already configured)
- Server hardening — already done in `setup-server.sh` (UFW, fail2ban, non-root app user)

## Success metric

After running the bootstrap, the user can run `ssh root@<VPS_IP> "cd /opt/efloud-bot && bash deploy/deploy.sh"` from any future commit and have the live bot updated within ~30s. No manual file transfers, no scp.
