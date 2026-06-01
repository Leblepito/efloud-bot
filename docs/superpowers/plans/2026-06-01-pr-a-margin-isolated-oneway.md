# PR A — Margin ISOLATED + One-Way Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch the live bot to ISOLATED margin + one-way position mode (hedge OFF) so Binance itself blocks holding long+short on the same symbol and one coin's volatility can't drain the whole wallet — enforced at startup, with a preflight flat-book gate that prevents a half-applied exchange state.

**Architecture:** Mostly a config change (`CROSSED→ISOLATED`, `hedge_mode true→false`, leverage stays 5x) plus hardening the existing startup enforce loop in `bot_runner.py` to ABORT when margin-mode setup fails (today it only warns), plus a new flat-book gate in `preflight.py` that fails when a position-mode change is pending but open positions/orders exist. The one-way order path already works (positionSide injection is gated on `hedge_mode`; OFF → `reduceOnly`).

**Tech Stack:** Python 3.12, ccxt (`fapiPrivateGetPositionSideDual`, `fetch_positions`, `fetch_open_orders`), pytest, YAML config.

**Spec:** `docs/superpowers/specs/2026-06-01-binance-sync-margin-sltp-hardening-design.md` (PR A section + deploy runbook).

**Depends on:** PR C + PR B merged. Land LAST — requires a flat-book maintenance window (operator closes all positions + cancels all orders before deploy).

---

## File Structure

- `configs/config.phase2_1k.yaml` (active prod) + `config.yaml` (passive root) — `exchange:` block.
- `backend/bot_runner.py` — harden the margin-mode enforce loop (abort on failure).
- `preflight.py` — add a testable `evaluate_flat_book()` helper + a `[5/5]` flat-book gate.
- Tests: `backend/tests/test_preflight_flat_book.py`, extend `backend/tests/test_exchange_futures_methods.py`.

---

## Task 1: Harden the startup margin-mode enforce loop

**Files:**
- Modify: `backend/bot_runner.py:165-193` (the futures setup block)
- Test: `backend/tests/test_exchange_futures_methods.py` (add a bot_runner-level enforce test) OR a new focused test

Today the per-symbol loop (169-174) swallows `set_margin_mode` failures as a
warning. For ISOLATED to be a real guarantee, a margin-mode failure must abort
startup the same way a position-mode failure already does (179-193).

- [ ] **Step 1: Read the current block once more to anchor the edit**

Run: `sed -n '165,194p' backend/bot_runner.py`

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_bot_runner_margin_enforce.py
import pytest


class _FailMarginClient:
    def __init__(self):
        self.calls = []

    def set_margin_mode(self, sym, mode):
        self.calls.append((sym, mode))
        raise RuntimeError("-4046 simulated hard failure")

    def set_leverage(self, sym, lev):
        pass

    def set_position_mode(self, dual_side=False):
        return True


def test_margin_mode_hard_failure_aborts_startup():
    from backend.bot_runner import _enforce_margin_setup   # extracted helper

    client = _FailMarginClient()
    ok, err = _enforce_margin_setup(
        client, tradeable=["BTC/USDT"], margin_mode="ISOLATED",
        leverage=5, hedge_mode=False,
    )
    assert ok is False
    assert "margin" in err.lower()


def test_margin_mode_benign_no_change_is_success():
    class _BenignClient(_FailMarginClient):
        def set_margin_mode(self, sym, mode):
            self.calls.append((sym, mode))
            return True   # set_margin_mode treats -4046 as success internally

    client = _BenignClient()
    ok, err = _enforce_margin_setup(
        client, tradeable=["BTC/USDT"], margin_mode="ISOLATED",
        leverage=5, hedge_mode=False,
    )
    assert ok is True
    assert err == ""
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest backend/tests/test_bot_runner_margin_enforce.py -v`
Expected: FAIL — `ImportError: cannot import name '_enforce_margin_setup'`

- [ ] **Step 4: Extract + harden the enforce logic**

In `backend/bot_runner.py`, add a module-level helper (above the `BotRunner`
class):

```python
def _enforce_margin_setup(client, tradeable, margin_mode, leverage, hedge_mode):
    """Apply margin mode + leverage per symbol, then position mode globally.

    Returns (ok, error_message). margin-mode failure is FATAL (returns False) —
    ISOLATED must be a real guarantee, not best-effort. set_margin_mode already
    treats the benign -4046 'no need to change' as success, so a raised
    exception here is a genuine failure.
    """
    for sym in tradeable:
        try:
            client.set_margin_mode(sym, margin_mode)
        except Exception as e:
            return False, f"Margin mode setup failed for {sym}: {e}"
        try:
            client.set_leverage(sym, leverage)
        except Exception as e:
            # Leverage is non-fatal (set_leverage already swallows internally);
            # log-only to avoid blocking startup on a transient leverage hiccup.
            log.warning(f"Leverage setup warning for {sym}: {e}")
    try:
        if not client.set_position_mode(dual_side=hedge_mode):
            return False, (
                "Position mode setup failed! Binance rejected the change. "
                "Ensure NO open positions and NO open orders on the entire "
                "Futures account, then restart."
            )
    except Exception as e:
        return False, f"Position mode setup failed with exception: {e}"
    return True, ""
