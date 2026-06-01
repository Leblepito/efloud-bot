# PR C — PnL Reconcile & Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local recorded PnL equal Binance's real net realized PnL (realizedPnl − commission − funding) for every closed position, and feed the reconciled figure to the dashboard.

**Architecture:** Add a `BinanceClient.fetch_realized_pnl()` that reads the USD-M income endpoint, store the result on the `Position` dataclass, wire it into `_record_close` (with soft-fail fallback to the existing estimate), add a periodic `audit_realized_pnl()` sweep driven from `reconcile()`, and add a journal-backed fallback for the DB-less dashboard `/history` and `/equity`.

**Tech Stack:** Python 3.12, ccxt (Binance USD-M `fapiPrivateGetIncome`), pytest, pandas (timestamps), FastAPI (dashboard).

**Spec:** `docs/superpowers/specs/2026-06-01-binance-sync-margin-sltp-hardening-design.md` (PR C section).

---

## File Structure

- `exchange/__init__.py`
  - `Position` dataclass — add 4 reconciliation fields (defaults → backward-compatible restore).
  - `BinanceClient` — new `fetch_realized_pnl()` (income endpoint reader).
  - `OrderManager._record_close()` — set net PnL from exchange when available.
  - `OrderManager.audit_realized_pnl()` — new periodic correction sweep.
  - `OrderManager.reconcile()` — call the audit sweep on a low cadence.
- `engine/journal.py` — `TradeSnapshot` gains `pnl_source` + reconciled-PnL fields.
- `backend/api.py` — journal-backed fallback for `/history` and `/equity`.
- Tests: `backend/tests/test_fetch_realized_pnl.py`, `backend/tests/test_record_close_realized.py`, `backend/tests/test_pnl_audit_sweep.py`, `backend/tests/test_api_journal_fallback.py`.

**Config flag** (`configs/config.phase2_1k.yaml`, mirror to `config.yaml`), under `safety:`:
```yaml
  enable_pnl_audit: true        # periodic income-history reconciliation sweep
  pnl_audit_every_cycles: 20    # run the audit sweep once per N reconcile cycles
```

---

## Task 1: Add reconciliation fields to the `Position` dataclass

**Files:**
- Modify: `exchange/__init__.py` (`Position`, after line 266 `pnl_usdt`)
- Test: `backend/tests/test_record_close_realized.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_record_close_realized.py
from exchange import Position


def test_position_has_reconciliation_fields_with_defaults():
    pos = Position(
        symbol="BTC/USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=110.0, tp2=120.0, size=1.0,
    )
    assert pos.realized_pnl_exchange == 0.0
    assert pos.commission_paid == 0.0
    assert pos.funding_paid == 0.0
    assert pos.pnl_source == "estimated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_record_close_realized.py::test_position_has_reconciliation_fields_with_defaults -v`
Expected: FAIL — `AttributeError: 'Position' object has no attribute 'realized_pnl_exchange'`

- [ ] **Step 3: Add the fields**

In `exchange/__init__.py`, immediately after the `pnl_usdt: float = 0.0` line (≈266):

```python
    # PR C — exchange-truth PnL reconciliation. Defaults keep _restore() of
    # pre-PR-C order_manager_positions.json backward-compatible.
    realized_pnl_exchange: float = 0.0   # net realizedPnl pulled from Binance income endpoint
    commission_paid: float = 0.0         # summed COMMISSION income for this position's fills
    funding_paid: float = 0.0            # summed FUNDING_FEE income over the position lifetime
    pnl_source: str = "estimated"        # "estimated" until reconciled, then "exchange"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_record_close_realized.py::test_position_has_reconciliation_fields_with_defaults -v`
Expected: PASS

- [ ] **Step 5: Verify old-state restore still works**

Run: `pytest backend/tests/test_order_manager_v2.py backend/tests/test_order_manager_atomicity.py -v`
Expected: PASS (new fields have defaults → asdict/restore round-trips unaffected)

- [ ] **Step 6: Commit**

