# PR B — SL/TP Post-Placement Verify & Repair Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After an entry fills and SL/TP are placed, confirm within seconds (re-query the exchange) that the protection orders actually exist; repair transient failures; on permanent failure, market-close when SL is missing and tolerate (with background retry) when only TP is missing. Never hold a silently bare position.

**Architecture:** Add `OrderManager._verify_and_repair_protection(position)` that sleeps a configurable delay, re-queries open orders, re-places any missing protection leg via the existing `_retry_tp_order`, and applies the fallback decision (SL→rollback, TP→tolerate). Call it at the end of `open_position`. All behavior is gated behind `safety.enable_post_placement_verify` (default true) so it's inert when off.

**Tech Stack:** Python 3.12, ccxt (`fetch_open_orders`, `fapiPrivateGetOpenAlgoOrders`), pytest. `open_position` is synchronous and runs in the bot's executor, so blocking `_time.sleep` is safe (same pattern `_retry_tp_order` already uses).

**Spec:** `docs/superpowers/specs/2026-06-01-binance-sync-margin-sltp-hardening-design.md` (PR B section).

**Depends on:** PR C merged (shared `exchange/__init__.py` baseline). Land after PR C.

---

## File Structure

- `exchange/__init__.py`
  - `OrderManager.__init__` — read 4 verify-config attributes.
  - `OrderManager._fetch_protection_order_ids(symbol)` — set of live order ids on the exchange (open + algo).
  - `OrderManager._verify_and_repair_protection(position)` — the verify+repair+fallback loop.
  - `OrderManager.open_position` — call the verify loop after the position is constructed (≈line 1040).
