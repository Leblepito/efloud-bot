# Phase 0 — Read-Only SL Evidence Extraction Script

**Date:** 2026-05-12
**Status:** Implemented in PR #48 (`feature/phase0-sl-evidence`)
**Owners:** Utku (decision), Claude (spec/architect), Hermes (implementation)
**Production impact:** **NONE.** Read-only script. No deploy. No exchange calls.
**Hard prerequisite of:** [PR-B v2 spec](./2026-05-12-pr-b-sl-logic-spec-v2.md).

Applied project skills:
- `efloud-trading-risk-checklist` — risk-adjacent: surfaces evidence for risk decision.
- `efloud-deploy-safety` — read-only by construction; no live state touched.
- `superpowers:test-driven-development` — 10 tests RED first, then GREEN, then smoke.
- `superpowers:verification-before-completion` — local smoke test required before PR.

---

## 1. What this script does

`scripts/extract_sl_evidence.py` is a single-purpose, read-only CLI that:

1. Queries the `trades` table (LEFT JOIN `trade_audits`) from the production
   DB for a given UTC time window + comma-separated symbol set.
2. Parses `trade_journal.jsonl` (default path:
   `state_aggressive/trade_journal.jsonl`) and attaches MAE/MFE per trade
   where available.
3. Emits a CSV (one row per closed trade) and a markdown summary
   (per-symbol aggregates + H1/H2/H3/H4 indicator sections + empty decision
   matrix).

It does **not** decide H1/H2/H3/H4 dominance. Utku decides. The script is the
data-extraction tool, not the analyst.

---

## 2. Hard constraints (no exceptions)

1. **Read-only DB.** Every SQL string passes through `assert_select_only()`:
   must start with `SELECT` or `WITH` AND must not contain `INSERT|UPDATE|
   DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY|MERGE|CALL` (case
   insensitive, word-boundary).
2. **No exchange imports.** No `BinanceClient`, no `ccxt`, no
   `exchange/__init__.py`. Pure DB + filesystem.
3. **No safety/lifecycle imports.** No `engine.safety.*`, no
   `engine.lifecycle.*`, no `engine.safe_orchestrator.*`.
4. **No mutations to filesystem outside `--out` / `--summary` paths.**
   Never edit configs, never write inside production state volumes.
5. **Idempotent.** Same input → byte-identical CSV (modulo new closing
   trades inside the time window). Deterministic sort: `ORDER BY
   t.closed_at ASC, t.id ASC` SQL-side, and `sorted(rows, key=(closed_at,
   trade_id))` Python-side before CSV write.
6. **Fails closed.**
   - DB unreachable → exit 1 with structured ERROR message (no secrets).
   - Journal missing → CSV emits with `journal_present=false`, summary warns
     once. Never silent partial output.
7. **No secrets in any output stream.** DB URL read from env var; never
   echoed, never written to CSV/summary/log. All three streams (stdout,
   stderr, files) pass through `assert_no_secrets()` regex check.
8. **Audit coverage warning.** If `audit_count / len(rows) < 0.10`, emit a
   stderr WARNING. Do not silently proceed without surfacing this.

---

## 3. Output schemas

### 3.1 CSV columns (26, in this exact order)