```bash
git add exchange/__init__.py backend/tests/test_record_close_realized.py
git commit -m "feat(pnl): add exchange-truth reconciliation fields to Position"
```

---

## Task 2: `BinanceClient.fetch_realized_pnl()` — income endpoint reader

**Files:**
- Modify: `exchange/__init__.py` (`BinanceClient`, add method after `get_open_positions`, ≈line 243)
- Test: `backend/tests/test_fetch_realized_pnl.py`

The Binance USD-M income endpoint (`fapiPrivateGetIncome`) returns one row per
income event: `{"symbol": "BTCUSDT", "incomeType": "REALIZED_PNL"|"COMMISSION"|"FUNDING_FEE", "income": "1.23", "time": 1234567890123}`. We sum each type over a symbol+time window and return the net.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_fetch_realized_pnl.py
from exchange import BinanceClient


class _FakeExchange:
    def __init__(self, rows, raise_exc=None):
        self._rows = rows
        self._raise = raise_exc
        self.calls = []

    def market(self, ccxt_sym):
        return {"id": ccxt_sym.split(":")[0].replace("/", "")}

    def fapiPrivateGetIncome(self, params):
        self.calls.append(params)
        if self._raise:
            raise self._raise
        return self._rows


def _client_with(rows, raise_exc=None):
    c = BinanceClient.__new__(BinanceClient)   # bypass __init__ (no network)
    c.exchange = _FakeExchange(rows, raise_exc)
    c.market_type = "futures"
    return c


def test_fetch_realized_pnl_sums_by_type():
    rows = [
        {"symbol": "BTCUSDT", "incomeType": "REALIZED_PNL", "income": "10.0", "time": 1},
        {"symbol": "BTCUSDT", "incomeType": "COMMISSION",   "income": "-0.4", "time": 2},
        {"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE",  "income": "-0.1", "time": 3},
    ]
    c = _client_with(rows)
    out = c.fetch_realized_pnl("BTC/USDT", since_ms=0)
    assert out["realized_pnl"] == 10.0
    assert out["commission"] == -0.4
    assert out["funding"] == -0.1
    assert round(out["net"], 6) == 9.5
    assert out["ok"] is True