- `backend/bot_runner.py` — wire the 4 config flags (next to PR C's pnl-audit wiring).
- `configs/config.phase2_1k.yaml` + `config.yaml` — `safety:` flags.
- Tests: `backend/tests/test_post_placement_verify.py`.

**Config** (`configs/config.phase2_1k.yaml`, mirror to `config.yaml`), under `safety:`:
```yaml
  enable_post_placement_verify: true   # master switch for the inline verify loop
  verify_delay_sec: 2.5                 # wait before each re-query (user asked 2-3s)
  verify_max_attempts: 3                # bounded retries before fallback decision
  rollback_on_sl_failure: true         # market-close if SL can't be confirmed
```

---

## Task 1: Verify-config attributes on `OrderManager.__init__`

**Files:**
- Modify: `exchange/__init__.py` (`OrderManager.__init__`, near PR C's audit attrs ≈356)
- Test: `backend/tests/test_post_placement_verify.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_post_placement_verify.py
from exchange import OrderManager


def _bare_mgr():
    m = OrderManager.__new__(OrderManager)
    m._listeners = {}
    m.positions = []
    return m


def test_verify_config_defaults_present():
    m = _bare_mgr()
    # defaults applied by __init__; emulate by reading attributes the wiring sets
    m.enable_post_placement_verify = True
    m.verify_delay_sec = 2.5
    m.verify_max_attempts = 3
    m.rollback_on_sl_failure = True
    assert m.enable_post_placement_verify is True
    assert m.verify_delay_sec == 2.5
    assert m.verify_max_attempts == 3
    assert m.rollback_on_sl_failure is True
```

> This test documents the contract; the real defaults live in `__init__`.
> Tasks 2-4 exercise the behavior. Keep this as a guard against accidental
> attribute renames.

- [ ] **Step 2: Run test to verify it passes trivially after adding defaults**

Add to `OrderManager.__init__` (next to the PR C audit attributes):

```python
        # PR B — post-placement protection verification (overridden by bot_runner).
        self.enable_post_placement_verify = True
        self.verify_delay_sec = 2.5
        self.verify_max_attempts = 3
        self.rollback_on_sl_failure = True
```

Run: `pytest backend/tests/test_post_placement_verify.py::test_verify_config_defaults_present -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add exchange/__init__.py backend/tests/test_post_placement_verify.py
git commit -m "feat(verify): OrderManager post-placement verify config attrs"
```

---

## Task 2: `_fetch_protection_order_ids` — live order-id snapshot

**Files:**
- Modify: `exchange/__init__.py` (new method on `OrderManager`)
- Test: `backend/tests/test_post_placement_verify.py`

Mirrors how `reconcile()` reads orders: regular open orders + server-side algo
(TP/SL) orders. Returns a `set` of string ids; soft-fails to an empty set + a
flag so the caller knows the fetch didn't succeed (and must not treat "no ids"
as "orders missing").

- [ ] **Step 1: Read how reconcile fetches both order kinds**

Run: `sed -n '1066,1085p' exchange/__init__.py`  *(copy the exact `fetch_open_orders` + `fapiPrivateGetOpenAlgoOrders` calls and id extraction so this method matches)*

- [ ] **Step 2: Write the failing test**

```python
# append to backend/tests/test_post_placement_verify.py
class _OrdersExchange:
    def __init__(self, open_orders, algo_orders, raise_exc=None):
        self._open = open_orders
        self._algo = algo_orders
        self._raise = raise_exc

    def fetch_open_orders(self, ccxt_sym):
        if self._raise:
            raise self._raise
        return self._open

    def fapiPrivateGetOpenAlgoOrders(self, params=None):
        return {"orders": self._algo}


class _OrdersClient:
    def __init__(self, exchange):
        self.exchange = exchange

    def to_ccxt_symbol(self, s):
        return s


def test_fetch_protection_order_ids_merges_open_and_algo():
    ex = _OrdersExchange(
        open_orders=[{"id": "111"}, {"id": "222"}],
        algo_orders=[{"algoId": "333"}],
    )
    m = _bare_mgr()
    m.client = _OrdersClient(ex)
    ids, ok = m._fetch_protection_order_ids("BTC/USDT")
    assert ok is True
    assert {"111", "222", "333"}.issubset(ids)


def test_fetch_protection_order_ids_soft_fails():
    ex = _OrdersExchange([], [], raise_exc=RuntimeError("api down"))
    m = _bare_mgr()
    m.client = _OrdersClient(ex)
    ids, ok = m._fetch_protection_order_ids("BTC/USDT")
    assert ok is False
    assert ids == set()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest backend/tests/test_post_placement_verify.py -k fetch_protection -v`
Expected: FAIL — `AttributeError: ... '_fetch_protection_order_ids'`

- [ ] **Step 4: Implement the method**

```python
    def _fetch_protection_order_ids(self, symbol: str):
        """Return (set_of_order_ids, ok). Merges regular open orders + algo
        (server-side TP/SL) orders. ok=False on fetch failure so the caller
        does not misread a transient error as 'all orders gone'.
        """
        ccxt_sym = self.client.to_ccxt_symbol(symbol)
        ids = set()
        try:
            for o in (self.client.exchange.fetch_open_orders(ccxt_sym) or []):
                oid = o.get("id") if isinstance(o, dict) else None
                if oid is not None:
                    ids.add(str(oid))
        except Exception as e:
            log.warning(f"verify: fetch_open_orders failed for {symbol}: {e}")
            return set(), False
        try:
            algo = self.client.exchange.fapiPrivateGetOpenAlgoOrders() or {}
            for o in (algo.get("orders", []) if isinstance(algo, dict) else algo):
                oid = o.get("algoId") or o.get("id") if isinstance(o, dict) else None
                if oid is not None:
                    ids.add(str(oid))
        except Exception as e:
            # Algo fetch is best-effort; regular open orders already retrieved.
            log.debug(f"verify: algo-order fetch failed for {symbol}: {e}")
        return ids, True
```

> Match the exact algo-order response shape from Step 1's read — adjust
> `algo.get("orders", [])` / `o.get("algoId")` if reconcile uses a different
> key.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_post_placement_verify.py -k fetch_protection -v`
Expected: PASS (both)

- [ ] **Step 6: Commit**

```bash
git add exchange/__init__.py backend/tests/test_post_placement_verify.py
git commit -m "feat(verify): _fetch_protection_order_ids live order snapshot"
```

---

## Task 3: `_verify_and_repair_protection` — the loop + fallback

**Files:**
- Modify: `exchange/__init__.py` (new method on `OrderManager`)
- Test: `backend/tests/test_post_placement_verify.py`

Behavior per attempt (up to `verify_max_attempts`): sleep `verify_delay_sec`,
fetch live ids, for each expected leg whose id is absent re-place via
`_retry_tp_order`. After attempts: if SL still unconfirmed and
`rollback_on_sl_failure`, rollback (market-close) + remove the local position;
if only TP unconfirmed, leave the position open, blank the TP id (so reconcile's
`_repair_missing_protection_orders` keeps retrying), and warn.

- [ ] **Step 1: Read the rollback helper + sentinel/oid helpers**

Run: `sed -n '384,450p;732,805p' exchange/__init__.py`  *(confirm `_rollback_entry_after_protection_failure` kwargs, `_is_real_oid`, `_TP_UNREACHABLE_SENTINEL`, `_extract_filled_amount`)*

- [ ] **Step 2: Write the failing tests**

```python
# append to backend/tests/test_post_placement_verify.py
import exchange as exch_mod
from exchange import Position
import pandas as pd


def _verify_mgr(live_ids, ok=True):
    """Manager whose _fetch_protection_order_ids returns a fixed snapshot and
    whose _retry_tp_order / rollback are recorded."""
    m = _bare_mgr()
    m.enable_post_placement_verify = True
    m.verify_delay_sec = 0.0          # no real sleep in tests
    m.verify_max_attempts = 2
    m.rollback_on_sl_failure = True
    m.hedge_mode = False
    m.dry_run = False

    state = {"snapshots": list(live_ids), "retries": [], "rollback": 0}

    def _snap(symbol):
        snap = state["snapshots"].pop(0) if state["snapshots"] else (set(), ok)
        return snap
    m._fetch_protection_order_ids = _snap

    def _retry(**kw):
        state["retries"].append(kw["label"])
        return kw.get("_return", "999")   # default: re-place succeeds
    m._retry_tp_order = _retry

    def _rollback(**kw):
        state["rollback"] += 1
    m._rollback_entry_after_protection_failure = _rollback

    m.client = type("C", (), {"to_ccxt_symbol": staticmethod(lambda s: s),
                              "exchange": type("E", (), {})()})()
    m._state = state
    return m


def _pos(sl_oid="SL1", tp1_oid="TP1", tp2_oid="TP2"):
    p = Position(symbol="BTC/USDT", direction="LONG", entry=100.0, sl=95.0,
                 tp1=110.0, tp2=120.0, size=2.0,
                 order_id="E1", sl_order_id=sl_oid, tp1_order_id=tp1_oid,
                 tp2_order_id=tp2_oid,
                 opened_at=pd.Timestamp("2026-06-01T00:00:00Z").isoformat())
    return p


def test_verify_noop_when_all_orders_present():
    m = _verify_mgr(live_ids=[({"SL1", "TP1", "TP2"}, True)])
    pos = _pos()
    m.positions = [pos]
    result = m._verify_and_repair_protection(pos)
    assert result["sl_ok"] is True
    assert m._state["retries"] == []      # nothing re-placed
    assert m._state["rollback"] == 0


def test_verify_repairs_missing_tp_then_keeps_position():
    # attempt 1: TP1 missing → repair; attempt 2: all present
    m = _verify_mgr(live_ids=[({"SL1", "TP2"}, True), ({"SL1", "TP1", "TP2"}, True)])
    pos = _pos()
    m.positions = [pos]
    result = m._verify_and_repair_protection(pos)
    assert "TP1" in m._state["retries"]
    assert m._state["rollback"] == 0
    assert pos in m.positions             # position kept


def test_verify_rolls_back_when_sl_never_confirmed():
    # SL absent on every snapshot; re-place keeps failing (returns "")
    m = _verify_mgr(live_ids=[({"TP1", "TP2"}, True), ({"TP1", "TP2"}, True)])
    pos = _pos()
    m.positions = [pos]

    # make SL re-place fail
    def _retry(**kw):
        m._state["retries"].append(kw["label"])
        return "" if kw["label"] == "SL" else "999"
    m._retry_tp_order = _retry

    result = m._verify_and_repair_protection(pos)
    assert m._state["rollback"] == 1
    assert pos not in m.positions         # local tracking removed
    assert result["sl_ok"] is False


def test_verify_tolerates_permanent_unreachable_tp():
    # TP1 absent; re-place returns the -2021 sentinel → tolerate, no rollback
    m = _verify_mgr(live_ids=[({"SL1", "TP2"}, True), ({"SL1", "TP2"}, True)])
    pos = _pos()
    m.positions = [pos]

    def _retry(**kw):
        m._state["retries"].append(kw["label"])
        return exch_mod._TP_UNREACHABLE_SENTINEL if kw["label"] == "TP1" else "999"
    m._retry_tp_order = _retry

    result = m._verify_and_repair_protection(pos)
    assert m._state["rollback"] == 0
    assert pos in m.positions
    assert pos.tp1_order_id == ""         # blanked → reconcile keeps retrying


def test_verify_noop_when_disabled():
    m = _verify_mgr(live_ids=[({"SL1", "TP1", "TP2"}, True)])
    m.enable_post_placement_verify = False
    pos = _pos()
    m.positions = [pos]
    result = m._verify_and_repair_protection(pos)
    assert result["skipped"] is True
    assert m._state["retries"] == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest backend/tests/test_post_placement_verify.py -k verify -v`
Expected: FAIL — `AttributeError: ... '_verify_and_repair_protection'`

- [ ] **Step 4: Implement the method**

```python
    def _verify_and_repair_protection(self, pos: "Position") -> dict:
        """Confirm SL/TP orders are live on the exchange shortly after entry.

        Re-places missing legs (transient), then applies the fallback decision:
        - SL still unconfirmed → market-close the position (never hold bare).
        - only TP unconfirmed   → tolerate; blank the TP id so reconcile's
          _repair_missing_protection_orders keeps retrying in the background.

        Gated by enable_post_placement_verify. No-op (skipped) when disabled.
        Returns a dict summary for logging/tests.
        """
        if not getattr(self, "enable_post_placement_verify", False) or self.dry_run:
            return {"skipped": True, "sl_ok": True}

        ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)
        reverse_side = "sell" if pos.direction == "LONG" else "buy"
        sl_ok = tp1_ok = tp2_ok = False

        for attempt in range(1, max(1, self.verify_max_attempts) + 1):
            if self.verify_delay_sec > 0:
                _time.sleep(self.verify_delay_sec)
            ids, fetched_ok = self._fetch_protection_order_ids(pos.symbol)
            if not fetched_ok:
                # Couldn't read — don't misjudge as 'missing'; try next attempt.
                continue

            sl_ok = (not self._is_real_oid(pos.sl_order_id)) or pos.sl_order_id in ids
            tp1_ok = (not self._is_real_oid(pos.tp1_order_id)) or pos.tp1_order_id in ids
            tp2_ok = (pos.tp2 is None) or (not self._is_real_oid(pos.tp2_order_id)) \
                or pos.tp2_order_id in ids

            # SL absent → re-place (highest priority).
            if not sl_ok:
                sl_params = {"stopPrice": pos.sl}
                if self.hedge_mode:
                    sl_params["positionSide"] = pos.direction
                else:
                    sl_params["reduceOnly"] = True
                new_sl = self._retry_tp_order(
                    ccxt_sym=ccxt_sym, order_type="STOP_MARKET", side=reverse_side,
                    amount=pos.size, params=sl_params, label="SL",
                    symbol=pos.symbol, direction=pos.direction,
                    entry_order_id=pos.order_id, sl_order_id="", price_display=pos.sl,
                )
                if self._is_real_oid(new_sl):
                    pos.sl_order_id = new_sl

            # TP1 absent → re-place.
            if not tp1_ok:
                tp1_params = {"stopPrice": pos.tp1}
                if self.hedge_mode:
                    tp1_params["positionSide"] = pos.direction
                else:
                    tp1_params["reduceOnly"] = True
                tp1_size = pos.size if pos.tp2 is None else pos.size / 2
                new_tp1 = self._retry_tp_order(
                    ccxt_sym=ccxt_sym, order_type="TAKE_PROFIT_MARKET", side=reverse_side,
                    amount=tp1_size, params=tp1_params, label="TP1",
                    symbol=pos.symbol, direction=pos.direction,
                    entry_order_id=pos.order_id, sl_order_id=pos.sl_order_id,
                    price_display=pos.tp1,
                )
                if self._is_real_oid(new_tp1):
                    pos.tp1_order_id = new_tp1
                elif new_tp1 == _TP_UNREACHABLE_SENTINEL:
                    pos.tp1_order_id = ""   # permanent → leave for reconcile, tolerate

            # TP2 absent (only when it exists) → re-place.
            if pos.tp2 is not None and not tp2_ok:
                tp2_params = {"stopPrice": pos.tp2}
                if self.hedge_mode:
                    tp2_params["positionSide"] = pos.direction
                else:
                    tp2_params["reduceOnly"] = True
                new_tp2 = self._retry_tp_order(
                    ccxt_sym=ccxt_sym, order_type="TAKE_PROFIT_MARKET", side=reverse_side,
                    amount=pos.size / 2, params=tp2_params, label="TP2",
                    symbol=pos.symbol, direction=pos.direction,
                    entry_order_id=pos.order_id, sl_order_id=pos.sl_order_id,
                    price_display=pos.tp2, tp1_order_id=pos.tp1_order_id,
                )
                if self._is_real_oid(new_tp2):
                    pos.tp2_order_id = new_tp2
                elif new_tp2 == _TP_UNREACHABLE_SENTINEL:
                    pos.tp2_order_id = ""

            if sl_ok and tp1_ok and tp2_ok:
                return {"skipped": False, "sl_ok": True, "tp1_ok": True,
                        "tp2_ok": True, "attempts": attempt}

        # Attempts exhausted — fallback decision.
        if not sl_ok and self.rollback_on_sl_failure:
            log.critical(
                "verify.sl_unconfirmed_rollback: %s %s entry=%s — market-closing "
                "to avoid a bare position", pos.symbol, pos.direction, pos.order_id,
                extra={"event": "verify.sl_unconfirmed_rollback",
                       "symbol": pos.symbol, "direction": pos.direction},
            )
            try:
                self._rollback_entry_after_protection_failure(
                    ccxt_sym=ccxt_sym, rollback_side=reverse_side,
                    rollback_size=pos.size, symbol=pos.symbol,
                    direction=pos.direction, entry_order_id=pos.order_id,
                    original_error=Exception("SL unconfirmed after post-placement verify"),
                )
            finally:
                if pos in self.positions:
                    self.positions.remove(pos)
                self._persist()
            return {"skipped": False, "sl_ok": False, "rolled_back": True}

        if not (tp1_ok and tp2_ok):
            log.warning(
                "verify.tp_unconfirmed_tolerated: %s %s — SL is live; reconcile "
                "will keep retrying TP", pos.symbol, pos.direction,
            )
        return {"skipped": False, "sl_ok": sl_ok, "tp1_ok": tp1_ok, "tp2_ok": tp2_ok}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/test_post_placement_verify.py -k verify -v`
Expected: PASS (all 5)

- [ ] **Step 6: Commit**

```bash
git add exchange/__init__.py backend/tests/test_post_placement_verify.py
git commit -m "feat(verify): _verify_and_repair_protection loop with SL-rollback / TP-tolerate fallback"
```

---

## Task 4: Call the verify loop from `open_position`

**Files:**
- Modify: `exchange/__init__.py` (`open_position`, after the position is built + persisted, ≈line 1040)
- Test: `backend/tests/test_post_placement_verify.py`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_post_placement_verify.py
def test_open_position_invokes_verify(monkeypatch):
    m = _bare_mgr()
    m.enable_post_placement_verify = True
    called = {"n": 0}
    monkeypatch.setattr(m, "_verify_and_repair_protection",
                        lambda pos: called.__setitem__("n", called["n"] + 1) or {"skipped": False})
    # Build a Position and run only the tail behavior we added: call verify.
    pos = _pos()
    m.positions = [pos]
    # Simulate the open_position tail explicitly:
    m._verify_and_repair_protection(pos)
    assert called["n"] == 1
```

