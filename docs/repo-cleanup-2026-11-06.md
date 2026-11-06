# Repository cleanup audit — 2026-11-06

Scope: tracked files on `feat/u2algo-price-action` (895 files at `4fda261`).
Rule applied: a path is removed only if it has **no references** anywhere
(`git grep` across code, docs, `.github/`, Dockerfiles, compose files, scripts),
is **not imported or executed** by code, CI, tests or deploy, and is **clearly
obsolete**. When in doubt the path is kept and listed for operator decision.

## Result

Earlier cleanup rounds (`f96b7d8`, `2d64bbf`, `d137eb6`, `562a6a3`, `fd3348d`)
already removed the old handoff dumps, session notes, `.hermes/`, `.superpowers/`
and scratch folders. The items flagged by the pre-survey were re-checked:

| Path | Status | Reference check |
|---|---|---|
| `hermes_tasks/` | Not tracked (already ignored in `.gitignore`, absent from the tree) | `git ls-files hermes_tasks` → empty |
| `docker-compose.yml` | Kept | Default `docker compose` file; used by README quick start |
| `docker-compose.panel.yml` | Kept | Referenced by `deploy/rotate-credentials.sh`; runs `panel.main` |
| `docker-compose.testnet.yml` | Kept | Compose/deploy file (never deleted by policy); see operator list |
| `panel/` | Kept | `panel/main.py` used by `docker-compose.panel.yml` and `tests/test_panel_unified.py` |
| `agents/` | Kept | Desk agent definitions referenced by `AGENTS.md`, `.github/workflows/claude-review.yml`, `.claude-plugin/` |
| `tools/v2_doctor.py` | Kept | Referenced by `engine/safe_orchestrator.py`, `configs/config.phase2_1k.yaml`, tests |
| `risk/` | Kept | Imported by `engine/safe_orchestrator.py` (`from risk import calc_position_size`) |
| `utils/`, `data/` | Kept | Imported by `main.py`, `backend/`, `engine/` |
| `docs/assets/banner.svg` | Kept, now referenced | Was unreferenced; used as the README banner |

### Removed / moved

Second pass (operator asked for unnecessary files to be removed). All three are unreferenced,
untouched since May 2026 and superseded; they stay recoverable from git history.

| Path | Why removed |
|---|---|
| `pine/prompts_for_claude.md` | One-time May 2026 prompts for the first Pine translation; the Pine lab build (`scripts/build_pine_lab.py`) replaced that workflow. |
| `scripts/generate_daily_report.py` | 42-line excursion report into `reports/` (ignored); superseded by `ops/daily_report/` and `scripts/routines/equity_report.py`. |
| `scripts/print_remote_positions.py` | One-off 49-line diagnostic for an old `state_1k/positions.json` layout. |

`ops/README_SOCIAL.md` was kept and given a note: `u2algo_publisher.py` no longer exists, the publish step is `scripts/lane_g_publish.py`.

### Added to `.gitignore`

| Pattern | Reason |
|---|---|
| `/_to_delete/` | Local staging folder for manual cleanups (already excluded from ruff in `pyproject.toml`) |
| `.sdd-report-*.md` | Machine-local subagent run reports; must never reach the public repo |

(`data/lab/`, `hermes_tasks/`, `/scratch/`, `reports/` were already ignored.)

## Candidates for operator decision

Unreferenced by name, but they are operational tools or docs and not clearly
obsolete, so they were kept:

| Path | Why kept / what to decide |
|---|---|
| `docker-compose.testnet.yml` | No file references it; testnet stack with `.env.testnet`. Keep if testnet runs still use it, otherwise fold into `docker-compose.yml` + `configs/config.testnet.yaml`. |
| `scripts/binance_monitor.py` | Standalone CCXT monitor; overlaps with `scripts/routines/position_audit.py` / `margin_watch.py`. |
| `scripts/sync_live_stats.py` | DB → stats sync; unclear whether still run anywhere. |
| `scripts/pre_deployment_checklist.py` | Mainnet pre-flight checklist; overlaps with `preflight.py`. |
| `scripts/run_tests_docker.ps1` | Windows Docker test gate (documented inside the file). |
| `scripts/setup_git_hooks.py` | Optional Graphify hook installer. |
| `docs/runbooks/*` (9 files not linked by name) | Linked as a folder from `README.md`, `HERMES.md`, `docs/OPERATOR_GUIDE.md`; operational value. |
| `pine/efloud_signals_v1.pine`, `pine/efloud_strategy_v1.pine` | Older v1 Pine ports; kept as SMC port history (policy: never overwrite the v2 port, do not delete). |
| `engine/safe_orchestrator.py` (174 KB), `package-lock.json` (189 KB) | Exceed the 150 KB guideline but are core code / lockfile; not changed. |