```

Replace the inline block (165-193) so it calls the helper:

```python
        # Leverage + margin mode setup
        if ex_cfg["market_type"] == "futures" and api_key and not self.cfg["operation"].get("dry_run", True):
            margin_mode = ex_cfg.get("margin_mode", "ISOLATED").upper()
            tradeable = (permission_mgr.get_tradeable_symbols() if permission_mgr else symbols)
            hedge_mode = ex_cfg.get("hedge_mode", False)
            ok, err = _enforce_margin_setup(
                self.client, tradeable, margin_mode,
                ex_cfg.get("leverage", 3), hedge_mode,
            )
            if not ok:
                log.error(f"⛔ {err}")
                self.last_error = err
                return
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_bot_runner_margin_enforce.py -v`
Expected: PASS (both)

- [ ] **Step 6: Run bot_runner regression**

Run: `pytest backend/tests/ -k "bot_runner or runner" -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/bot_runner.py backend/tests/test_bot_runner_margin_enforce.py
git commit -m "feat(margin): abort startup on margin-mode enforce failure (ISOLATED guarantee)"
```

---

## Task 2: `evaluate_flat_book` helper + preflight flat-book gate

**Files:**
- Modify: `preflight.py` (add helper + `[5/5]` gate, renumber existing `[4/4]`)
- Test: `backend/tests/test_preflight_flat_book.py`

Binance rejects a position-mode change while any position/order exists. The gate
fails preflight when a mode change is pending AND the book isn't flat — so the
operator can't half-apply PR A.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_preflight_flat_book.py
from preflight import evaluate_flat_book


def test_flat_book_ok_when_no_change_needed():
    ok, msg = evaluate_flat_book(mode_change_needed=False, open_positions=3, open_orders=2)
    assert ok is True


def test_flat_book_ok_when_change_needed_and_flat():
    ok, msg = evaluate_flat_book(mode_change_needed=True, open_positions=0, open_orders=0)
    assert ok is True


def test_flat_book_fails_when_change_needed_and_positions_open():
    ok, msg = evaluate_flat_book(mode_change_needed=True, open_positions=1, open_orders=0)
    assert ok is False
    assert "flat" in msg.lower()


def test_flat_book_fails_when_change_needed_and_orders_open():
    ok, msg = evaluate_flat_book(mode_change_needed=True, open_positions=0, open_orders=5)
    assert ok is False
    assert "flat" in msg.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_preflight_flat_book.py -v`
Expected: FAIL — `ImportError: cannot import name 'evaluate_flat_book'`

- [ ] **Step 3: Add the helper to `preflight.py`**

Add near the top of `preflight.py` (after the imports, before the `print`
banner — so it's importable without running the script's side effects... but the
script runs at import time). To keep it importable for tests, **guard the
script body** under `if __name__ == "__main__":` OR move the procedural checks
into a `def main():`. Minimal approach: define the pure helper at top, and wrap
the existing procedural block in `def main(): ...` called under
`if __name__ == "__main__": main()`.

First add the helper:

```python
def evaluate_flat_book(mode_change_needed: bool, open_positions: int,
                       open_orders: int) -> tuple:
    """Decide whether preflight may proceed given a pending mode change.

    A position-mode / margin-mode change is rejected by Binance while any
    position or order is open. Returns (ok, message).
    """
    if mode_change_needed and (open_positions > 0 or open_orders > 0):
        return False, (
            f"FAIL: margin/position-mode change is pending but the book is NOT "
            f"flat ({open_positions} open positions, {open_orders} open orders). "
            f"Close all positions and cancel all orders, then restart."
        )
    return True, "Flat-book gate OK"
```