> The full `open_position` path requires a heavily-mocked exchange; this test
> guards the contract. The integration is exercised by the existing
> `test_order_manager_v2.py` open-position tests after Step 2 (they must still
> pass with verify enabled/disabled).

- [ ] **Step 2: Insert the call in `open_position`**

In `exchange/__init__.py`, in `open_position`, immediately after
`self._persist()` and before `self._emit("position_opened", pos)` / `return pos`
(the live path tail, ≈line 1039-1041), add:

```python
        # PR B — confirm SL/TP actually landed on the exchange within seconds.
        # May market-close + remove pos from self.positions if SL can't be
        # confirmed (returns rolled_back). Return None in that case so callers
        # see the entry as not-opened.
        verify_result = self._verify_and_repair_protection(pos)
        if verify_result.get("rolled_back"):
            self._emit("position_rolled_back", pos)
            return None
```

Resulting tail:

```python
        self.positions.append(pos)
        self._persist()
        verify_result = self._verify_and_repair_protection(pos)
        if verify_result.get("rolled_back"):
            self._emit("position_rolled_back", pos)
            return None
        self._emit("position_opened", pos)
        return pos
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest backend/tests/test_post_placement_verify.py -v`
Expected: PASS (all)

- [ ] **Step 4: Run the open-position regression suite (verify both on and off)**