def test_fetch_realized_pnl_soft_fails_to_zeros():
    c = _client_with([], raise_exc=RuntimeError("api down"))
    out = c.fetch_realized_pnl("BTC/USDT", since_ms=0)
    assert out["ok"] is False
    assert out["net"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_fetch_realized_pnl.py -v`
Expected: FAIL — `AttributeError: 'BinanceClient' object has no attribute 'fetch_realized_pnl'`

- [ ] **Step 3: Implement the method**

Add to `BinanceClient` (after `get_open_positions`, ≈line 243):

```python
    def fetch_realized_pnl(self, symbol: str, since_ms: int,
                           until_ms: int = None) -> dict:
        """Sum REALIZED_PNL / COMMISSION / FUNDING_FEE for a symbol+window.

        Reads the USD-M income endpoint (fapiPrivateGetIncome). Soft-fails:
        any transport/API error returns ok=False with zeroed sums so the
        caller can fall back to its estimate — never raises into reconcile.
        """
        if self.market_type != "futures":
            return {"realized_pnl": 0.0, "commission": 0.0, "funding": 0.0,
                    "net": 0.0, "ok": False}
        try:
            bn_sym = self.exchange.market(self.to_ccxt_symbol(symbol))["id"]
        except Exception:
            bn_sym = symbol.replace("/", "")

        totals = {"REALIZED_PNL": 0.0, "COMMISSION": 0.0, "FUNDING_FEE": 0.0}
        for income_type in totals:
            params = {"symbol": bn_sym, "incomeType": income_type,
                      "startTime": int(since_ms), "limit": 1000}
            if until_ms is not None:
                params["endTime"] = int(until_ms)
            try:
                rows = self.exchange.fapiPrivateGetIncome(params)
            except Exception as e:
                log.warning(f"fetch_realized_pnl({symbol},{income_type}) failed: {e}")
                return {"realized_pnl": 0.0, "commission": 0.0, "funding": 0.0,
                        "net": 0.0, "ok": False}
            for r in (rows or []):
                try:
                    totals[income_type] += float(r.get("income", 0) or 0)
                except (TypeError, ValueError):
                    continue

        net = totals["REALIZED_PNL"] + totals["COMMISSION"] + totals["FUNDING_FEE"]
        return {"realized_pnl": totals["REALIZED_PNL"],
                "commission": totals["COMMISSION"],
                "funding": totals["FUNDING_FEE"],
                "net": net, "ok": True}
```

> Note: `to_ccxt_symbol` already exists on `BinanceClient`. The test stubs
> `market()` to return the `id`; the real ccxt `market()` returns the Binance
> symbol id (e.g. `BTCUSDT`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_fetch_realized_pnl.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add exchange/__init__.py backend/tests/test_fetch_realized_pnl.py
git commit -m "feat(pnl): BinanceClient.fetch_realized_pnl income-endpoint reader"
```

---

## Task 3: Wire exchange-truth PnL into `_record_close`

**Files:**
- Modify: `exchange/__init__.py` (`_record_close`, lines 1384-1405)
- Test: `backend/tests/test_record_close_realized.py`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_record_close_realized.py
from exchange import OrderManager, Position
import pandas as pd


class _FakeClient:
    def __init__(self, net=None, ok=True):
        self._net = net
        self._ok = ok
        self.called_with = None

    def fetch_realized_pnl(self, symbol, since_ms, until_ms=None):
        self.called_with = (symbol, since_ms)
        if self._net is None:
            return {"ok": False, "net": 0.0, "realized_pnl": 0.0,
                    "commission": 0.0, "funding": 0.0}
        return {"ok": self._ok, "net": self._net, "realized_pnl": self._net + 0.5,
                "commission": -0.4, "funding": -0.1}


def _mgr(client):
    m = OrderManager.__new__(OrderManager)
    m.client = client
    m.closed_positions = []
    m.trade_journal = None
    m._listeners = {}
    return m


def _pos():
    return Position(symbol="BTC/USDT", direction="LONG", entry=100.0, sl=95.0,
                    tp1=110.0, tp2=120.0, size=1.0,
                    opened_at=pd.Timestamp("2026-06-01T00:00:00Z").isoformat())


def test_record_close_uses_exchange_net_when_available():
    m = _mgr(_FakeClient(net=8.7, ok=True))
    pos = _pos()
    m._record_close(pos, exit_price=109.0, reason="TP1")
    assert pos.pnl_source == "exchange"
    assert pos.pnl_usdt == 8.7
    assert pos.realized_pnl_exchange == 9.2   # net + 0.5 per fake


def test_record_close_falls_back_to_estimate_on_soft_fail():
    m = _mgr(_FakeClient(net=None))   # ok=False
    pos = _pos()
    m._record_close(pos, exit_price=109.0, reason="TP1")
    assert pos.pnl_source == "estimated"
    # gross estimate = (109 - 100) * 1.0 = 9.0
    assert pos.pnl_usdt == 9.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_record_close_realized.py -v`
Expected: FAIL — `test_record_close_uses_exchange_net_when_available` asserts `pnl_source == "exchange"` but current code never sets it.

- [ ] **Step 3: Modify `_record_close`**

Replace the body of `_record_close` (1384-1405) with:

```python
    def _record_close(self, pos: Position, exit_price: float, reason: str) -> None:
        """Pozisyon kapanış metadata'sını doldur ve event emit et.

        PR C: prefer Binance net realizedPnl (realizedPnl - commission - funding)
        over the gross estimate. Falls back to the estimate (and tags
        pnl_source="estimated") when the exchange read soft-fails.
        """
        is_long = pos.direction == "LONG"
        pnl_pct = ((exit_price - pos.entry) / pos.entry * 100) if is_long else \
                  ((pos.entry - exit_price) / pos.entry * 100)
        est_pnl_usdt = (exit_price - pos.entry) * pos.size if is_long else \
                       (pos.entry - exit_price) * pos.size

        # Exchange-truth PnL (soft-fail → keep estimate).
        pnl_usdt = est_pnl_usdt
        pos.pnl_source = "estimated"
        try:
            since_ms = int(pd.Timestamp(pos.opened_at).value // 1_000_000) if pos.opened_at else 0
        except Exception:
            since_ms = 0
        try:
            res = self.client.fetch_realized_pnl(pos.symbol, since_ms=since_ms)
        except Exception:
            res = {"ok": False}
        if res.get("ok"):
            pnl_usdt = res["net"]
            pos.realized_pnl_exchange = res.get("realized_pnl", 0.0)
            pos.commission_paid = res.get("commission", 0.0)
            pos.funding_paid = res.get("funding", 0.0)
            pos.pnl_source = "exchange"

        pos.closed_at = pd.Timestamp.now(tz="UTC").isoformat()
        pos.exit_reason = reason
        pos.exit_price = exit_price
        pos.pnl_usdt = pnl_usdt

        log.info(
            f"{reason}: {pos.symbol} {pos.direction} | "
            f"Entry={pos.entry:.4f} Exit={exit_price:.4f} | "
            f"PnL={pnl_pct:+.2f}% (${pnl_usdt:+.2f}) [{pos.pnl_source}]"
        )

        self.closed_positions.append(pos)
        self._journal_record_close(pos, exit_price, reason)
        self._emit("position_closed", pos)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_record_close_realized.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Run the close-path regression suite**

Run: `pytest backend/tests/test_order_manager_v2.py backend/tests/test_order_manager_slippage.py backend/tests/test_reconcile_breaker_sync.py -v`
Expected: PASS (existing close behavior unchanged when `fetch_realized_pnl` is mocked/absent — real client returns ok and overrides; old tests that assert gross PnL must mock the client to soft-fail, see Step 6)

- [ ] **Step 6: Fix any regression in existing close tests**

If an existing test constructs an `OrderManager` whose `client` lacks
`fetch_realized_pnl`, the `try/except` returns `{"ok": False}` and the estimate
path runs — behavior matches today. If a test uses a real-ish mock client,
add `fetch_realized_pnl = lambda *a, **k: {"ok": False}` to that mock. Make the
minimal edit and re-run.

- [ ] **Step 7: Commit**

```bash
git add exchange/__init__.py backend/tests/test_record_close_realized.py
git commit -m "feat(pnl): _record_close uses Binance net realizedPnl with estimate fallback"
```

---

## Task 4: `pnl_source` + reconciled fields on the trade journal

**Files:**
- Modify: `engine/journal.py` (`TradeSnapshot`)
- Modify: `exchange/__init__.py` (`_journal_record_close`, after line 1434)
- Test: `backend/tests/test_pnl_audit_sweep.py` (journal write assertion)

- [ ] **Step 1: Read the current `TradeSnapshot` definition**

Run: `sed -n '1,80p' engine/journal.py`  *(inspect existing fields + how snapshots serialize to `trade_journal.jsonl`)*

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_pnl_audit_sweep.py
from engine.journal import TradeSnapshot


def test_tradesnapshot_has_pnl_source_field():
    snap = TradeSnapshot(
        trade_id="t1", symbol="BTC/USDT", direction="LONG", timeframe="",
        entry_timestamp="2026-06-01T00:00:00Z", entry_price=100.0,
        sl_initial=95.0, tp1_initial=110.0, tp2_initial=120.0,
        position_size=1.0, htf_bias="",
    )
    assert hasattr(snap, "pnl_source")
    assert snap.pnl_source == "estimated"
    assert hasattr(snap, "realized_pnl_exchange")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest backend/tests/test_pnl_audit_sweep.py::test_tradesnapshot_has_pnl_source_field -v`
Expected: FAIL — `TypeError`/`AttributeError` (field missing)

- [ ] **Step 4: Add fields to `TradeSnapshot`**

In `engine/journal.py`, add to the `TradeSnapshot` dataclass (with defaults so
existing callers are unaffected):

```python
    pnl_source: str = "estimated"          # "estimated" | "exchange"
    realized_pnl_exchange: float = 0.0
    commission_paid: float = 0.0
    funding_paid: float = 0.0
```

- [ ] **Step 5: Populate them in `_journal_record_close`**

In `exchange/__init__.py` `_journal_record_close`, in the `TradeSnapshot(...)`
constructor call (≈1423-1434), add the new kwargs:

```python
                pnl_source=pos.pnl_source,
                realized_pnl_exchange=pos.realized_pnl_exchange,
                commission_paid=pos.commission_paid,
                funding_paid=pos.funding_paid,
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest backend/tests/test_pnl_audit_sweep.py::test_tradesnapshot_has_pnl_source_field -v`
Expected: PASS

- [ ] **Step 7: Run journal regression**

Run: `pytest backend/tests/ -k journal -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add engine/journal.py exchange/__init__.py backend/tests/test_pnl_audit_sweep.py
git commit -m "feat(pnl): persist pnl_source + reconciled PnL on trade journal"
```

---

## Task 5: `OrderManager.audit_realized_pnl()` — periodic correction sweep

**Files:**
- Modify: `exchange/__init__.py` (new method on `OrderManager`, after `_record_close`)
- Test: `backend/tests/test_pnl_audit_sweep.py`

The sweep re-reads income for recently-closed positions still tagged
`estimated` and upgrades them to exchange-truth. It appends a correction record
to the journal rather than mutating history in place.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_pnl_audit_sweep.py
from exchange import OrderManager, Position
import pandas as pd


class _AuditClient:
    def __init__(self, net):
        self._net = net

    def fetch_realized_pnl(self, symbol, since_ms, until_ms=None):
        return {"ok": True, "net": self._net, "realized_pnl": self._net,
                "commission": 0.0, "funding": 0.0}


def _audit_mgr(client):
    m = OrderManager.__new__(OrderManager)
    m.client = client
    m.closed_positions = []
    m.trade_journal = None
    m._listeners = {}
    return m


def test_audit_upgrades_estimated_closed_positions():
    m = _audit_mgr(_AuditClient(net=-2.5))
    pos = Position(symbol="SOL/USDT", direction="LONG", entry=82.0, sl=80.0,
                   tp1=85.0, tp2=88.0, size=1.0,
                   opened_at=pd.Timestamp("2026-06-01T00:00:00Z").isoformat(),
                   closed_at=pd.Timestamp("2026-06-01T01:00:00Z").isoformat(),
                   pnl_usdt=3.0, pnl_source="estimated")
    m.closed_positions.append(pos)

    corrected = m.audit_realized_pnl(window_hours=24)

    assert corrected == 1
    assert pos.pnl_source == "exchange"
    assert pos.pnl_usdt == -2.5


def test_audit_skips_already_reconciled():
    m = _audit_mgr(_AuditClient(net=99.0))
    pos = Position(symbol="SOL/USDT", direction="LONG", entry=82.0, sl=80.0,
                   tp1=85.0, tp2=88.0, size=1.0,
                   opened_at=pd.Timestamp("2026-06-01T00:00:00Z").isoformat(),
                   closed_at=pd.Timestamp("2026-06-01T01:00:00Z").isoformat(),
                   pnl_usdt=5.0, pnl_source="exchange")
    m.closed_positions.append(pos)

    corrected = m.audit_realized_pnl(window_hours=24)

    assert corrected == 0
    assert pos.pnl_usdt == 5.0   # untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_pnl_audit_sweep.py -k audit -v`
Expected: FAIL — `AttributeError: 'OrderManager' object has no attribute 'audit_realized_pnl'`

- [ ] **Step 3: Implement `audit_realized_pnl`**

Add to `OrderManager` (after `_record_close`):

```python
    def audit_realized_pnl(self, window_hours: int = 24) -> int:
        """Re-reconcile recently-closed positions still tagged 'estimated'.

        Pulls exchange income for each estimated close within the window and
        upgrades pnl_usdt to net exchange truth. Returns the number corrected.
        Soft-fails per position so one bad read never aborts the sweep.
        """
        try:
            cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=window_hours)
        except Exception:
            return 0
        corrected = 0
        for pos in self.closed_positions:
            if pos.pnl_source == "exchange":
                continue
            if not pos.closed_at:
                continue
            try:
                closed_ts = pd.Timestamp(pos.closed_at)
                if closed_ts < cutoff:
                    continue
                since_ms = int(pd.Timestamp(pos.opened_at).value // 1_000_000)
            except Exception:
                continue
            try:
                res = self.client.fetch_realized_pnl(pos.symbol, since_ms=since_ms)
            except Exception:
                res = {"ok": False}
            if not res.get("ok"):
                continue
            old = pos.pnl_usdt
            pos.pnl_usdt = res["net"]
            pos.realized_pnl_exchange = res.get("realized_pnl", 0.0)
            pos.commission_paid = res.get("commission", 0.0)
            pos.funding_paid = res.get("funding", 0.0)
            pos.pnl_source = "exchange"
            corrected += 1
            log.info(
                "pnl_audit: corrected %s %s est=%.4f → exchange=%.4f",
                pos.symbol, pos.direction, old, pos.pnl_usdt,
            )
            self._journal_record_close(pos, pos.exit_price, f"{pos.exit_reason}_AUDIT")
        return corrected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_pnl_audit_sweep.py -k audit -v`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add exchange/__init__.py backend/tests/test_pnl_audit_sweep.py
git commit -m "feat(pnl): audit_realized_pnl periodic exchange-truth correction sweep"
```

---

## Task 6: Drive the audit sweep from `reconcile()` on a low cadence

**Files:**
- Modify: `exchange/__init__.py` (`OrderManager.__init__` — counter + flag; `reconcile()` — invoke sweep near `_persist()` at line 1231)
- Modify: `backend/bot_runner.py` (wire the two config flags, next to `max_entry_drift_pct` at ≈line 217)
- Test: `backend/tests/test_pnl_audit_sweep.py`

- [ ] **Step 1: Read the OrderManager `__init__` flag/counter area and the reconcile tail**

Run: `sed -n '326,362p;1225,1235p' exchange/__init__.py`  *(confirm where to add `self.enable_pnl_audit`, `self.pnl_audit_every_cycles`, a cycle counter, and the call site before/after `_persist()`)*

- [ ] **Step 2: Write the failing test**

```python
# append to backend/tests/test_pnl_audit_sweep.py
def test_reconcile_runs_audit_every_n_cycles(monkeypatch):
    m = _audit_mgr(_AuditClient(net=0.0))
    m.enable_pnl_audit = True
    m.pnl_audit_every_cycles = 3
    m._pnl_audit_cycle = 0

    calls = {"n": 0}
    monkeypatch.setattr(m, "audit_realized_pnl", lambda **k: calls.__setitem__("n", calls["n"] + 1) or 0)

    for _ in range(7):
        m._maybe_run_pnl_audit()

    assert calls["n"] == 2   # cycles 3 and 6
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest backend/tests/test_pnl_audit_sweep.py::test_reconcile_runs_audit_every_n_cycles -v`
Expected: FAIL — `AttributeError: ... '_maybe_run_pnl_audit'`

- [ ] **Step 4: Add the counter + helper, and call it from reconcile**

In `OrderManager.__init__` (near the other config-derived attributes, ≈356), add:

```python
        self.enable_pnl_audit = True            # overridden by bot_runner wiring
        self.pnl_audit_every_cycles = 20        # overridden by bot_runner wiring
        self._pnl_audit_cycle = 0
```

Add the helper method (next to `audit_realized_pnl`):

```python
    def _maybe_run_pnl_audit(self) -> None:
        """Tick the cycle counter; run the audit sweep every N cycles."""
        if not self.enable_pnl_audit:
            return
        self._pnl_audit_cycle += 1
        if self._pnl_audit_cycle % max(1, self.pnl_audit_every_cycles) != 0:
            return
        try:
            self.audit_realized_pnl(window_hours=24)
        except Exception as e:
            log.warning(f"pnl_audit sweep failed: {e}")
```

In `reconcile()`, immediately before the final `self._persist()` (≈line 1231), add:

```python
        self._maybe_run_pnl_audit()
```

- [ ] **Step 5: Wire the config flags in `bot_runner.py`**

Near the `max_entry_drift_pct` wiring (≈line 217), after the `OrderManager` is
constructed, add:

```python
        _safety = self.cfg.get("safety", {})
        self.order_mgr.enable_pnl_audit = bool(_safety.get("enable_pnl_audit", True))
        self.order_mgr.pnl_audit_every_cycles = int(_safety.get("pnl_audit_every_cycles", 20))
```

*(If `order_mgr` is named differently or constructed elsewhere, match the
existing `max_entry_drift_pct` assignment site exactly.)*

- [ ] **Step 6: Add the config keys**

In `configs/config.phase2_1k.yaml` under `safety:`:

```yaml
  enable_pnl_audit: true
  pnl_audit_every_cycles: 20
```

Mirror the same two keys into root `config.yaml` under `safety:`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest backend/tests/test_pnl_audit_sweep.py -v`
Expected: PASS (all)

- [ ] **Step 8: Run the reconcile regression suite**

Run: `pytest backend/tests/test_order_manager_v2.py backend/tests/test_reconcile_algo_orders_visibility.py backend/tests/test_cli_reconcile_parity.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add exchange/__init__.py backend/bot_runner.py configs/config.phase2_1k.yaml config.yaml backend/tests/test_pnl_audit_sweep.py
git commit -m "feat(pnl): run audit sweep every N reconcile cycles (config-gated)"
```

---

## Task 7: Journal-backed `/history` & `/equity` fallback (DB-less dashboard)

**Files:**
- Modify: `backend/api.py` (`/history` line 191, `/equity` line 196)
- Test: `backend/tests/test_api_journal_fallback.py`

Prod is DB-less, so `db.fetch_recent_trades()` / `db.fetch_equity_history()`
return empty. Add a fallback that reads reconciled closes from
`trade_journal.jsonl` so the dashboard shows exchange-truth PnL.

- [ ] **Step 1: Read the current `/history` and `/equity` handlers + how the DB helper signals "empty/unavailable"**

Run: `sed -n '185,215p' backend/api.py`

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_api_journal_fallback.py
import json
from backend.api import read_journal_history


def test_read_journal_history_returns_reconciled_closes(tmp_path):
    jf = tmp_path / "trade_journal.jsonl"
    rows = [
        {"trade_id": "a", "symbol": "BTC/USDT", "direction": "LONG",
         "pnl_usdt": -2.5, "pnl_source": "exchange",
         "closed_at": "2026-06-01T01:00:00Z"},
        {"trade_id": "b", "symbol": "SOL/USDT", "direction": "SHORT",
         "pnl_usdt": 4.0, "pnl_source": "exchange",
         "closed_at": "2026-06-01T02:00:00Z"},
    ]
    jf.write_text("\n".join(json.dumps(r) for r in rows))

    out = read_journal_history(str(jf), limit=10)

    assert len(out) == 2
    assert out[0]["symbol"] == "SOL/USDT"   # newest first
    assert out[1]["pnl_usdt"] == -2.5


def test_read_journal_history_missing_file_returns_empty():
    assert read_journal_history("/no/such/file.jsonl", limit=10) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest backend/tests/test_api_journal_fallback.py -v`
Expected: FAIL — `ImportError: cannot import name 'read_journal_history'`

- [ ] **Step 4: Implement the helper + wire the fallback**

Add to `backend/api.py`:

```python
import json as _json
import os as _os


def read_journal_history(journal_path: str, limit: int = 100) -> list:
    """Read closed trades from trade_journal.jsonl, newest first.

    DB-less fallback for /history. Returns [] when the file is absent or
    unreadable — never raises into the request handler.
    """
    if not journal_path or not _os.path.exists(journal_path):
        return []
    rows = []
    try:
        with open(journal_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if obj.get("closed_at"):
                    rows.append(obj)
    except OSError:
        return []
    rows.sort(key=lambda r: r.get("closed_at", ""), reverse=True)
    return rows[:limit]
```

In the `/history` handler (≈191), after `db.fetch_recent_trades()`, if the DB
result is empty, fall back:

```python
    trades = db.fetch_recent_trades() if db else []
    if not trades:
        journal_path = _os.environ.get("EFLOUD_TRADE_JOURNAL", "trade_journal.jsonl")
        trades = read_journal_history(journal_path, limit=100)
    return {"trades": trades}
```

*(Match the actual return shape of the existing `/history` handler — inspect it
in Step 1 and mirror its key names. If it already returns `{"trades": ...}`,
keep that; otherwise adapt.)*

For `/equity` (≈196): derive a running cumulative-PnL series from the same
journal rows when `db.fetch_equity_history()` is empty:

```python
    equity = db.fetch_equity_history() if db else []
    if not equity:
        journal_path = _os.environ.get("EFLOUD_TRADE_JOURNAL", "trade_journal.jsonl")
        rows = list(reversed(read_journal_history(journal_path, limit=1000)))
        cum = 0.0
        equity = []
        for r in rows:
            cum += float(r.get("pnl_usdt", 0) or 0)
            equity.append({"t": r.get("closed_at"), "equity": cum})
    return {"equity": equity}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_api_journal_fallback.py -v`
Expected: PASS (both)

- [ ] **Step 6: Run the api regression suite**

Run: `pytest backend/tests/ -k api -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/api.py backend/tests/test_api_journal_fallback.py
git commit -m "feat(pnl): journal-backed /history + /equity fallback for DB-less dashboard"
```

---

## Task 8: Full-suite verification

- [ ] **Step 1: Run the full backend suite**

Run: `pytest backend/tests -q`
Expected: PASS — baseline ~1139 tests + the new PR C tests, 0 failures.

- [ ] **Step 2: If any pre-existing test regressed**

Use superpowers:systematic-debugging. The most likely regression is an existing
close/journal test that now hits the exchange-PnL branch — add
`fetch_realized_pnl = lambda *a, **k: {"ok": False}` to that test's mock client
so it deterministically uses the estimate path.

- [ ] **Step 3: Final commit if any fixups were needed**

```bash
git add -A
git commit -m "test(pnl): stabilize close/journal tests for exchange-PnL branch"
```

---

## Self-Review Checklist (run before handoff)

- [ ] **Spec coverage:** real realizedPnl on close (Task 3) ✓; commission+funding (Task 2 income types) ✓; periodic audit sweep (Tasks 5-6) ✓; dashboard reconciled figure (Task 7) ✓; backward-compatible restore (Task 1 defaults) ✓; soft-fail everywhere (Tasks 2,3,5) ✓.
- [ ] **No placeholders:** every code step has complete code; no TBD/TODO.
- [ ] **Type consistency:** `fetch_realized_pnl` returns `{realized_pnl, commission, funding, net, ok}` — used identically in Tasks 2,3,5. `Position` fields (`realized_pnl_exchange`, `commission_paid`, `funding_paid`, `pnl_source`) named identically in Tasks 1,3,4,5. `read_journal_history(path, limit)` signature consistent in Task 7.

## Notes for the implementer (Gemini)

- **Do not change** entry/signal logic — PR C is reporting-only.
- All exchange reads must **soft-fail** (return ok=False / []), never raise into
  `reconcile()` or a request handler.
- `_record_close` is called from multiple reconcile branches; the change is
  localized to that one method so every close path benefits.
- Verify the real `/history` and `/equity` return shapes in `backend/api.py`
  Step-1 reads and mirror them — the snippets assume `{"trades": [...]}` /
  `{"equity": [...]}` but adapt to what exists.