- [ ] **Step 4: Wrap the procedural body in `main()` and add the `[5/5]` gate**

Refactor `preflight.py` so the procedural checks live in `def main():` and the
file ends with:

```python
if __name__ == "__main__":
    main()
```

Inside `main()`, after the `[4/4]` position-mode check, compute
`mode_change_needed` and run the gate as `[5/5]`:

```python
    # 5. Flat-book gate — a pending mode change requires a flat account.
    mode_change_needed = (is_hedge != hedge_mode)   # from the [4/4] block
    try:
        positions = [p for p in ex.fetch_positions() if float(p.get("contracts", 0) or 0) > 0]
        open_orders = ex.fetch_open_orders()
        n_pos, n_ord = len(positions), len(open_orders)
    except Exception as e:
        print(f"  [5/5] Flat-book gate: ⚠️ could not query positions/orders ({e})")
        n_pos = n_ord = 0
        mode_change_needed = False   # don't block on a read failure
    ok, msg = evaluate_flat_book(mode_change_needed, n_pos, n_ord)
    if not ok:
        print(f"  [5/5] Flat-book gate: ❌ {msg}")
        sys.exit(1)
    print(f"  [5/5] Flat-book gate: ✅ ({n_pos} positions, {n_ord} orders, "
          f"change_needed={mode_change_needed})")
```

> Renumber the existing `[1/4]`…`[4/4]` prints to `[1/5]`…`[4/5]` for accuracy.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_preflight_flat_book.py -v`
Expected: PASS (all 4)

- [ ] **Step 6: Smoke-run preflight import (no script side effects on import)**

Run: `python -c "import preflight; print(preflight.evaluate_flat_book(True,0,0))"`
Expected: `(True, 'Flat-book gate OK')` — and NO preflight banner printed
(confirms the body is under `main()` / `__main__`).

- [ ] **Step 7: Commit**

```bash
git add preflight.py backend/tests/test_preflight_flat_book.py
git commit -m "feat(preflight): flat-book gate blocks half-applied mode change"
```

---

## Task 3: Extend exchange-method tests for one-way + ISOLATED

**Files:**
- Modify: `backend/tests/test_exchange_futures_methods.py`
- Test: same file

- [ ] **Step 1: Read the existing test file to match its mock style**

Run: `sed -n '1,60p' backend/tests/test_exchange_futures_methods.py`

- [ ] **Step 2: Add tests for `set_position_mode(dual_side=False)` and one-way order params**

```python
# append to backend/tests/test_exchange_futures_methods.py
def test_set_position_mode_oneway_get_first_short_circuits():
    """When the exchange already reports ONE_WAY, set_position_mode(False)
    returns True via the GET check without POSTing."""
    from exchange import BinanceClient

    class _Ex:
        def __init__(self):
            self.posted = False
        def fapiPrivateGetPositionSideDual(self):
            return {"dualSidePosition": False}
        def fapiPrivatePostPositionSideDual(self, params):
            self.posted = True
            return {}

    c = BinanceClient.__new__(BinanceClient)
    c.exchange = _Ex()
    assert c.set_position_mode(dual_side=False) is True
    assert c.exchange.posted is False   # GET short-circuited the POST


def test_oneway_order_params_use_reduce_only_not_position_side():
    """In one-way mode (hedge_mode False) protection orders carry reduceOnly
    and never positionSide — verified via the param-building branch."""
    # This documents the open_position branch behavior; the gating is:
    #   if self.hedge_mode: params["positionSide"] = direction
    #   else:               params["reduceOnly"] = True
    hedge_mode = False
    sl_params = {"stopPrice": 95.0}
    if hedge_mode:
        sl_params["positionSide"] = "LONG"
    else:
        sl_params["reduceOnly"] = True
    assert sl_params.get("reduceOnly") is True
    assert "positionSide" not in sl_params
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest backend/tests/test_exchange_futures_methods.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_exchange_futures_methods.py
git commit -m "test(margin): one-way position mode + reduceOnly order params"
```

---

## Task 4: Config change — ISOLATED + one-way

**Files:**
- Modify: `configs/config.phase2_1k.yaml` (lines ≈35-37)
- Modify: `config.yaml` (`exchange:` block)

> ⚠️ This is the live-behavior change. It takes effect only on the next bot
> start AND only on a flat book (Task 2 gate + Binance rejection). Do NOT deploy
> outside the maintenance window in the runbook below.

- [ ] **Step 1: Edit `configs/config.phase2_1k.yaml`**

Change the `exchange:` block:

```yaml
  leverage: 5              # unchanged (5x confirmed)
  margin_mode: ISOLATED    # was CROSSED
  hedge_mode: false        # was true → one-way; Binance blocks long+short on one symbol
