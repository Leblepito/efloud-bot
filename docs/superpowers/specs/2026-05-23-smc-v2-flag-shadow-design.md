# SMC v2 Feature Flag + Dry-Run Shadow Mode — Design Spec (PR #S6)

**Status:** Approved (Hermes 2026-05-23 — content + 3-phase rollout)
**Branch:** `feat/smc-v2-flag-shadow`
**Predecessor:** PR #S5.6 (master `7ad0c74`)
**Successor:** PR #S7 (production rollout)

## 1. Goal

Add the feature flag dispatch and dry-run shadow mode so v2 can run in
production-paralel mode (compute signals, log them, do NOT execute orders).
Operator gets 1 week of observable v1-vs-v2 data before PR #S7 flips to live
trading.

**Crucially**: this PR does NOT execute v2 trades on its own. The actual
"first v2 trade" requires:
- `engine.smc_version: "v2"` + symbol in `engine.smc_v2_symbols` whitelist + `engine.smc_v2_shadow: false`
- Hermes manual config edit + container recreate

Default config ships `smc_version: v1` / `smc_v2_symbols: []` / `smc_v2_shadow: false` → zero behavioral change.

## 2. Architecture

```
config.yaml
   └── engine.smc_version: "v1" | "v2"
       engine.smc_v2_symbols: list[str]  ← whitelist; ["*"] = all
       engine.smc_v2_shadow: bool        ← true = log v2 signal, skip order
       smc_v2:
         pullback_timeout_bars: 8
         fvg_priority: true
         ote_band: [0.618, 0.786]
         require_confirmation: true
         max_pending_per_symbol: 3

main.py (line ~522)
   └── if config.engine.smc_version == "v2":
           setup_state_store = SetupStateStore(state_dir / "setup_candidates.json", ...)
       else:
           setup_state_store = None
       SafeOrchestrator(..., setup_state_store=setup_state_store)

engine/safe_orchestrator.py:_place_v2_entry_order
   └── NEW gates (in order, before existing safety gates):
       1. symbol whitelist: `if symbol not in smc_v2_symbols and "*" not in smc_v2_symbols → reject`
       2. shadow mode: `if smc_v2_shadow: log to logs/smc_v2_shadow.log and return None`
```

## 3. Inert default

`engine.smc_version` defaults to `"v1"` in config.yaml. With v1 active:
- `setup_state_store = None` → all v2 hooks short-circuit (PR #67 contract)
- `_place_v2_entry_order` never reached (never invoked)
- Zero behavioral change in production after deploy of this PR

## 4. Shadow mode behavior

When `engine.smc_v2_shadow: true` AND symbol whitelisted:
- v2 signal computation runs to completion (calc_sl + calc_tp_targets + sizing + safety gates)
- BEFORE `order_manager.open_position` call, check `smc_v2_shadow` flag
- If true: log full v2 signal payload to `logs/smc_v2_shadow.log` (JSON-per-line) and return `None`
- Log payload: `{ts, symbol, direction, entry, sl, tp1, tp2, size, entry_setup_source, tp1_target_type, tp2_target_type, bars_to_pullback, confluence_score, would_execute: false, reason: "SHADOW_MODE"}`
- All safety gates still execute (breaker, pos_guard, pause) — operator sees rejections too, logged with `would_execute: false, reason: "<gate_name>"`

## 5. Symbol whitelist

`engine.smc_v2_symbols`:
- `[]` (default) → v2 never fires (even if smc_version=v2)
- `["ETH/USDT", "BTC/USDT"]` → only these symbols use v2
- `["*"]` → all symbols use v2
- Any other symbol falls through to v1 path

Check happens INSIDE `_place_v2_entry_order` as the first gate. v2 candidate
state machine still runs (consumes the setup), but no order placement attempt.

**Decision**: NOT in `_emit_setup_candidates` — that would mean v2 wouldn't
build state for non-whitelisted symbols, breaking the symmetry. The state
machine runs for all symbols; only execution gates by whitelist. Cost is
trivial (in-memory candidate list).

## 6. Out of scope

- Remove `tp2=None` rejection from `_place_v2_entry_order` — defer to PR #S6.5
  (single-target lifecycle integration is its own PR; this PR just wires the flag).
- Telegram notifications for shadow-mode signals (operator reads log file).
- Backtest CLI changes (already comprehensive in PR #S4).
- Daily summary report of shadow vs v1 deltas (defer to follow-up).

## 7. Tests

### 7a. main.py wiring
- `test_main_passes_setup_state_store_when_v2`
- `test_main_passes_none_when_v1`

### 7b. Symbol whitelist gate
- `test_place_v2_entry_order_rejects_when_symbol_not_in_whitelist`
- `test_place_v2_entry_order_accepts_when_symbol_in_whitelist`
- `test_place_v2_entry_order_wildcard_accepts_all`
- `test_place_v2_entry_order_empty_whitelist_rejects_all`

### 7c. Shadow mode
- `test_shadow_mode_logs_signal_and_skips_order`
- `test_shadow_mode_log_payload_shape`
- `test_shadow_mode_off_executes_normally`
- `test_shadow_mode_logs_rejection_with_reason` (when safety gate rejects)

### 7d. Config defaults
- `test_config_defaults_smc_version_v1`
- `test_config_defaults_smc_v2_symbols_empty`
- `test_config_defaults_smc_v2_shadow_false`

## 8. Acceptance

- 12+ new tests green
- Full backend suite: 674 + 12 = 686 expected
- v1 path strictly unchanged (default config inert)
- Hermes deploys this PR; flip flags manually for shadow run; observe 1 week
- Risk-ops gate REQUIRED (touches `engine/safe_orchestrator.py` order placement
  logic + adds production config keys; though defaults preserve v1 inert)

## 9. Deploy + observe

Hermes ops:
1. `git pull && docker compose -f docker-compose.prod.yml up -d` (defaults
   still v1 — zero behavioral change)
2. Edit `config.yaml`:
   ```yaml
   engine:
     smc_version: v2
     smc_v2_symbols: ["*"]
     smc_v2_shadow: true
   ```
3. `docker compose -f docker-compose.prod.yml up -d` (recreate)
4. Observe `logs/smc_v2_shadow.log` for 7 days
5. Daily review: v1 signal vs v2 signal payload, hypothetical PnL deltas
6. PR #S7 if metrics look good