| # | Column | Type | Source | Notes |
|---|---|---|---|---|
| 1 | `trade_id` | text | `trades.id::text` | |
| 2 | `symbol` | text | `trades.symbol` | e.g. `OP/USDT` |
| 3 | `direction` | text | `trades.direction` | `LONG` / `SHORT` |
| 4 | `entry` | numeric | `trades.entry` | |
| 5 | `sl` | numeric | `trades.sl` | NULL → empty cell |
| 6 | `exit` | numeric | `trades.exit` | |
| 7 | `reason` | text | `trades.reason` | `SL` / `TP1` / `RECONCILED` / etc. |
| 8 | `pnl` | numeric | `trades.pnl_usdt` | |
| 9 | `pnl_pct` | numeric | `trades.pnl_pct` | |
| 10 | `size` | numeric | `trades.size` | |
| 11 | `opened_at` | timestamptz | `trades.opened_at` | ISO 8601 UTC |
| 12 | `closed_at` | timestamptz | `trades.closed_at` | ISO 8601 UTC |
| 13 | `sl_distance` | numeric | computed: `abs(entry − sl)` | NULL if either input NULL |
| 14 | `sl_distance_pct` | numeric | computed: `sl_distance / entry × 100` | NULL if entry is 0 or NULL |
| 15 | `atr14` | numeric | `trade_audits.notes->>atr_14h` (fallback `atr14`) | NULL if not in notes |
| 16 | `sl_atr_ratio` | numeric | computed: `sl_distance / atr14` | NULL if atr14 missing |
| 17 | `mae_pct` | numeric | `journal entry .mae_pct` (fallback `max_adverse_excursion_pct`) | NULL if journal missing |
| 18 | `mfe_pct` | numeric | `journal entry .mfe_pct` (fallback `max_favorable_excursion_pct`) | NULL if journal missing |
| 19 | `journal_present` | bool | `journal_entries.get(trade_id) is not None` | `true` / `false` |
| 20 | `entry_score` | numeric | `trade_audits.entry_score` | |
| 21 | `sl_score` | numeric | `trade_audits.sl_score` | |
| 22 | `rr_score` | numeric | `trade_audits.rr_score` | |
| 23 | `overall_score` | numeric | `trade_audits.overall_score` | |
| 24 | `outcome` | text | `trade_audits.outcome` | `SL` / `TP1` / `TP2` / etc. |
| 25 | `audit_present` | bool | any of (entry/sl/rr/overall)_score not NULL | `true` / `false` |
| 26 | `trace_id_used` | bool or empty | `trade_audits.notes->>trace_id_used` | empty when not in notes |

Header row uses these exact names. Row formatting rules:
- NULL → empty cell.
- bool → `true` / `false`.
- dict/list → `json.dumps(..., sort_keys=True, ensure_ascii=False)`.
- All other types → `str(...)`.

### 3.2 Summary markdown structure

Exact section order (level-1 + level-2 headings, no extras):

1. `# Phase 0 SL Evidence Summary` (run header) — also includes the
   "Verdict owner: Utku" prose disclaimer.
2. `## Warnings` — bulleted list; if no warnings: `- None`.
3. `## Overall` — closed-trade count, audit coverage `N/M`, journal coverage
   `N/M`, net PnL.
4. `## Per-symbol aggregates` — table:
   `| Symbol | Trades | Net PnL | Wins | Losses | Audit coverage | Journal coverage |`
5. `## H1 indicator — protection failure` — Reconciled/manual close count, NULL/zero SL count.
6. `## H2 indicator — SL price logic` — Rows-with-sl_atr_ratio count, OP+FIL trade count + net PnL.
7. `## H3 indicator — strategy expectancy` — pointer prose: "Use per-symbol aggregates above…"
8. `## H4 indicator — reconcile mismatch` — pointer prose: "Compare bot PnL columns against external Binance/accounting data outside this read-only script."
9. `## Decision matrix` — empty table for Utku to fill: `| Hypothesis | Evidence | Utku verdict |`

Total: 9 headings (1 H1 + 8 H2). The summary is intentionally pointer-heavy
for sections that require cross-data Utku judgement (H3) or out-of-script data
(H4).

### 3.3 Output paths

- CSV → `--out` arg. Required. Path parent created if missing.
- Summary → `--summary` arg. Required. Path parent created if missing.
- Recommended local-only directory: `reports/.local/` (must be in
  `.gitignore`; production-derived data is never committed).

---

## 4. CLI surface

### 4.1 Arguments

| Flag | Required | Default | Description |
|---|---|---|---|
| `--since` | yes | — | UTC lower bound for `closed_at`, ISO 8601 (e.g. `2026-05-05T00:00:00Z`). |
| `--symbols` | yes | — | Comma-separated, e.g. `OP/USDT,FIL/USDT,BTC/USDT`. |
| `--out` | yes | — | CSV output path. |
| `--summary` | yes | — | Markdown summary output path. |
| `--journal` | no | `state_aggressive/trade_journal.jsonl` | JSONL journal path. |
| `--database-url-env` | no | `DATABASE_URL` | Env var name to read DB URL from. |
| `--dry-run` | no | off | Validate args, print plan to stdout, exit 0 without DB or file writes. |

### 4.2 Behavior

- `--dry-run`: prints a single line `DRY RUN: would query N symbols since
  <since>; CSV=<out>; summary=<summary>; journal=<journal>` (after passing
  `assert_no_secrets`), exits 0.
