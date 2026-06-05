# Kronos Advisory — Remaining Work Handoff

**Date:** 2026-06-05 · **PR:** #166 (`feat/kronos-advisory` → `master`, OPEN/MERGEABLE/CLEAN)
**Commits:** `a69aa3e` (Phase 0–5) · `ee78046` (Phase 6–7 + review fixes) · `f7aa874` (vendor skill + deploy guide)

The Kronos advisory layer (time-series forecast + LLM-synthesis commentary → Telegram/DB) is
**code-complete and parked**. It is **ADDITIVE & ADVISORY-ONLY** — its output never feeds
trade/sizing/SL-TP/confluence — and **default-OFF** (`kronos.enabled: false`). 17 backend + 3
frontend tests green. Nothing is deployed or merged. This doc lists the open items so the next
session/AI can finish them without re-deriving context.

> Read first: `docs/superpowers/plans/2026-06-05-kronos-advisory-integration.md` (full plan + rollout)
> and the Gemini hand-off `docs/handoff/2026-06-05-kronos-gemini-handoff-prompt.md`.

---

## ✅ Done (this lane)
- **Phase 0–5 (`a69aa3e`):** `kronos:` config flag (default-OFF) + flag-gated wiring; `make_llm_client`
  (MiniMax in prod, not hard-wired Gemini); dedicated bounded executor + `Semaphore` (drop-if-busy) +
  `(symbol,direction,bar)` dedup/cooldown + `SentimentCache`; `synth_timeout_sec`; narrowed exceptions;
  Telegram relabel (categorical band, ADVISORY label, `⚠️[fallback]` tag); prewarm/availability gate;
  executor shutdown on stop; 15 hermetic tests.
- **Phase 6–7 (`ee78046`, Gemini + Claude review):** Binance-native data feed
  (`run_kronos_prediction(df=)` → temp parquet → `--df-path` → patched `_predict.py`/`run_kronos.py`);
  `KronosCard.tsx` (advisory-labeled, replaces prior fabricated panel values) + 3 vitest tests.
  Review fixes: **B1** added `pyarrow` to the sub-venv + skill `requirements.txt` (else `read_parquet`
  fails at runtime); **B3** reverted `data_source` default `binance`→`yfinance`.
- **B2 (`f7aa874`):** vendored the patched skill (`scripts/*.py` + `requirements.txt`) into the repo
  (`.gitignore` negation; embedded `.git` removed; `.venv`/`_kronos` stay ignored, rebuilt by `ensure_venv()`).

---

## ⚠️ Coordination (MANDATORY)
- **Shared local working tree:** two sessions branch-switch the same checkout — branch state flaps.
  Do NOT assume the working tree is on a given branch. The Kronos work is safe on
  `origin/feat/kronos-advisory` + PR #166. To edit this branch without racing, use an **isolated git
  worktree** (`git worktree add --detach <path> <sha>` then `git push origin HEAD:feat/kronos-advisory`)
  or the GitHub API.
- **VPS `/opt/efloud-bot` is HYBRID** (base `66c767c` + surgical fixes; bot RUNNING mainnet; positions OPEN).
  - **NEVER** `git pull` / `git reset --hard` on the VPS — clobbers live surgical fixes or pulls un-vetted
    gap commits (e.g. `5cc4318`). Vetted fixes are on `origin/master` (`461f94b`: #156–#161, #164, #165).
    **#162/#163 are backtest-gated — must NOT reach the VPS.**
  - Deploy via **surgical checkout only**: `git checkout origin/master -- <file>`.
  - Do **not** clobber the live working-copy config (`conf=50` + `min_rr=1.8`, uncommitted on VPS) or
    `configs/config.phase2_1k.yaml`.

---

## 📋 Remaining work

### R1 — Merge PR #166 + deploy (MAIN; operator + flat-book gated)
- Merge PR #166 → `master` **only when the book is FLAT** (positions closed). It is inert (`enabled:false`)
  so the merge is behaviorally a no-op.
- After merge, confirm on `master`: `kronos.enabled: false` **and** `data_source: yfinance` in both
  `config.yaml` and `configs/config.phase2_1k.yaml` (no config-deploy surprise).
- VPS deploy = **surgical checkout** of the Kronos files:
  `engine/ai/kronos.py`, `backend/bot_runner.py`, `backend/db.py`, `engine/notifications/__init__.py`,
  `config.yaml`, `configs/config.phase2_1k.yaml`, `backend/migrations/011_kronos_telemetry.sql`,
  `frontend/components/KronosCard.tsx`, `frontend/components/TradeDetailPanel.tsx`,
  `frontend/components/__tests__/KronosCard.test.tsx`, `frontend/vitest.config.ts`,
  `frontend/package.json`, `frontend/package-lock.json`, and the vendored
  `external_repos/kronos-claude-skill/scripts/*.py` + `requirements.txt`.

### R2 — Phase 8 (deferred; quality — BEFORE trusting numeric confidence)
- `external_repos/kronos-claude-skill/scripts/_predict.py`: raise `sample_count` `1 → ≥20`; derive the
  band from the empirical **p10/p90** of the sample paths (not min/max of a single path); make
  `interval`/`pred_len` config-driven and aligned to the entry TF / trade horizon.
- Shadow-study: log `{direction, band, change_pct}` vs realized R-multiple; run a falsifiable
  aligned-vs-divergent **PF test (≥150 trades)**. Keep `show_numeric_confidence: false` until a positive
  regime-split result exists.

### R3 — Persist the real band (minor; quality — M1)
- Today only `kronos_comment` + `kronos_confidence` are persisted; `KronosCard` **derives** the band
  heuristically (`conf>=85→NARROW`, text hints) so it can mismatch the real `synthesis["band"]`.
- Persist `synthesis["band"]` (NARROW/MODERATE/WIDE) to the DB/API + `Trade` type, and have `KronosCard`
  render the real band. If you add a migration, remember prod is DB-less (inert; Telegram is the live surface).

### R4 — Staged enable (operator; AFTER deploy)
- VPS pre-warm (off the trade path):
  `python external_repos/kronos-claude-skill/scripts/run_kronos.py BTC-USD 1mo 1h 12`
  (if a stale `.venv` exists, `rm -rf external_repos/kronos-claude-skill/.venv` first so the new
  `requirements.txt` pyarrow is installed — only needed if enabling `binance`).
- Enable `enabled: true`, `run_on: [trade_open]` (readonly OFF). Watch ≥24h: one tagged Telegram per
  trade open, `source != [fallback]`, RSS flat, `reconcile` cadence unaffected. Only if clean, consider
  adding `readonly` (cooldown-capped). Flip `data_source: binance` only once the vendored skill + venv
  parquet engine are provisioned on the VPS; otherwise keep `yfinance`.
- Kill switch: `kronos.enabled: false`.

---

## ✅ Verification
```
python -m pytest backend/tests/test_kronos_integration.py -q   # 17 green, hermetic (no subprocess/network)
cd frontend && npm run test                                    # 3 green
```
Do not deploy / merge without a flat book + operator approval.