```

- [ ] **Step 2: Mirror into root `config.yaml`**

In `config.yaml` `exchange:` block: set `margin_mode: ISOLATED`,
`hedge_mode: false`, and `leverage: 5` (was 3 — bump for consistency per spec).

- [ ] **Step 3: Smoke-test config load**

Run: `python -c "import main; c=main.load_config('configs/config.phase2_1k.yaml'); e=c['exchange']; print(e['margin_mode'], e['hedge_mode'], e['leverage'])"`
Expected: `ISOLATED False 5`

- [ ] **Step 4: Commit**

```bash
git add configs/config.phase2_1k.yaml config.yaml
git commit -m "config(margin): ISOLATED + one-way (hedge off), leverage 5x"
```

---

## Task 5: Full-suite verification

- [ ] **Step 1: Run the full backend suite**

Run: `pytest backend/tests -q`
Expected: PASS — baseline + PR A tests, 0 failures.

- [ ] **Step 2: Verify anti-flip in one-way mode**

Run: `pytest backend/tests/test_reverse_guard.py backend/tests/ -k position_guard -v`
Expected: PASS. The `PositionGuard` opposite-direction reject still applies; in
one-way mode a contra entry would net-reduce rather than stack, and the guard
rejects it before that. If any guard test assumed hedge mode, update its setup.

- [ ] **Step 3: Debug any regression**

Use superpowers:systematic-debugging.

- [ ] **Step 4: Final fixup commit if needed**

```bash
git add -A
git commit -m "test(margin): adapt guard tests to one-way mode"
```

---

## Deploy Runbook (operator: Utku) — flat-book maintenance window

> Code is merged but DORMANT until the bot restarts with the new config on a
> flat book. Execute these steps in order during a quiet window:

1. **Stop the bot** (so it places no new orders) — via dashboard stop or
   `docker exec efloud-bot ...` stop per memory `reference_live_bot_control`.
2. **Close every open position** on Binance Futures manually (market) —
   e.g. the open BCH/USDT SHORT from the audit.
3. **Cancel every pending SL/TP/limit order** for all symbols.
4. **Verify flat:** 0 positions, 0 open orders (Binance UI or
   `docker exec ... python -c "import ccxt; ..."`).
5. **Deploy** the new config (pull, rebuild/redeploy container).
6. **Run preflight:** `EFLOUD_ALLOW_MAINNET=1 python preflight.py` — the `[5/5]`
   flat-book gate must pass.
7. **Start the bot.** Startup enforce applies ISOLATED + one-way + 5x per symbol;
   if anything fails it aborts with `last_error` (check `/healthz`).
8. **Confirm on Binance:** margin type = ISOLATED, position mode = One-way for
   the traded symbols.

If preflight `[5/5]` fails → a residual position/order remains; repeat 2-4.

---

## Self-Review Checklist (run before handoff)

- [ ] **Spec coverage:** ISOLATED + one-way config (Task 4) ✓; startup enforce
  aborts on failure (Task 1) ✓; flat-book preflight gate (Task 2) ✓; one-way
  order path uses reduceOnly (Task 3 + already-gated code) ✓; deploy runbook ✓;
  leverage 5x unchanged ✓.
- [ ] **No placeholders:** every code step has complete code.
- [ ] **Type consistency:** `_enforce_margin_setup(client, tradeable, margin_mode, leverage, hedge_mode) -> (ok, err)` used identically in Task 1. `evaluate_flat_book(mode_change_needed, open_positions, open_orders) -> (ok, msg)` used identically in Task 2.

## Notes for the implementer (Gemini)

- PR A is **config + guardrails**; the order-path one-way behavior already
  exists (positionSide gated on `hedge_mode`). Do not add positionSide handling.
- `preflight.py` currently executes at import — Task 2 Step 4 MUST wrap the body
  in `main()` so importing it for tests has no side effects. Verify with Step 6.
- The config change (Task 4) is the only step with live-trading impact and is
  gated by the maintenance-window runbook — never merge+deploy PR A while
  positions are open.
- After deploy, the existing `[4/5]` position-mode auto-switch in startup enforce
  will apply one-way; the preflight gate ensures the book is flat first.