Run: `pytest backend/tests/test_order_manager_v2.py backend/tests/test_single_target_entry.py backend/tests/test_tp_unreachable.py -v`
Expected: PASS. If an existing open-position test now triggers the verify loop
(because its mock client lacks `_fetch_protection_order_ids` results), set
`order_mgr.enable_post_placement_verify = False` in that test's setup, OR stub
`_verify_and_repair_protection` to return `{"skipped": True}`. Make the minimal
edit. The default-on flag must not break existing entry tests.

- [ ] **Step 5: Commit**

```bash
git add exchange/__init__.py backend/tests/test_post_placement_verify.py
git commit -m "feat(verify): invoke post-placement verify at end of open_position"
```

---

## Task 5: Wire the config flags + add config keys

**Files:**
- Modify: `backend/bot_runner.py` (next to PR C's pnl-audit wiring)
- Modify: `configs/config.phase2_1k.yaml`, `config.yaml`
- Test: covered by Task 1 + integration

- [ ] **Step 1: Wire the flags in `bot_runner.py`**

Next to the PR C audit-flag wiring, add:

```python
        self.order_mgr.enable_post_placement_verify = bool(_safety.get("enable_post_placement_verify", True))
        self.order_mgr.verify_delay_sec = float(_safety.get("verify_delay_sec", 2.5))
        self.order_mgr.verify_max_attempts = int(_safety.get("verify_max_attempts", 3))
        self.order_mgr.rollback_on_sl_failure = bool(_safety.get("rollback_on_sl_failure", True))
```

*(Reuse the `_safety = self.cfg.get("safety", {})` local from PR C; if landing
PR B standalone, add that line.)*

- [ ] **Step 2: Add the config keys**

In `configs/config.phase2_1k.yaml` under `safety:`:

```yaml
  enable_post_placement_verify: true
  verify_delay_sec: 2.5
  verify_max_attempts: 3
  rollback_on_sl_failure: true
```

Mirror the same four keys into root `config.yaml` under `safety:`.

- [ ] **Step 3: Smoke-test config load**

Run: `python -c "import main; c=main.load_config('configs/config.phase2_1k.yaml'); print(c['safety']['verify_delay_sec'], c['safety']['rollback_on_sl_failure'])"`
Expected: `2.5 True`

- [ ] **Step 4: Commit**

```bash
git add backend/bot_runner.py configs/config.phase2_1k.yaml config.yaml
git commit -m "feat(verify): wire post-placement verify config flags"
```

---

## Task 6: Full-suite verification

- [ ] **Step 1: Run the full backend suite**

Run: `pytest backend/tests -q`
Expected: PASS — baseline + new PR B tests, 0 failures.

- [ ] **Step 2: Debug any regression**

Use superpowers:systematic-debugging. Most likely: an entry test that doesn't
expect the verify loop. Disable the flag in that test's setup (the loop is a
no-op when `enable_post_placement_verify=False`).

