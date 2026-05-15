# VPS Rebuild Redeploy Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore efloud-bot production service on the fresh Hetzner VPS (`efloud-bot-prod`, 178.104.122.91) after the 2026-05-15 disk wipe, deploying master `855bb87` (overseer + healthz fix + all 4 overseer bug fixes), and leave the bot in a safe `EFLOUD_AUTOSTART=0` state for operator-controlled startup.

**Architecture:** SSH-driven deploy from the local Windows machine into the empty VPS. The repo already ships `deploy/setup-server.sh` (Docker + UFW + fail2ban + efloud user) and `deploy/deploy.sh` (git pull + compose build + up + healthz wait). Plan reuses both scripts; new work is limited to wiring the production `.env.production` file (lives only locally today as `.env`) and verifying the post-deploy state including the new overseer sidecar container.

**Tech Stack:** SSH, Hetzner Cloud (Ubuntu 22.04 LTS), Docker Engine + Compose plugin, Caddy 2 (reverse-proxy + Let's Encrypt), Python 3.12 (efloud-bot image), Anthropic API (overseer summarizer, DRY_RUN=1 for Week 1).

**Pre-conditions:**
- SSH alias `efloud-bot` working (`ssh efloud-bot 'hostname'` returns `efloud-bot-prod`).
- Local repo at `c:/Users/utkuc/Downloads/efloud-bot/`, branch `master`, commit `855bb87` pushed to GitHub.
- Local `.env` has `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `ANTHROPIC_API_KEY`, `EFLOUD_ALLOW_MAINNET=1`.
- CircuitBreaker state is fresh (the rebuild wiped the HALTED weekly-DD state — this is intentional but means **first boot starts unhalted**; risk parameters must be sane in `configs/config.phase2_1k.yaml`).
- Binance positions (BTC, ADA) already have manual TP/SL placed; OP status unknown — **operator must verify before bot start**.

**Safety rails:**
- `EFLOUD_AUTOSTART=0` in `.env.production` — bot stays stopped after compose up; operator manually presses Start in dashboard.
- `EFLOUD_OVERSEER_DRY_RUN=1` already baked into `docker-compose.prod.yml` — overseer logs only, no Telegram.
- Binance API key whitelist will need the VPS IP (`178.104.122.91`) — already there from the previous deploy, but **verify before bot start**.
- Two checkpoints in plan where execution PAUSES for operator confirmation: (a) after server bootstrap, before pushing secrets; (b) after `docker compose up -d`, before bot autostart flip.

---

## Chunk 1: Preparation + Server Bootstrap

### Task 1: Verify local repo is at master 855bb87

**Files:**
- Read only: `c:/Users/utkuc/Downloads/efloud-bot/`

- [ ] **Step 1: Check git state**

Run: `git -C c:/Users/utkuc/Downloads/efloud-bot status && git -C c:/Users/utkuc/Downloads/efloud-bot log --oneline -3`

Expected output:
```
On branch master
Your branch is up to date with 'origin/master'.
nothing to commit, working tree clean

855bb87 fix(overseer): 4 bugs — dedup bypass, ingestor cadence, token cap
be3378e test(healthz): update breaker_halted assertion to match 200-suspended contract
9a9d337 feat(overseer): 24/7 bot observer agent — sidecar with rule engine + LLM summarizer + healthz HALTED fix (#62)
```

If any commits are missing or branch is not master, STOP and resolve before continuing.

---

### Task 2: Verify SSH access to VPS

**Files:**
- Read only: `~/.ssh/config`

- [ ] **Step 1: Test SSH connectivity**

Run: `ssh -o ConnectTimeout=10 efloud-bot 'echo SSH_OK && hostname && uname -a'`

Expected:
```
SSH_OK
efloud-bot-prod
Linux efloud-bot-prod 5.15.0-... Ubuntu ... x86_64 ...
```

If timeout or permission denied, fix SSH first (see `memory/hetzner_ssh_access.md`).

- [ ] **Step 2: Confirm VPS is empty**

Run: `ssh efloud-bot 'ls /opt/ 2>&1; which docker 2>&1; df -h / | tail -1'`

Expected:
- `/opt/` empty (no `efloud-bot` dir)
- `which docker` → no output / "not found"
- `/dev/sda1` ~1 GB used / 75 GB total

If `/opt/efloud-bot` already exists or Docker is installed, the VPS is NOT in the expected fresh state — STOP and investigate (somebody else may have started deploy).

---

### Task 3: Upload setup-server.sh and run bootstrap

**Files:**
- Use: `c:/Users/utkuc/Downloads/efloud-bot/deploy/setup-server.sh`

- [ ] **Step 1: Copy setup script to VPS**

Run: `scp c:/Users/utkuc/Downloads/efloud-bot/deploy/setup-server.sh efloud-bot:/root/setup.sh`

Expected: `setup-server.sh   100%   ...   ...KB/s`

- [ ] **Step 2: Execute bootstrap**

Run: `ssh efloud-bot 'bash /root/setup.sh' 2>&1 | tee /tmp/setup-output.log`

This installs Docker, Docker Compose plugin, UFW (22/80/443), fail2ban, creates `efloud` user. Takes ~3-5 min.

Expected final lines:
```
✅ Server bootstrap complete.
Server public IPv4 (whitelist this in Binance API key):
178.104.122.91
```

If any step fails (e.g., apt mirror issue), STOP — read `/tmp/setup-output.log` to diagnose.

- [ ] **Step 3: Verify bootstrap landed**

Run: `ssh efloud-bot 'docker --version && docker compose version && ufw status | head -5 && id efloud'`

Expected:
```
Docker version 26.x.x or 27.x.x ...
Docker Compose version v2.x.x
Status: active
... (22, 80, 443 listed)
uid=1001(efloud) gid=1001(efloud) groups=1001(efloud),133(docker)
```

- [ ] **Step 4: Commit checkpoint — none (no local code changed)**

Nothing to commit on local. This task only mutates the VPS.

---

### Task 4: Clone repo into /opt/efloud-bot

**Files:**
- VPS: `/opt/efloud-bot/`

- [ ] **Step 1: Clone master**

Run: `ssh efloud-bot 'cd /opt && git clone --depth 50 -b master https://github.com/Leblepito/efloud-bot.git efloud-bot && chown -R efloud:efloud /opt/efloud-bot'`

Note: `--depth 50` is enough for `deploy.sh` to do `git fetch + pull` later, and avoids cloning years of history.

Expected: `Cloning into 'efloud-bot'... done.`

- [ ] **Step 2: Verify commit is 855bb87**

Run: `ssh efloud-bot 'cd /opt/efloud-bot && git log --oneline -1'`

Expected: `855bb87 fix(overseer): 4 bugs — dedup bypass, ingestor cadence, token cap`

If a different commit, the repo state is wrong — STOP.

---

## Chunk 2: Environment + Secrets

### Task 5: Prepare local .env.production file

**Files:**
- Create local: `c:/tmp/.env.production` (temporary; never committed)
- Source: `c:/Users/utkuc/Downloads/efloud-bot/.env` (local secrets) and `c:/Users/utkuc/Downloads/efloud-bot/deploy/.env.production.example` (template)

- [ ] **Step 1: Generate a fresh SESSION_SECRET**

Run: `python -c "import secrets; print(secrets.token_hex(32))"`

Copy the output — this is the new SESSION_SECRET. Do NOT reuse the local one from `.env` (which is for dev).

- [ ] **Step 2: Pick a strong DASHBOARD_PASSWORD**

User must choose a password ≥16 chars, different from local `efloud-test-12345`. Suggested: another run of `python -c "import secrets; print(secrets.token_urlsafe(20))"`.

Store both new SESSION_SECRET and DASHBOARD_PASSWORD somewhere safe (password manager) before pasting into the env file.

- [ ] **Step 3: Compose .env.production file body locally**

Write `c:/tmp/.env.production` with this content (fill in values, do NOT commit):

```
BINANCE_API_KEY=<from local .env>
BINANCE_API_SECRET=<from local .env>
EFLOUD_ALLOW_MAINNET=1

EFLOUD_CONFIG_PATH=configs/config.phase2_1k.yaml
EFLOUD_AUTOSTART=0
EFLOUD_AUTO_MIGRATE=0

DASHBOARD_PASSWORD=<step 2 value>
SESSION_SECRET=<step 1 value>

ALLOWED_ORIGINS=https://178-104-122-91.nip.io

ENV=production
LOG_LEVEL=INFO

ANTHROPIC_API_KEY=<from local .env>
```

Note: `DATABASE_URL` intentionally NOT included — Supabase pooler is still broken per local `.env` comment; `EFLOUD_AUTO_MIGRATE=0` lets the bot run without persistence.

- [ ] **Step 4: Verify .env.production has no placeholder values**

Run: `grep -E "(CHANGE_ME|PASTE_|your_)" c:/tmp/.env.production || echo "NO_PLACEHOLDERS"`

Expected: `NO_PLACEHOLDERS`. If any matches print, fix before uploading.

---

### Task 6: Upload .env.production to VPS

**Files:**
- VPS create: `/opt/efloud-bot/.env.production` (owner `efloud`, mode 600)

- [ ] **Step 1: SCP file to VPS root tmp**

Run: `scp c:/tmp/.env.production efloud-bot:/tmp/.env.production`

Expected: `100% ... KB/s`

- [ ] **Step 2: Move into repo dir with correct owner + permissions**

Run: `ssh efloud-bot 'mv /tmp/.env.production /opt/efloud-bot/.env.production && chown efloud:efloud /opt/efloud-bot/.env.production && chmod 600 /opt/efloud-bot/.env.production && ls -la /opt/efloud-bot/.env.production'`

Expected: `-rw------- 1 efloud efloud ... .env.production`

- [ ] **Step 3: Sanity check (no secret printed)**

Run: `ssh efloud-bot 'wc -l /opt/efloud-bot/.env.production && grep -c "^[A-Z]" /opt/efloud-bot/.env.production'`

Expected: ~15-20 lines, ~12 lines starting with uppercase var name. Do NOT cat the file over SSH — secrets in log history.

- [ ] **Step 4: Delete local temp file**

Run: `rm c:/tmp/.env.production`

This file held secrets and must not linger on the local machine.

---

### Task 7: ⏸️ CHECKPOINT — Operator verifies Binance state before deploy

**Files:** none (manual operator step).

- [ ] **Step 1: Operator opens Binance UI, checks:**

  - BTC/USDT futures position: TP and SL orders present (operator placed manually on 2026-05-14).
  - ADA/USDT futures position: TP and SL orders present (operator placed manually on 2026-05-14).
  - **OP/USDT futures position: state UNKNOWN** — operator either places manual TP/SL OR closes the position OR confirms it doesn't exist anymore.

- [ ] **Step 2: Operator confirms Binance API key IP whitelist still includes 178.104.122.91**

Binance → API Management → key → Edit restrictions → confirm `178.104.122.91` in trusted IP list.

- [ ] **Step 3: Operator gives go-ahead OR aborts**

If any of the above is not OK, STOP here. Do NOT proceed to deploy until positions are safe.

---

## Chunk 3: Deploy + Verification

### Task 8: Run deploy.sh (build + up)

**Files:**
- Run on VPS: `/opt/efloud-bot/deploy/deploy.sh`

- [ ] **Step 1: Execute deploy script**

Run: `ssh efloud-bot 'cd /opt/efloud-bot && bash deploy/deploy.sh' 2>&1 | tee /tmp/deploy-output.log`

This does: `git fetch + pull` (no-op, already at master), `docker compose build` (~3-5 min first build), `docker compose up -d`, healthz wait (≤60s).

Expected ending:
```
✅ Bot is up and healthy
{"status":"ok",...}
```

If healthcheck fails within 60s, the script prints last 80 lines of logs. STOP and read `/tmp/deploy-output.log`.

- [ ] **Step 2: Verify all expected containers are up**

Run: `ssh efloud-bot 'docker compose -f /opt/efloud-bot/docker-compose.prod.yml ps'`

Expected status `running` for:
- `efloud-bot` (healthy)
- `efloud-alerter` (running, no healthcheck)
- `efloud-overseer` (running, no healthcheck)
- `efloud-caddy` (running)
- `efloud-autoheal` (running)

If any container is `exited` or `restarting`, STOP — read its logs:
`docker compose -f /opt/efloud-bot/docker-compose.prod.yml logs --tail=80 <container>`

- [ ] **Step 3: Verify healthz endpoint shape**

Run: `ssh efloud-bot 'docker compose -f /opt/efloud-bot/docker-compose.prod.yml exec -T efloud-bot python -c "import urllib.request,json; print(json.dumps(json.loads(urllib.request.urlopen(chr(34)+chr(104)+chr(116)+chr(116)+chr(112)+chr(58)+chr(47)+chr(47)+chr(108)+chr(111)+chr(99)+chr(97)+chr(108)+chr(104)+chr(111)+chr(115)+chr(116)+chr(58)+chr(56)+chr(48)+chr(56)+chr(48)+chr(47)+chr(104)+chr(101)+chr(97)+chr(108)+chr(116)+chr(104)+chr(122), timeout=5).read().decode()), indent=2))"'`

(Simpler version if shell-quoting tolerates it):
`ssh efloud-bot "docker exec efloud-bot curl -s http://localhost:8080/healthz | python -m json.tool"`

Expected JSON keys include: `status`, `checks`, `now_ms`, `failures`. `status` should be `"ok"` (bot not started yet → no breaker, healthz still healthy because we treat AUTOSTART=0 as intentional, not unhealthy).

If `status` is `"suspended"` with `failures: ["breaker_halted"]`, the breaker state from the previous incident somehow persisted — unexpected, STOP and investigate.

---

### Task 9: Verify overseer rule registry loaded

**Files:** none.

- [ ] **Step 1: Check OVERSEER_RULES count**

Run: `ssh efloud-bot 'docker exec efloud-overseer python -c "from ops.overseer.rules import OVERSEER_RULES; print(len(OVERSEER_RULES)); [print(r.name) for r in OVERSEER_RULES]"'`

Expected:
```
6
bot_unhealthy
cycle_gap
consecutive_losses
audit_score_dropping
regime_flipflop
reverse_block_streak
```

- [ ] **Step 2: Check overseer DRY_RUN flag**

Run: `ssh efloud-bot 'docker exec efloud-overseer printenv EFLOUD_OVERSEER_DRY_RUN'`

Expected: `1`. If `0`, Telegram alerts will fire — STOP and fix.

- [ ] **Step 3: Check alerter rule count (separate Track 2 alerter)**

Run: `ssh efloud-bot 'docker exec efloud-alerter python -c "from ops.alerter.rules import RULES; print(len(RULES))"'`

Expected: `9`. If different, alerter is at wrong commit somehow.

---

### Task 10: Tail logs briefly to confirm steady state

**Files:** none.

- [ ] **Step 1: Watch logs for 30s, look for errors**

Run: `ssh efloud-bot 'timeout 30 docker compose -f /opt/efloud-bot/docker-compose.prod.yml logs -f --tail=20 2>&1' || true`

Look for:
- ✅ `efloud-bot` printing FastAPI startup / cycle_loop (or stopped-state if AUTOSTART=0)
- ✅ `efloud-overseer` printing "overseer watch loop starting" and tick stats
- ✅ `efloud-alerter` printing tail/poll cadence
- ❌ NO `Traceback`, `CRITICAL`, `ImportError`, `binance.exceptions.BinanceAPIException`

If errors appear, STOP and diagnose before continuing.

---

### Task 11: ⏸️ CHECKPOINT — Operator opens dashboard and presses Start

**Files:** none (manual operator step in browser).

- [ ] **Step 1: Operator opens dashboard URL**

URL: `https://178-104-122-91.nip.io`

Browser may warn about cert on first load (Let's Encrypt issuing) — wait ~30s, refresh.

- [ ] **Step 2: Login with DASHBOARD_PASSWORD from .env.production**

- [ ] **Step 3: Verify pre-start state**

In dashboard:
- `bot_running`: `false`
- `cycle_count`: 0 or undefined
- watchlist visible (10 coins)
- No critical errors banner

- [ ] **Step 4: Press Start button — operator decides moment**

This is the irreversible go-live action. Once Start is pressed, the bot begins ticking and may place orders on Binance.

DO NOT auto-press Start from this plan — the plan stops here. Operator confirms readiness based on:
- All positions on Binance are protected with TP/SL.
- Risk config (`configs/config.phase2_1k.yaml`) reviewed (post-rebuild reset means clean slate; verify position size, leverage, drawdown caps).
- Operator/Hermes is available to watch the first ~30 min of trading.

- [ ] **Step 5: After Start, watch first cycle**

```
ssh efloud-bot 'docker compose -f /opt/efloud-bot/docker-compose.prod.yml logs -f --tail=50 efloud-bot'
```

Expected within ~1-2 min: `cycle_start` event, regime detection per symbol, no `Traceback`.

---

## Chunk 4: Memory + Documentation Updates

### Task 12: Update memory files with post-deploy state

**Files:**
- Modify: `C:/Users/utkuc/.claude/projects/c--Users-utkuc-Downloads-efloud-bot/memory/efloud_state.md`
- Modify: `C:/Users/utkuc/.claude/projects/c--Users-utkuc-Downloads-efloud-bot/memory/MEMORY.md`

- [ ] **Step 1: Update efloud_state.md with new state**

Replace prior "bot DOWN (Exited 137)" entry with:
> Bot RUNNING at master `855bb87` (PR #62 overseer + healthz fix live). Deployed 2026-05-15 from local laptop via SSH after VPS rebuild incident. AUTOSTART=0, operator pressed Start manually. Overseer DRY_RUN=1.

- [ ] **Step 2: Update MEMORY.md index line for state**

The state link should now read "RUNNING at `855bb87`" not "DOWN".

- [ ] **Step 3: Commit memory updates (local repo, NOT the bot repo)**

Memory dir is outside the efloud-bot repo — no commit needed. Files auto-load next session.

---

### Task 13: Tag the deploy commit on GitHub (optional)

**Files:** none.

- [ ] **Step 1: Tag locally and push**

Run:
```
git -C c:/Users/utkuc/Downloads/efloud-bot tag -a deploy/2026-05-15-vps-rebuild -m "Redeploy after VPS rebuild (master 855bb87)"
git -C c:/Users/utkuc/Downloads/efloud-bot push origin deploy/2026-05-15-vps-rebuild
```

This makes future "what was deployed when" trivial. Skip if not desired.

---

## Rollback Plan

If anything between Task 8 and Task 11 goes wrong:

1. **Container fails to start:** `ssh efloud-bot 'docker compose -f /opt/efloud-bot/docker-compose.prod.yml down'` — stops everything. Bot is not running, so no live risk.
2. **Bot started but misbehaving:** in dashboard press **Stop**, then `docker compose down` — Binance positions remain (operator's manual TP/SL still active).
3. **Caddy cert issue:** dashboard inaccessible but bot internal — temporarily fall back: `ssh -L 8080:efloud-bot:8080 efloud-bot` (port-forward), open `http://localhost:8080`.
4. **Wrong commit deployed:** `ssh efloud-bot 'cd /opt/efloud-bot && git fetch && git checkout <good-commit> && bash deploy/deploy.sh'`.

Binance positions are **NOT** at risk from any of these failures — the bot can't take new actions while stopped, and existing TP/SL orders live on Binance independently.

---

## Out-of-Scope (deliberately deferred)

- **DATABASE_URL / persistence:** Supabase pooler still broken (per local `.env` comment). Plan leaves `EFLOUD_AUTO_MIGRATE=0`. Wire DB in a separate session.
- **Hetzner Cloud project SSH key upload:** so rebuilds auto-install our key. Memory file `hetzner_ssh_access.md` documents this — needs manual web step OR API token.
- **Snapshot creation:** after deploy is stable, create a Hetzner snapshot to make future rebuilds cheap. Hermes/operator call.
- **PR #64 (reconcile Conditional tab):** mentioned in earlier priority list; unrelated to this redeploy.

---

## Acceptance Criteria

Plan succeeds when **all of** the following are true after Task 11 Step 5:

1. `ssh efloud-bot 'docker compose ps'` shows 5 containers running, `efloud-bot` healthy.
2. `https://178-104-122-91.nip.io/healthz` returns `{"status":"ok",...}` (via Caddy).
3. Dashboard login works with new `DASHBOARD_PASSWORD`.
4. After operator presses Start, logs show `cycle_start` within 2 min, no tracebacks.
5. Memory `MEMORY.md` index reflects "RUNNING at 855bb87".
6. Local `c:/tmp/.env.production` is deleted (no secret leakage).

---

## Estimated Wall-Clock Time

| Chunk | Tasks | Time |
|---|---|---|
| 1 (Bootstrap) | 1-4 | ~10 min (apt + docker install dominates) |
| 2 (Env + secrets) | 5-7 | ~10 min (operator Binance check is variable) |
| 3 (Deploy + verify) | 8-11 | ~10 min (build is ~3-5 min, healthz wait ~1 min, operator Start decision is variable) |
| 4 (Docs) | 12-13 | ~3 min |
| **Total** | | **~30-45 min** |
