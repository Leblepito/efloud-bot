# Efloud SMC Bot

Binance USDT-M futures üzerinde çalışan Efloud SMC (Smart Money Concepts) trade botu.
Güncel odak: **Ualgo Telegram sinyal entegrasyonu + canlı operasyon güvenliği**.

- **Bugün:** Binance futures / crypto execution
- **Yakın dönem:** dashboard, test coverage, daily brief ve ops kalitesi
- **Roadmap:** pluggable exchange adapter ile MT5/OANDA forex desteği
- **Rafta:** U2algo_bot (u2Algo.com içerik paylaşım botu)

> Production canlıdır. Risk, mainnet, deploy ve açık pozisyonları etkileyen değişiklikler
> Hermes/Utku onayı olmadan yapılmaz.

---

## Pausing new entries

The bot supports pausing **new market entries** while keeping existing position
protection active.

### What it does

- Blocks new entries before exchange order submission.
- Keeps reconcile running.
- Keeps lifecycle/SL/TP management running.
- Keeps breaker/equity updates running.
- Keeps notifications and status reporting running.

### What it does not do

- Does not close existing positions.
- Does not cancel existing SL/TP orders.
- Does not stop the bot.
- Does not replace `dry_run`.
- Does not provide runtime hot-flip without container recreate.

### Config activation

```yaml
safety:
  pause_new_entries: true
```

Production activation requires Hermes/Utku approval.

### Env override

```bash
EFLOUD_PAUSE_NEW_ENTRIES=true
```

Env has precedence over config. Accepted true values: `1`, `true`, `yes`, `on`.
Accepted false values: `0`, `false`, `no`, `off`, and empty string.
Unknown env values are ignored with a warning and the config value is used.

Important: Docker env changes require container recreate:

```bash
docker compose -f docker-compose.prod.yml up -d efloud-bot
```

Do **not** use `docker restart` for env/config pickup.

### Verification

Startup logs include the effective value and source:

```text
pause_new_entries config loaded: effective=True source=env (config=False, env='true')
```

Blocked signals log `reason=pause_new_entries` and the source
(`EFLOUD_PAUSE_NEW_ENTRIES` or `safety.pause_new_entries`).

## Orphan position auto-protection

When the bot detects an exchange position that is not in local lifecycle state
(an orphan), it can optionally place a close-position `STOP_MARKET` stop-loss so
the position is protected even though the bot cannot manage the full lifecycle.

### What this does not do

- Does not import the orphan into lifecycle state.
- Does not place take-profit orders.
- Does not cancel any existing orders.
- Does not auto-fix wrong-direction or non-reduceOnly SL orders; those produce
  critical warnings only.

### Modes

- `warn_only` (default): observe and log, no orders placed.
- `place_missing_sl`: place `closePosition=true STOP_MARKET reduceOnly=true` SL
  for unprotected orphan positions.

### Activation

Start with observation only:

```yaml
safety:
  orphan_protection:
    enabled: true
    mode: warn_only
```

Then recreate the container; do not use `docker restart` for config pickup:

```bash
docker compose -f docker-compose.prod.yml up -d efloud-bot
```

Observe one full cycle of `orphan_protection.warn_only` logs. If clean, switch
`mode` to `place_missing_sl` and recreate again. Production activation requires
Hermes/Utku approval.

### Why no env override

Auto-placing orders is not an emergency hot-flip. It requires deliberate operator
review, so this feature intentionally uses config only.

---

## Current Status

- Production: Hetzner VPS + `docker-compose.prod.yml`
- Aktif çalışma alanı: **Ualgo_bot + Efloud-bot**
- PR-B daily brief audit tamamlandı; günlük brifing lifecycle state, WEAKNESS count ve GitHub özetini kullanır.
- Test altyapısı root-level pytest discovery + regression guard testleriyle güncellendi.
- UI tarafında destructive controls (Stop / Kill Switch) erişilebilirlik ve güvenlik iyileştirmeleri yapıldı.

### Recent Changes

- **PR #30** — WEAKNESS churn guard + `log_audit` JSONB serialization fix
- **PR #31** — `CLAUDE.md` project memory + temel Claude agents/skills
- **PR #32** — opsiyonel Claude extras (explorer, UI/UX audit, forex research, `/review` command)
- **PR #33** — root-level `test_*.py` dosyalarını pytest collection'a dahil etme
- **PR #34** — `test_safety.py` helper rename; pytest fixture confusion fix
- **PR #35** — lifecycle/audit/reconcile/breaker regression guard testleri
- **PR #36** — Stop / Kill Switch UI accessibility & safety improvements

---

## What It Does

- Efloud SMC sinyal üretimi: CHoCH/BOS, Order Block, FVG, SFP, OTE, range context
- Multi-timeframe karar akışı: HTF bias → MTF onay → entry timeframe
- Confluence scoring + regime detection
- Binance futures execution via CCXT / Binance API
- Server-side SL/TP ve reduce-only order yönetimi
- Position lifecycle: TP1/TP2, break-even SL, WEAKNESS partial exits, reconcile
- Safety layer: circuit breaker, position guard, mainnet guard, state persistence
- FastAPI backend + Next.js dashboard
- Telegram alerter, audit log, daily reports / morning brief

---

## Architecture