- Normal run: connects to DB via env var (default `DATABASE_URL`), executes
  bound-parameter SELECT, loads journal, enriches rows, writes CSV +
  summary, prints success line to stdout, returns exit 0.

### 4.3 Success stdout line

```
Phase 0 evidence extracted: rows=<N> audit_rows=<A> journal_rows=<J> csv=<path> summary=<path>
```

### 4.4 Required tests (10, file `tests/scripts/test_extract_sl_evidence.py`)

| # | Test name | What it asserts |
|---|---|---|
| 1 | `test_cli_help_works_without_db` | `--help` exits 0; no DB connection attempted. |
| 2 | `test_dry_run_writes_no_files` | `--dry-run` exits 0; no files created at `--out` or `--summary`. |
| 3 | `test_sql_uses_bound_parameters_and_select_only_guard` | Generated SQL is SELECT/WITH only; mutation verbs are rejected; parameters are bound, not interpolated. |
| 4 | `test_csv_null_handling_and_column_order` | NULL values render as empty cells; column order matches §3.1 exactly. |
| 5 | `test_journal_parser_tolerates_missing_file` | Missing journal → warning emitted, CSV rows still produced with `journal_present=false`. |
| 6 | `test_journal_parser_tolerates_malformed_lines` | Malformed JSONL line → skipped with warning; remaining valid lines parsed. |
| 7 | `test_summary_markdown_renders_required_sections` | All 9 headings from §3.2 present in exact order; per-symbol aggregates table renders. |
| 8 | `test_no_secrets_in_outputs` | DB URL containing `postgres://` is never echoed to stdout, stderr, CSV, summary, or warnings. |
| 9 | `test_idempotent_csv_and_summary_output` | Two runs over identical inputs → byte-identical CSV; byte-identical summary md (modulo unordered warnings). |
| 10 | `test_import_guard_forbidden_exchange_and_safety_modules` | `scripts/extract_sl_evidence.py` and `scripts/_sl_evidence/**` do not import `exchange.*`, `engine.safety.*`, `engine.lifecycle.*`, `engine.safe_orchestrator.*`, `ccxt`. |

All 10 must be RED before any implementation. Tests do not connect to a real DB
(use fixtures and mocks). `pytest tests/scripts/test_extract_sl_evidence.py -v`
must run with no env var setup.

### 4.5 Exit codes

| Code | Condition |
|---|---|
| 0 | Success, including `--dry-run`. |
| 1 | DB error (URL missing, connect failure, query failure) or output write error. |
| 2 | Argument validation error (e.g. empty `--symbols` list, argparse failure). |

---

## 5. Module layout

```
scripts/
├── extract_sl_evidence.py          # CLI entry point
└── _sl_evidence/
    ├── __init__.py                  # version constant
    ├── db.py                        # SELECT-only assertion, bound query builder, async fetch
    ├── journal.py                   # JSONL parser with malformed-line tolerance
    ├── render.py                    # CSV writer, summary renderer
    └── secrets.py                   # regex-based no-secrets assertion

tests/scripts/
└── test_extract_sl_evidence.py     # 10 tests per §4.4
```

Underscored package name (`_sl_evidence/`) marks it as private to the script.
Nothing else in the codebase imports it.

---

## 6. Implementation playbook (14 tasks, atomic commits)

Each task: write → run → verify → commit. No mixing.

| Task | Action | Verify |
|---|---|---|
| 0 | Branch `feature/phase0-sl-evidence` from master | `git status` clean on new branch |
| 1 | Scaffold `scripts/_sl_evidence/` + `__init__.py` | `python -c "import scripts._sl_evidence"` |
| 2 | RED — write all 10 tests | `pytest tests/scripts/ -v` → 10 fails / 10 errors |
| 3 | GREEN test 1 (CLI help) | test 1 PASS |
| 4 | GREEN tests 2, 3 (dry-run, SQL guard) | tests 2, 3 PASS |
| 5 | GREEN test 4 (CSV null handling + column order) | test 4 PASS |
| 6 | GREEN tests 5, 6 (journal parser tolerance) | tests 5, 6 PASS |
| 7 | GREEN test 7 (summary markdown sections) | test 7 PASS |
| 8 | GREEN test 8 (no secrets in any output) | test 8 PASS |
| 9 | GREEN test 9 (idempotent) | test 9 PASS |
| 10 | GREEN test 10 (import guard) | test 10 PASS; `reports/.local/` added to `.gitignore` |
| 11 | Local smoke test against prod read replica | output written to `reports/.local/`, NOT committed |
| 12 | Open PR with read-only-emphasis description | PR URL recorded; CI green |
| 13 | STOP. Wait for Utku to review CSV + summary | — |
| 14 | After Utku verdict, PR-B implementer prompt may activate | — |

