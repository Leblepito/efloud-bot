# SMC v2 State-Reload + Notifications tp2=None Hotfix — Design Spec (PR #S5.6)

**Status:** Approved (Hermes 2026-05-23: "ayrı hotfix PR doğru")
**Branch:** `fix/smc-v2-state-reload-tp2-none`
**Predecessor:** PR #S5.5 (master `b8a1568`)
**Successor:** PR #S6 (config flag — REQUIRES this hotfix)

## 1. Problem

PR #S5.5 widened `tp2` to `Optional[float]` everywhere except 3 sites missed by spec scope (now confirmed by Hermes review):

| Site | Today's behavior | Risk after PR #S6 |
|---|---|---|
| `engine/safe_orchestrator.py:294` `tp2=float(d.get("tp2") or 0.0)` | `None → 0.0` coercion | Restart with open single-target Position → silently rehydrated as two-target (tp2=0.0), single-target lifecycle branch never fires on next TP1 |
| `engine/lifecycle.py:224` `tp2=d.get("tp2", 0.0)` | Same coercion (different loader path) | Same risk |
| `backend/notifications/__init__.py:113` `tp2: float` + `f"{tp2:.4f}"` | Crashes on None | First v2 single-target signal → notifier TypeError swallowed by `_emit` try/except → Telegram alert lost |

Format sites at `engine/report.py:163/175` and `safe_orchestrator.py:941` reference `Scenario.tp2` / `Signal.tp2` — both typed `float`. v2 path doesn't traverse those (uses `_place_v2_entry_order` directly). **Deferred — only fix when Scenario/Signal widens.**

## 2. Changes

### 2a. `engine/safe_orchestrator.py:285-298`
```python
# WAS:
tp2=float(d.get("tp2") or 0.0),

# WILL BE:
# tp2=None signals single-target mode (SMC v2). Coercing to 0.0 would
# silently downgrade single-target Position on restart, breaking the
# lifecycle.partial_close single-target branch (PR #S5).
tp2=d.get("tp2") if d.get("tp2") is not None else 0.0,
```

Wait — the simpler fix is to preserve None directly:
```python
_tp2_raw = d.get("tp2")
tp2=float(_tp2_raw) if _tp2_raw is not None else None,
```

Backward-compat:
- Pre-PR-#S5.5 state files: have numeric tp2 → behavior unchanged
- Post-PR-#S5.5: tp2 may be None → preserved as None

### 2b. `engine/lifecycle.py:224 from_full_dict`
Same pattern as 2a. Replace `tp2=d.get("tp2", 0.0)` with None-preserving expression.

### 2c. `backend/notifications/__init__.py:106-125`
Widen signature + format guard:
```python
def notify_position_opened(
    self,
    symbol: str,
    direction: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: Optional[float],  # widened
    size: float,
) -> None:
    ...
    tp2_str = f"`{tp2:.4f}`" if tp2 is not None else "`NONE`"
    text = (
        f"{emoji} *Yeni pozisyon: {symbol} {direction}*\n"
        f"Entry: `{entry:.4f}`  Size: `{size}`\n"
        f"SL: `{sl:.4f}`  TP1: `{tp1:.4f}`  TP2: {tp2_str}"
    )
```

## 3. Inert today

All 3 fixes target paths that only fire when `tp2=None` exists. v2 entry path (`_place_v2_entry_order`) still rejects `tp2=None`. So today these branches are unreachable. They become live the moment PR #S6 removes the rejection.

## 4. Tests

### 4a. State-reload roundtrip
- `test_lifecycle_from_full_dict_preserves_tp2_none` — set tp2=None, save, load, assert tp2 is None
- `test_lifecycle_from_full_dict_legacy_numeric_unchanged` — regression: numeric tp2 still loads as float
- `test_lifecycle_from_full_dict_missing_key_defaults_to_zero` — backward-compat for pre-PR-#S5 state

### 4b. Orchestrator legacy compact reload
- `test_safe_orchestrator_legacy_compact_restore_preserves_tp2_none` — same shape, orchestrator path

### 4c. Notifications
- `test_notify_position_opened_with_tp2_none_does_not_crash`
- `test_notify_position_opened_with_tp2_none_message_contains_none_marker`
- `test_notify_position_opened_with_tp2_numeric_unchanged`

## 5. Acceptance

- 7+ new tests green
- Full backend suite: 666 + 7 = 673 expected
- Zero regression on existing lifecycle / orchestrator / notifications tests
- Hermes pre-approved scope; risk-ops gate REQUIRED (state file rehydration touches Position dataclass restoration semantics)

## 6. Out of scope

- `engine/report.py:163/175` (Scenario.tp2/Signal.tp2 — defer until those dataclasses widen)
- `safe_orchestrator.py:941` (same — Signal-typed)
- Any new config / flag changes (those are PR #S6)