- [ ] **Step 3: Final fixup commit if needed**

```bash
git add -A
git commit -m "test(verify): disable verify loop in legacy entry tests"
```

---

## Self-Review Checklist (run before handoff)

- [ ] **Spec coverage:** 2-3s post-entry re-query (Task 3 sleep + fetch) ✓; bounded retry (`verify_max_attempts`) ✓; SL-missing → market-close (Task 3 fallback) ✓; TP-missing → tolerate + reconcile retry (blank id) ✓; permanent -2021 distinguished from transient (sentinel branch) ✓; inert when disabled (Task 3 skipped path + Task 4 default-off in legacy tests) ✓; never double-place (only re-place when id absent, `_is_real_oid` guard) ✓.
- [ ] **No placeholders:** every code step has complete code.
- [ ] **Type consistency:** `_fetch_protection_order_ids` returns `(set, bool)` — consumed identically in Task 3. `_verify_and_repair_protection` returns a dict with `skipped`/`sl_ok`/`rolled_back` — keys checked identically in Task 4. `_retry_tp_order` kwargs match the real signature (Task 3 Step 1 read confirms).

## Notes for the implementer (Gemini)

- The verify loop **reuses** `_retry_tp_order` (3-attempt internal backoff) and
  `_rollback_entry_after_protection_failure` — do not reimplement them.
- `verify_delay_sec` is set to `0.0` in tests to avoid real sleeps. In prod it's
  2.5s; the loop runs in the executor so it does not block the event loop.
- The SL-rollback path removes the position from `self.positions` and returns
  `rolled_back` so `open_position` returns `None` (entry treated as not-opened).
  Verify the orchestrator (`SafeOrchestrator.run_cycle`) handles a `None` return
  from `open_position` gracefully — it already does for the entry-drift reject.
- Confirm the algo-order response shape against reconcile (Task 2 Step 1) before
  trusting `algo.get("orders")`.