---

## 7. Local smoke test command

```bash
python scripts/extract_sl_evidence.py \
    --since "$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ)" \
    --symbols OP/USDT,FIL/USDT,BTC/USDT,ETH/USDT,ADA/USDT,SUI/USDT,LTC/USDT \
    --out reports/.local/sl-evidence-test.csv \
    --summary reports/.local/sl-evidence-test.md
```

Expected: completes in < 60 seconds, prints the success line, writes both
files. Inspect first few CSV rows + summary structure manually. If
`audit_rows / rows < 0.10` or `journal_rows == 0`, surface to Utku before
PR-B implementation begins.

---

## 8. Blocker handling

If any of the following happen → STOP, message Utku, do not improvise:

- DB read replica not accessible from your environment.
- `trade_journal.jsonl` missing or corrupted in unexpected ways (beyond the
  malformed-line case the parser handles).
- `trade_audits` empty or sparse (< 10% of trades have audits).
- Tests fail in ways that need spec interpretation.
- Temptation to "also pull funding history" — STOP, that is PR-C.
- Temptation to "cross-check against Binance API" — STOP, no exchange imports.

---

## 9. PR description template

```
docs(pr): Phase 0 — read-only SL evidence extraction (no production impact)

Implements `scripts/extract_sl_evidence.py` per
`docs/superpowers/specs/2026-05-12-pr-b-phase0-script-spec.md`.

- Read-only DB queries (SELECT/WITH only, mutation verbs rejected at runtime).
- No exchange imports, no `engine.safety`, no `engine.lifecycle`.
- 10 tests in `tests/scripts/test_extract_sl_evidence.py` (TDD).
- Local smoke test output not committed (under `reports/.local/`).
- Output: CSV per §3.1 + summary markdown per §3.2.
- Hypothesis verdict NOT decided by this PR; Utku reviews evidence offline.

Production impact: NONE.
```

---

## 10. Verification before completion (script self-checks)

The implementation must demonstrate:

1. `git grep -nE "INSERT|UPDATE|DELETE|DROP|ALTER" scripts/` → empty output.
2. `git grep -nE "from exchange|from engine.safety|from engine.lifecycle|import ccxt|BinanceClient" scripts/extract_sl_evidence.py scripts/_sl_evidence/` → empty output.
3. `pytest tests/scripts/test_extract_sl_evidence.py -v` → 10 PASS.
4. Local smoke test → file outputs exist, success line printed, no secrets in any stream.

If any of the four fails, the PR is not ready for review.

---

## 11. What success looks like

Utku receives:
- PR URL (read-only script, 10 tests, passing).
- Local-only CSV showing trade-level evidence for the 7-day window.
- Local-only summary md with per-symbol P&L + H1-H4 indicator sections + empty
  decision matrix.
- One-line status: "Phase 0 PR ready, evidence sample shared offline,
  standing by."

Then Utku reviews and either:
- "H2 dominant, GO PR-B" → [implementer prompt](./2026-05-12-pr-b-implementer-prompt.md) activates.
- "H1 dominant" / "H3 dominant" / "H4 dominant" → PR-B parks; alternate
  workstream picks up.
- "Need more data" → window extended or metric added; re-run.

The script ships the tool. It does not ship opinions.

---

## 12. Known follow-ups (not in this PR)

- `trade_journal.jsonl` may be empty in production (`journal_rows=0`
  confirmed 2026-05-12). A separate investigation + fix PR is required
  before Utku can render a clean H2 vs H3 verdict. See
  [hermes-handoff-consolidated.md](../../../) Task C and
  [v2 spec §1.5](./2026-05-12-pr-b-sl-logic-spec-v2.md).
- The 10% audit coverage warning is a sanity nudge, not a gate. Utku may
  decide to proceed with sparse audits if the existing rows clearly point
  to one hypothesis.