```text
main.py
  └── SafeOrchestrator (engine/__init__.py)
        ├── SymbolUniverse (engine/universe.py)
        ├── SMCEngine + signal pipeline (engine/smc.py, engine/signals.py)
        ├── Regime detector (engine/regimes/)
        ├── Confluence scoring (engine/confluence.py)
        ├── PositionLifecycle (engine/lifecycle.py)
        ├── Safety layer (engine/safety/)
        └── BinanceClient + OrderManager (exchange/__init__.py)

backend/             → FastAPI, WebSocket, DB, migrations, notifications
frontend/            → Next.js dashboard (static export)
ops/                 → Telegram alerter, daily reports
backtest/            → walk-forward/backtest engine
configs/             → strategy profiles
state*/              → runtime state volumes / local state directories
```

Useful entry points:

- `main.py` — bot startup
- `engine/safe_orchestrator.py` / `engine/__init__.py` — main cycle orchestration
- `exchange/__init__.py` — Binance client, order manager, reconcile path
- `engine/lifecycle.py` — position lifecycle and WEAKNESS handling
- `engine/safety/breaker.py` — circuit breaker
- `backend/api.py` — dashboard/backend API
- `backend/migrate.py` — migration runner
- `frontend/` — dashboard UI

Line numbers in docs are approximate; verify with `rg`, `grep`, or by reading the file before editing.

---

## Live Ops Guardrails

**Production is live. Treat this as a trading system, not a demo script.**

- Live deploy, VPS/SSH operations, risk parameter changes, mainnet/dry_run/testnet changes require Hermes/Utku approval.
- `EFLOUD_ALLOW_MAINNET=1` is required for intentional mainnet use.
- Keep `dry_run: true` unless a live trading rollout has been explicitly approved.
- Secrets live in env files or platform secrets — never commit API keys or tokens.

### Docker Compose env changes

`docker restart` or `docker compose restart` does **not** reload changed env vars.

Use recreate instead:

```bash
cd /opt/efloud-bot
docker compose -f docker-compose.prod.yml up -d
```

### Database migrations

Migration runner does not auto-run in production. After adding new `.sql` migrations:

```bash
docker exec efloud-bot python3 -m backend.migrate up
```

Copy the migration output into the PR/deploy notes.

### Conditional order caveat

`ccxt.fetch_open_orders()` may not show Binance conditional/algo TP/SL orders.
For SL/TP/order reconcile checks, cross-check with Binance algo endpoints or the Binance UI.
Do not assume “0 open orders” from `fetch_open_orders()` means there are no TP/SL orders.

---

## Configuration

Primary config lives in `config.yaml` / `configs/` strategy profiles. Environment values override file config where implemented.

Common env vars:

- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`
- `DATABASE_URL`
- `EFLOUD_ALLOW_MAINNET`
- `EFLOUD_TELEGRAM_TOKEN`
- `EFLOUD_TELEGRAM_CHAT_ID`
- SMTP vars for daily reports, if email reporting is enabled

Risk and safety config changes must be reviewed as trading-risk changes, not ordinary config edits.

---

## Tests

Default command:

```bash
python3 -m pytest
```

Useful targeted examples:

```bash
python3 -m pytest tests/ backend/tests/ -q
python3 -m pytest backend/tests/test_lifecycle_weakness_churn.py -q
python3 -m pytest backend/tests/test_log_audit_jsonb_serialization.py -q
python3 -m pytest backend/tests/test_reconcile_algo_orders_visibility.py -q
python3 -m pytest test_safety.py -v
```

Notes:

- Pytest discovery includes root-level `test_*.py` files.
- Some legacy/manual backtest scripts are intentionally ignored by pytest config.
- Default tests must not require live Binance/Supabase/API credentials.
- Live/integration tests should be opt-in and clearly named (for example `test_real_*`).

---

## Claude / Hermes Workflow

This repo includes project memory and reusable Claude assets:

- `CLAUDE.md` — project memory: architecture, ops rules, current state
- `.claude/agents/` — project-specific review/test/risk agents
- `.claude/skills/` — bugfix, deploy-safety and trading-risk workflows
- `.claude/commands/` — optional workflow commands

Role split:

- **Hermes:** live ops, deploy, VPS/SSH, risk decisions, mainnet changes, incident response, final merge/deploy coordination.
- **Claude Code:** docs, tests, refactor proposals, read-only research, PR preparation and code review support.

Claude Code should not run production commands, change live risk config, merge/deploy, or bypass mainnet guards.

---

## Forex Roadmap

Forex support is planned but not implemented yet.

Current execution is Binance-bound. The intended path is a pluggable adapter interface:

- `BinanceAdapter` — current crypto futures path
- `MT5Adapter` — likely first forex candidate because of broker availability / practical usage
- `OandaAdapter` — cleaner API-native option for later evaluation

Key design questions before implementation:

- Symbol mapping: `BTC/USDT` vs `EURUSD` / `XAUUSD`
- Lot size, pip value, spread and market-hours handling
- Server-side SL/TP behavior per broker
- Position/reconcile semantics
- Demo/paper validation before any live pilot

Forex work should start with a separate design/spec PR before code changes.

---

## DON'T

- Do not commit secrets, API keys, Telegram tokens or private SSH material.
- Do not change `testnet`, `dry_run`, leverage, sizing or risk limits without explicit approval.
- Do not deploy env changes with only `docker restart`.
- Do not mix bugfix + refactor + feature in one PR.
- Do not write default tests that hit live Binance/Supabase APIs.
- Do not trust `ccxt.fetch_open_orders()` alone for conditional TP/SL visibility.
- Do not edit active production config casually while live positions are open.

---

## Related Docs

- `CLAUDE.md` — always-read project memory for Claude sessions
- `RISK_MAP.md` — failure modes and risk analysis
- `docs/` — plans, specs, runbooks and historical notes
- `.claude/` — project-local Claude agents, skills and commands
