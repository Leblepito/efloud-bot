# SMC v2 Lifecycle + DB Telemetry — Design Spec (PR #S5)

**Status:** Approved (Hermes-mode autoresearch ratchet 2026-05-23)
**Branch:** `feat/smc-v2-telemetry`
**Parent spec:** `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §6

## 1. Goal

Add observability fields to both `Position` dataclasses (`engine/lifecycle.py`,
`exchange/__init__.py`) + DB schema + bot_runner wiring + single-target close
branch, so v2 trades carry full provenance into the trades table for post-mortem
analysis.

## 2. Fields added (all nullable, all forward-compatible)

| Field | Type | Values | Source |
|---|---|---|---|
| `entry_setup_source` | `str \| None` | `"FVG_PULLBACK"` \| `"OTE_RETRACE"` \| `"V1_LEGACY"` \| `None` | v2: SetupCandidate.target_zone.kind; v1: `"V1_LEGACY"` or `None` |
| `tp1_target_type` | `str \| None` | `"LIQUIDITY"` \| `"FVG_NEAR"` \| `"RR_PROJECTION"` | v2: `calc_tp_targets` result; v1: `None` |
| `tp2_target_type` | `str \| None` | `"FVG_FAR"` \| `"FIB_EXT"` \| `"NONE"` | v2: `calc_tp_targets` result; v1: `None` |
| `bars_to_pullback` | `int \| None` | bars elapsed AWAITING_PULLBACK → IN_ZONE | v2: SetupCandidate.bars_waited at CONFIRM; v1: `None` |

## 3. Changes

### 3.1 `engine/lifecycle.py:58 Position`
Add 4 nullable fields. Update `to_full_dict` + `from_full_dict` to round-trip them.
`open_position` accepts them as optional kwargs.

### 3.2 `exchange/__init__.py:200 Position`
Mirror: 4 nullable fields. `OrderManager.open_position` accepts them as optional
kwargs and threads to the Position constructor.

### 3.3 `backend/migrations/007_smc_v2_telemetry.sql`
```sql
ALTER TABLE trades ADD COLUMN IF NOT EXISTS entry_setup_source TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS tp1_target_type    TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS tp2_target_type    TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS bars_to_pullback   INT;
```
Idempotent (`IF NOT EXISTS`). No backfill — historical rows stay NULL.

### 3.4 `backend/db.py`
- `record_trade_open(...)` gains 4 optional kwargs (default `None`) appended to the INSERT statement.
- `fetch_recent_trades` / `fetch_trades_since` SELECT lists extended.

### 3.5 `backend/bot_runner.py`
The `position_opened` branch already uses `getattr(pos, "trace_id", None)` defensive
pattern — extend the same for the 4 new fields.

### 3.6 `engine/safe_orchestrator.py:_place_v2_entry_order` (PR #71)
When OrderManager.open_position is called, pass:
- `entry_setup_source=cand.target_zone.kind.upper() + "_PULLBACK"` (FVG_PULLBACK or OTE_RETRACE)
  - NOTE: `ZoneSpec.kind` literal values are `"FVG"` and `"OTE"` per `engine/smc_v2/zones.py`. Map: `FVG` → `"FVG_PULLBACK"`, `OTE` → `"OTE_RETRACE"`.
- `tp1_target_type=tp.tp1_source` (string from TPTargets)
- `tp2_target_type=tp.tp2_source if tp.tp2 is not None else "NONE"`
- `bars_to_pullback=cand.bars_waited`

### 3.7 `engine/lifecycle.py` single-target close branch (spec §6)
`partial_close` TP1 path: if `pos.tp2 is None`, instead of moving SL to BE,
close 100% of the position. Caller (orchestrator/reconcile) is responsible for
the actual `_cancel_position_siblings('TP1_FULL_CLOSE')` exchange call — this
spec only handles the in-memory lifecycle.

```python
def partial_close(self, pos, price, size_pct, reason="TP1"):
    if not pos.is_open: return False
    if reason == "TP1" and pos.tp2 is None:
        # Single-target mode: full close on TP1 fill
        return self.close_position(pos, price, "TP1")
    # ... existing logic
```

**Inert proof**: `pos.tp2 = None` can only originate from `_place_v2_entry_order`
(PR #71), which requires `setup_state_store is not None`. Production today:
`setup_state_store = None` → v2 path dormant → no Position with `tp2 = None`
ever created → new branch never executes. v1 always sets `tp2` (float).

## 4. Out of scope

- `_avg_realized_rr` precision fix (PR #S4 follow-up — needs `notional_at_entry`).
- Exchange-side cleanup of orphan SL on single-target TP1 fill (PR #C1 helper
  exists; wiring to lifecycle's single-target branch deferred — orchestrator
  callsite work).
- Telegram notification enrichment (spec §6 mentions; YAGNI for this PR — operator
  reads DB for retros).

## 5. Tests

### 5.1 lifecycle.py
- `test_position_telemetry_fields_default_none`
- `test_position_to_full_dict_roundtrip_with_telemetry`
- `test_open_position_accepts_telemetry_kwargs`
- `test_partial_close_single_target_full_close_on_tp1` (new branch)
- `test_partial_close_two_target_unchanged` (regression — old behavior preserved)

### 5.2 exchange/__init__.py
- `test_position_dataclass_has_telemetry_fields`

### 5.3 db.py
- `test_record_trade_open_accepts_telemetry_kwargs` (mocked pool — verify SQL params)

### 5.4 migration
- The SQL file itself + `backend/migrate.py` integration not unit-tested locally
  (requires real Postgres). Idempotency proven by `IF NOT EXISTS`. Operator runs
  `docker exec efloud-bot python3 -m backend.migrate up` post-deploy per
  CLAUDE.md §5.

## 6. Acceptance criteria

- 7+ new tests, all green
- 6 lifecycle tests preserved (no regression)
- exchange/__init__.py existing tests green
- Full backend suite green (was 626 after PR #S4)
- v1 production path: no semantic change (telemetry fields = None throughout, single-target branch dormant)

## 7. Risk-ops gate

**REQUIRED.** Touches `exchange/__init__.py` (Position dataclass) + adds a
migration. Per CLAUDE.md §4: risk/safety + exchange/ + migrations → risk-ops
reviewer mandatory before merge.

**Risk surface assessment**:
- Position dataclass additive nullable → zero behavioral impact on v1
- Migration `ADD COLUMN IF NOT EXISTS` → idempotent, no data loss
- Single-target close branch gated by `tp2 is None` invariant which only v2
  (currently inert in prod) can produce
- No `engine/safety/` touched
- No `config.yaml` risk:/safety: touched
- No `docker-compose.prod.yml` touched
