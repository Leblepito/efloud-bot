# SL/TP Delivery Bugfix Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Fix critical bugs causing SL/TP orders to sometimes fail delivery after successful entry placement.

**Architecture:** 4 sequential PRs addressing: (1) CLI wiring gaps, (2) SL retry mechanism, (3) breakeven SL retry, (4) test coverage expansion. Each PR is atomic with TDD approach.

**Tech Stack:** Python, pytest, CCXT, Binance Futures API

**Safety invariants:**
- No changes to config.yaml, docker-compose.prod.yml, or production deployment files
- All changes are non-breaking for existing bot_runner.py (FastAPI) production path
- Tests use mocks; no live API calls
- Each PR is independently deployable without requiring other PRs

---

## PR #1: main.py OrderManager Wiring Fix (CRITICAL)

### Background
main.py CLI mode creates OrderManager with missing critical parameters:
- `hedge_mode`: Config has `hedge_mode: true` but OM receives default False
- `state_dir`: Not passed → crash recovery disabled
- `orphan_protector`: Not wired → orphan detection silent
- `on_position_change`: Not wired → no event callbacks

**Impact:** In hedge mode, Binance requires `positionSide` parameter (not `reduceOnly`). When OM uses False default, SL/TP orders are rejected by Binance.

### Task 1.1: Write test for main.py OrderManager construction

**Objective:** Verify main.py constructs OrderManager with correct parameters from config.

**Files:**
- Create: `backend/tests/test_main_om_wiring.py`

**Step 1: Write failing test**

```python
"""Test main.py OrderManager wiring matches config.yaml parameters."""
from unittest.mock import MagicMock, patch
import pytest
from main import main


class TestMainOMWiring:
    """Verify OrderManager receives correct parameters from config."""

    @patch("main.BinanceClient")
    @patch("main.OrderManager")
    @patch("main.SafeOrchestrator")
    @patch("main.SymbolUniverse")
    @patch("main.TradeJournal")
    @patch("main.load_config")
    @patch("main.resolve_credentials")
    @patch("main.validate_config")
    @patch("main.MainnetGuard.check")
    @patch("main.GracefulShutdown")
    def test_om_receives_hedge_mode_from_config(
        self, mock_shutdown_cls, mock_mainnet, mock_validate,
        mock_credentials, mock_load_config, mock_journal_cls,
        mock_universe_cls, mock_orch_cls, mock_om_cls, mock_client_cls
    ):
        """OrderManager must receive hedge_mode from config.yaml."""
        mock_shutdown = MagicMock()
        mock_shutdown.stop = True  # Exit immediately
        mock_shutdown_cls.return_value = mock_shutdown
        
        mock_mainnet.return_value = True
        mock_credentials.return_value = ("test_key", "test_secret")
        mock_load_config.return_value = {
            "exchange": {"testnet": True, "leverage": 3, "margin_mode": "ISOLATED", "hedge_mode": True, "market_type": "futures"},
            "operation": {"dry_run": True, "check_interval_sec": 1, "state_dir": "./state"},
            "risk": {"risk_per_trade_pct": 1.0, "min_confluence": 50, "min_rr": 1.5},
            "safety": {"min_seconds_between_symbol_fetches": 1.0},
            "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m", "kline_limit": 100},
            "symbols": {"mode": "fixed", "fixed_core": ["BTC/USDT"]},
            "structure": {"swing_lookback": 4, "ob_sequential": 5, "body_mode": True, "eq_threshold_pct": 0.1, "range_lookback": 50},
            "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786},
        }
        
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        
        try:
            main()
        except SystemExit:
            pass  # Expected
        
        # Verify OrderManager was called with hedge_mode=True
        om_call = mock_om_cls.call_args
        assert om_call.kwargs.get("hedge_mode") is True, \
            f"OrderManager should receive hedge_mode=True, got kwargs: {om_call.kwargs}"

    @patch("main.BinanceClient")
    @patch("main.OrderManager")
    @patch("main.SafeOrchestrator")
    @patch("main.SymbolUniverse")
    @patch("main.TradeJournal")
    @patch("main.load_config")
    @patch("main.resolve_credentials")
    @patch("main.validate_config")
    @patch("main.MainnetGuard.check")
    @patch("main.GracefulShutdown")
    def test_om_receives_state_dir_from_config(
        self, mock_shutdown_cls, mock_mainnet, mock_validate,
        mock_credentials, mock_load_config, mock_journal_cls,
        mock_universe_cls, mock_orch_cls, mock_om_cls, mock_client_cls
    ):
        """OrderManager must receive state_dir for crash recovery."""
        mock_shutdown = MagicMock()
        mock_shutdown.stop = True
        mock_shutdown_cls.return_value = mock_shutdown
        
        mock_mainnet.return_value = True
        mock_credentials.return_value = ("test_key", "test_secret")
        mock_load_config.return_value = {
            "exchange": {"testnet": True, "leverage": 3, "margin_mode": "ISOLATED", "hedge_mode": False, "market_type": "futures"},
            "operation": {"dry_run": True, "check_interval_sec": 1, "state_dir": "./test_state"},
            "risk": {"risk_per_trade_pct": 1.0, "min_confluence": 50, "min_rr": 1.5},
            "safety": {"min_seconds_between_symbol_fetches": 1.0},
            "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m", "kline_limit": 100},
            "symbols": {"mode": "fixed", "fixed_core": ["BTC/USDT"]},
            "structure": {"swing_lookback": 4, "ob_sequential": 5, "body_mode": True, "eq_threshold_pct": 0.1, "range_lookback": 50},
            "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786},
        }
        
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        
        try:
            main()
        except SystemExit:
            pass
        
        om_call = mock_om_cls.call_args
        assert om_call.kwargs.get("state_dir") == "./test_state", \
            f"OrderManager should receive state_dir='./test_state', got kwargs: {om_call.kwargs}"
```

**Step 2: Run test to verify failure**

Run:
```bash
python -m pytest backend/tests/test_main_om_wiring.py -v --import-mode=importlib
```

Expected: FAIL — `AssertionError: OrderManager should receive hedge_mode=True`

**Step 3: Commit test**

```bash
git add backend/tests/test_main_om_wiring.py
git commit -m "test: add main.py OrderManager wiring tests (RED phase)"
```

### Task 1.2: Fix main.py OrderManager construction

**Objective:** Pass hedge_mode, state_dir, orphan_protector to OrderManager.

**Files:**
- Modify: `main.py:574-576`

**Step 1: Read current code**

```python
# main.py:574 (current — BROKEN)
order_mgr = OrderManager(client, dry_run=cfg["operation"]["dry_run"],
                          trade_journal=trade_journal)
```

**Step 2: Compare with bot_runner.py (correct wiring)**

```python
# bot_runner.py:201-208 (correct)
self.order_mgr = OrderManager(
    self.client, dry_run=self.cfg["operation"]["dry_run"],
    on_position_change=self._on_position_change,
    state_dir=state_dir,
    orphan_protector=orphan_protector,
    trade_journal=trade_journal,
    hedge_mode=self.cfg.get("exchange", {}).get("hedge_mode", False),
)
```

**Step 3: Fix main.py**

Find the section after orphan_protector creation (~line 567) and before OrderManager construction.

Replace:
```python
    order_mgr = OrderManager(client, dry_run=cfg["operation"]["dry_run"],
                              trade_journal=trade_journal)
```

With:
```python
    # Build orphan_protector (mirrors bot_runner.py:189-190)
    orphan_cfg = load_orphan_protection_config(cfg.get("safety", {}))
    orphan_protector = OrphanProtector(orphan_cfg, client) if not cfg["operation"]["dry_run"] else None
    
    order_mgr = OrderManager(
        client,
        dry_run=cfg["operation"]["dry_run"],
        state_dir=state_dir,
        orphan_protector=orphan_protector,
        trade_journal=trade_journal,
        hedge_mode=cfg.get("exchange", {}).get("hedge_mode", False),
    )
```

**Step 4: Add missing imports**

At top of main.py (after line 44):
```python
from engine.safety import (
    MainnetGuard, mask_secret, retry_with_backoff,
    RateLimiter, validate_kline_integrity,
    OrphanProtector, load_orphan_protection_config,  # NEW
)
```

**Step 5: Run tests to verify pass**

```bash
python -m pytest backend/tests/test_main_om_wiring.py -v --import-mode=importlib
```

Expected: PASS — both tests pass.

Then run full suite:
```bash
python -m pytest backend/tests/ --ignore=external_repos --import-mode=importlib -q
```

Expected: All existing tests still pass.

**Step 6: Commit**

```bash
git add main.py backend/tests/test_main_om_wiring.py
git commit -m "fix(main.py): wire OrderManager with hedge_mode, state_dir, orphan_protector

CLI mode (python main.py) was creating OrderManager with default
hedge_mode=False, ignoring config.yaml's hedge_mode: true.

In hedge mode, Binance requires positionSide parameter on SL/TP orders
(not reduceOnly). When OM used wrong default, SL/TP orders were rejected
by Binance, leaving positions unprotected.

Also added state_dir for crash recovery and orphan_protector for
orphan detection parity with bot_runner.py (production FastAPI path).

Fixes: SL/TP delivery failures in CLI mode with hedge_mode enabled."
```

---

## PR #2: SL Placement Retry Mechanism

### Background
TP placement has retry (3 attempts, exponential backoff) via `_retry_tp_order()`.
SL placement has no retry — transient API errors cause immediate rollback or orphan.
`_repair_missing_protection_orders()` only repairs TP1/TP2, not SL.

### Task 2.1: Write test for SL retry

**Objective:** Verify SL placement retries on transient errors.

**Files:**
- Create: `backend/tests/test_sl_retry.py`

**Step 1: Write failing test**

```python
"""Tests for SL placement retry and repair mechanisms."""
from unittest.mock import MagicMock, patch
import pytest

from exchange import BinanceClient, OrderManager, Position


@pytest.fixture
def mock_client():
    client = MagicMock(spec=BinanceClient)
    client.exchange = MagicMock()
    client.market_type = "futures"
    client.testnet = True
    client.to_ccxt_symbol.side_effect = lambda s: (
        s if ":" in s or client.market_type != "futures" else f"{s}:USDT"
    )
    return client


@pytest.fixture
def mgr(mock_client):
    return OrderManager(mock_client, dry_run=False)


class TestSLRetry:
    """SL placement should retry transient errors like TP does."""

    @patch("exchange._time.sleep")
    def test_sl_transient_error_retries_and_succeeds(self, mock_sleep, mgr, mock_client):
        """SL fails with timeout on attempt 1, succeeds on attempt 2."""
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0},  # entry
            TimeoutError("Request timed out"),  # SL attempt 1 — transient
            {"id": "SL-1"},                     # SL attempt 2 — success
            {"id": "TP1-1"},                    # TP1
            {"id": "TP2-1"},                    # TP2
        ]

        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0,
            entry=95000, sl=94000, tp1=96000, tp2=97000,
        )

        assert pos is not None
        assert pos.sl_order_id == "SL-1"
        assert pos.tp1_order_id == "TP1-1"
        assert pos.tp2_order_id == "TP2-1"
        # Verify retry sleep was called
        assert mock_sleep.call_count >= 1

    @patch("exchange._time.sleep")
    def test_sl_three_transient_failures_exhausts_retries(self, mock_sleep, mgr, mock_client):
        """3 consecutive transient errors exhaust retries → rollback."""
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0},     # entry
            TimeoutError("timed out 1"),           # SL attempt 1
            TimeoutError("timed out 2"),           # SL attempt 2
            TimeoutError("timed out 3"),           # SL attempt 3 — exhausted
            {"id": "ROLLBACK-1"},                  # rollback close
        ]

        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0,
            entry=95000, sl=94000, tp1=96000, tp2=97000,
        )

        assert pos is None  # Rollback succeeded, no position opened
        assert mock_sleep.call_count == 2  # Sleeps after attempt 1 and 2


class TestSLRepair:
    """reconcile should detect and re-send missing SL orders."""

    def test_repair_sends_missing_sl(self, mgr, mock_client, caplog):
        """Position with empty sl_order_id gets repaired during reconcile."""
        import logging
        caplog.set_level(logging.CRITICAL, logger="efloud.exchange")

        # Pre-populate a position with missing SL
        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=94000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="",  # Missing SL
            tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions.append(pos)

        # Mock repair order success
        mock_client.exchange.create_order.return_value = {"id": "SL-REPAIR"}

        # Simulate reconcile finding the position still open
        mgr._repair_missing_protection_orders(bn_order_ids={"TP1-1", "TP2-1"})

        assert pos.sl_order_id == "SL-REPAIR"
        # Verify order was placed with correct params
        repair_call = mock_client.exchange.create_order.call_args
        assert repair_call.args[1] == "STOP_MARKET"
        assert repair_call.kwargs["params"]["stopPrice"] == 94000
```

**Step 2: Run test to verify failure**

```bash
python -m pytest backend/tests/test_sl_retry.py -v --import-mode=importlib
```

Expected: FAIL — `AssertionError: assert pos.sl_order_id == "SL-1"`

**Step 3: Commit test**

```bash
git add backend/tests/test_sl_retry.py
git commit -m "test: add SL retry and repair tests (RED phase)"
```

### Task 2.2: Implement SL retry logic

**Objective:** Add retry mechanism for SL placement matching TP retry pattern.

**Files:**
- Modify: `exchange/__init__.py:751-774` (SL placement section)

**Step 1: Refactor _retry_tp_order to generic _retry_protection_order**

The existing `_retry_tp_order` is already generic enough. Rename it internally (or keep name) and use for SL.

**Step 2: Replace SL placement block**

Find `exchange/__init__.py:751-774`:

```python
# Current code (no retry)
sl_params = {"stopPrice": sl}
if self.hedge_mode:
    sl_params["positionSide"] = direction
else:
    sl_params["reduceOnly"] = True
try:
    sl_order = self.client.exchange.create_order(
        ccxt_sym, "STOP_MARKET", reverse_side, size,
        params=sl_params
    )
except Exception as e:
    log.error(f"Order failed for {symbol}: {e}", exc_info=True)
    self._rollback_entry_after_protection_failure(...)
    return None
```

Replace with:

```python
# New code (with retry)
sl_params = {"stopPrice": sl}
if self.hedge_mode:
    sl_params["positionSide"] = direction
else:
    sl_params["reduceOnly"] = True

sl_oid = self._retry_tp_order(
    ccxt_sym=ccxt_sym,
    order_type="STOP_MARKET",
    side=reverse_side,
    amount=size,
    params=sl_params,
    label="SL",
    symbol=symbol,
    direction=direction,
    entry_order_id=oid,
    sl_order_id="",  # SL not yet placed
    price_display=sl,
)

if not sl_oid:
    # SL placement exhausted retries — rollback entry
    self._rollback_entry_after_protection_failure(
        ccxt_sym=ccxt_sym,
        rollback_side=reverse_side,
        rollback_size=rollback_size,
        symbol=symbol,
        direction=direction,
        entry_order_id=oid,
        original_error=Exception("SL placement exhausted after 3 retries"),
    )
    return None

log.info(f"  ↳ SL @ {sl:.4f} | order_id={sl_oid}")
```

**Step 3: Add SL repair to _repair_missing_protection_orders**

Find `_repair_missing_protection_orders` and add SL repair block before TP1 repair:

```python
def _repair_missing_protection_orders(self, bn_order_ids: set) -> None:
    """Re-send missing SL/TP1/TP2 orders for positions..."""
    for pos in self.positions:
        ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)
        reverse_side = "sell" if pos.direction == "LONG" else "buy"
        
        # === NEW: Repair SL if missing ===
        if not pos.sl_order_id:
            log.critical(
                "order_manager.repair_missing_sl: %s %s — re-sending protection order",
                pos.symbol, pos.direction,
                extra={
                    "event": "order_manager.repair_missing_sl",
                    "symbol": pos.symbol,
                    "direction": pos.direction,
                },
            )
            sl_params = {"stopPrice": pos.sl}
            if self.hedge_mode:
                sl_params["positionSide"] = pos.direction
            else:
                sl_params["reduceOnly"] = True
            new_sl_oid = self._retry_tp_order(
                ccxt_sym=ccxt_sym,
                order_type="STOP_MARKET",
                side=reverse_side,
                amount=pos.size,
                params=sl_params,
                label="SL_REPAIR",
                symbol=pos.symbol,
                direction=pos.direction,
                entry_order_id=pos.order_id,
                sl_order_id="",
                price_display=pos.sl,
            )
            if new_sl_oid:
                pos.sl_order_id = new_sl_oid
        
        # ... existing TP1/TP2 repair code ...
```

**Step 4: Run tests**

```bash
python -m pytest backend/tests/test_sl_retry.py -v --import-mode=importlib
```

Expected: PASS — all 3 tests pass.

```bash
python -m pytest backend/tests/test_tp_order_reliability.py backend/tests/test_order_manager_v2.py -v --import-mode=importlib
```

Expected: PASS — no regressions.

**Step 5: Commit**

```bash
git add exchange/__init__.py backend/tests/test_sl_retry.py
git commit -m "fix(exchange): add SL placement retry and repair mechanisms

SL placement previously had no retry — transient API errors caused
immediate rollback or orphan positions with no SL protection.

Changes:
- Reuse _retry_tp_order for SL (3 attempts, exponential backoff)
- On exhaustion: rollback entry (same as before)
- Add SL repair to _repair_missing_protection_orders (called during
  reconcile) — catches historical positions or exhausted retries

Mirrors TP retry mechanism from PR #38. Closes the gap where Binance
positions could exist with TP1/TP2 but no SL."
```

---

## PR #3: _move_sl_to_breakeven Retry

### Background
When TP1 hits, SL is moved to entry. If new SL placement fails:
- Old SL is cancelled
- New SL doesn't exist
- Remaining half-position is unprotected
- No retry, no recovery

### Task 3.1: Write test for breakeven SL retry

**Objective:** Verify _move_sl_to_breakeven retries on transient errors.

**Files:**
- Modify: `backend/tests/test_sl_retry.py` (add class)

**Step 1: Add failing test**

```python
class TestBreakevenSLRetry:
    """_move_sl_to_breakeven should retry new SL placement."""

    @patch("exchange._time.sleep")
    def test_be_sl_retry_on_transient_failure(self, mock_sleep, mgr, mock_client):
        """New SL fails transiently, then succeeds on retry."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=94000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="SL-OLD",
            tp1_order_id="TP1-1", tp2_order_id="TP2-1",
            tp1_hit=True,
        )
        mgr.positions.append(pos)
        # Set pos.sl to entry (TP1 already hit)
        pos.sl = pos.entry

        mock_client.exchange.create_order.side_effect = [
            TimeoutError("timed out"),  # New SL attempt 1 — transient
            {"id": "SL-NEW"},           # New SL attempt 2 — success
        ]

        mgr._move_sl_to_breakeven(pos)

        assert pos.sl_order_id == "SL-NEW"
        assert pos.sl == 95000  # Moved to entry
        assert mock_sleep.call_count == 1  # One retry delay

    @patch("exchange._time.sleep")
    def test_be_sl_exhausted_leaves_empty_for_repair(self, mock_sleep, mgr, mock_client):
        """If all retries fail, sl_order_id stays empty → reconcile repairs."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=94000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="SL-OLD",
            tp1_order_id="TP1-1", tp2_order_id="TP2-1",
            tp1_hit=True,
        )
        mgr.positions.append(pos)
        pos.sl = pos.entry
        pos.sl_order_id = "SL-OLD"

        mock_client.exchange.create_order.side_effect = TimeoutError("timed out")

        mgr._move_sl_to_breakeven(pos)

        # Old SL was cancelled, new SL exhausted → sl_order_id = ""
        assert pos.sl_order_id == ""
        # pos.sl was updated but order doesn't exist yet
        # Reconcile will detect empty sl_order_id and repair
```

**Step 2: Run test to verify failure**

```bash
python -m pytest backend/tests/test_sl_retry.py::TestBreakevenSLRetry -v --import-mode=importlib
```

Expected: FAIL — `AssertionError: assert pos.sl_order_id == "SL-NEW"`

**Step 3: Commit test**

```bash
git add backend/tests/test_sl_retry.py
git commit -m "test: add _move_sl_to_breakeven retry tests (RED phase)"
```

### Task 3.2: Implement breakeven SL retry

**Objective:** Wrap new SL placement in retry logic.

**Files:**
- Modify: `exchange/__init__.py:1113-1142` (_move_sl_to_breakeven)

**Step 1: Replace _move_sl_to_breakeven implementation**

Find `_move_sl_to_breakeven` (~line 1092) and replace the implementation:

```python
def _move_sl_to_breakeven(self, pos: Position) -> None:
    """TP1 hit sonrası SL'i entry'ye kaydır (server-side cancel + new order).

    Single-target branch (SMC v2, PR #S5.5): when pos.tp2 is None, the
    lifecycle has already done a full close on TP1 (no remaining size to
    protect). Skip the BE move entirely and instead cancel orphan SL/TP2
    reduceOnly orders on the exchange to prevent them lingering forever.
    Inert under v1 (v1 always sets numeric tp2).

    NEW: New SL placement uses retry with backoff. If all retries fail,
    sl_order_id is set to "" so reconcile's _repair_missing_protection_orders
    can place it on the next cycle.
    """
    if self.dry_run:
        pos.sl = pos.entry
        return

    ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)

    if pos.tp2 is None:
        # Single-target mode: full close already done by lifecycle.
        # Cancel orphan SL (TP1 already filled; TP2 was never placed).
        self._cancel_position_siblings(pos, ccxt_sym, reason="TP1_FULL_CLOSE")
        return

    # Cancel old SL
    if pos.sl_order_id:
        try:
            self.client.exchange.cancel_order(pos.sl_order_id, ccxt_sym)
        except Exception as e:
            log.warning(f"SL cancel failed for {pos.symbol}: {e} (continuing)")

    # Place new SL at breakeven with retry
    reverse_side = "sell" if pos.direction == "LONG" else "buy"
    remaining_size = pos.size / 2
    if not self.dry_run:
        try:
            res = self.client.exchange.amount_to_precision(ccxt_sym, remaining_size)
            if isinstance(res, str):
                remaining_size = float(res)
        except Exception as e:
            log.warning(f"Failed to format remaining SL size using exchange precision for {pos.symbol}: {e}")
    
    sl_params = {"stopPrice": pos.entry}
    if self.hedge_mode:
        sl_params["positionSide"] = pos.direction
    else:
        sl_params["reduceOnly"] = True

    # Use retry helper (3 attempts, exponential backoff)
    new_sl_oid = self._retry_tp_order(
        ccxt_sym=ccxt_sym,
        order_type="STOP_MARKET",
        side=reverse_side,
        amount=remaining_size,
        params=sl_params,
        label="SL_BE",
        symbol=pos.symbol,
        direction=pos.direction,
        entry_order_id=pos.order_id,
        sl_order_id=pos.sl_order_id,  # Old SL (may be cancelled)
        price_display=pos.entry,
    )

    if new_sl_oid:
        pos.sl = pos.entry
        pos.sl_order_id = new_sl_oid
        log.info(f"  ↳ New SL @ break-even {pos.entry:.4f} | order_id={pos.sl_order_id}")
    else:
        # All retries exhausted — set empty so reconcile repairs
        pos.sl = pos.entry  # Still update logical SL
        pos.sl_order_id = ""
        log.warning(
            "order_manager.be_sl_placement_failed: %s %s — "
            "sl_order_id cleared, reconcile will repair on next cycle",
            pos.symbol, pos.direction,
            extra={
                "event": "order_manager.be_sl_placement_failed",
                "symbol": pos.symbol,
                "direction": pos.direction,
                "sl_price": pos.sl,
            },
        )
```

**Step 2: Run tests**

```bash
python -m pytest backend/tests/test_sl_retry.py -v --import-mode=importlib
```

Expected: PASS — all 5 tests pass.

```bash
python -m pytest backend/tests/test_order_manager_v2.py backend/tests/test_tp_order_reliability.py -v --import-mode=importlib
```

Expected: PASS — no regressions.

**Step 3: Commit**

```bash
git add exchange/__init__.py backend/tests/test_sl_retry.py
git commit -m "fix(exchange): add retry to _move_sl_to_breakeven

Previously, if new SL placement at breakeven failed:
- Old SL was cancelled
- New SL didn't exist
- Remaining half-position was unprotected
- No retry or recovery mechanism

Changes:
- Wrap new SL placement in _retry_tp_order (3 attempts, backoff)
- On exhaustion: set sl_order_id='' so reconcile's
  _repair_missing_protection_orders places it on next cycle
- Update pos.sl regardless (logical state stays consistent)

Closes the gap where TP1-hit positions could lose SL protection."
```

---

## PR #4: Test Coverage Expansion

### Task 4.1: Add hedge mode test scenarios

**Objective:** Verify SL/TP parameter injection for hedge mode.

**Files:**
- Create: `backend/tests/test_hedge_mode_orders.py`

**Step 1: Write test**

```python
"""Test that hedge mode correctly injects positionSide into SL/TP orders."""
from unittest.mock import MagicMock
import pytest

from exchange import BinanceClient, OrderManager


@pytest.fixture
def mock_client():
    client = MagicMock(spec=BinanceClient)
    client.exchange = MagicMock()
    client.market_type = "futures"
    client.testnet = True
    client.to_ccxt_symbol.side_effect = lambda s: (
        s if ":" in s or client.market_type != "futures" else f"{s}:USDT"
    )
    return client


class TestHedgeModeOrderParameters:
    """Verify positionSide is used instead of reduceOnly in hedge mode."""

    def test_sl_uses_position_side_in_hedge_mode(self, mock_client):
        """SL order must use positionSide parameter in hedge mode."""
        mgr = OrderManager(mock_client, dry_run=False, hedge_mode=True)
        
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0},
            {"id": "SL-1"},
            {"id": "TP1-1"},
            {"id": "TP2-1"},
        ]

        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0,
            entry=95000, sl=94000, tp1=96000, tp2=97000,
        )

        assert pos is not None
        # Get SL order call (2nd create_order call)
        sl_call = mock_client.exchange.create_order.call_args_list[1]
        assert sl_call.args[1] == "STOP_MARKET"
        assert "positionSide" in sl_call.kwargs["params"]
        assert sl_call.kwargs["params"]["positionSide"] == "LONG"
        assert "reduceOnly" not in sl_call.kwargs["params"]

    def test_tp1_uses_position_side_in_hedge_mode(self, mock_client):
        """TP1 order must use positionSide parameter in hedge mode."""
        mgr = OrderManager(mock_client, dry_run=False, hedge_mode=True)
        
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0},
            {"id": "SL-1"},
            {"id": "TP1-1"},
            {"id": "TP2-1"},
        ]

        mgr.open_position(
            "BTC/USDT", "SHORT", 2.0,
            entry=3000, sl=3100, tp1=2900, tp2=2800,
        )

        # Get TP1 order call (3rd create_order call)
        tp1_call = mock_client.exchange.create_order.call_args_list[2]
        assert tp1_call.args[1] == "TAKE_PROFIT_MARKET"
        assert "positionSide" in tp1_call.kwargs["params"]
        assert tp1_call.kwargs["params"]["positionSide"] == "SHORT"
        assert "reduceOnly" not in tp1_call.kwargs["params"]

    def test_no_position_side_in_one_way_mode(self, mock_client):
        """In one-way mode (hedge_mode=False), use reduceOnly, not positionSide."""
        mgr = OrderManager(mock_client, dry_run=False, hedge_mode=False)
        
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0},
            {"id": "SL-1"},
            {"id": "TP1-1"},
            {"id": "TP2-1"},
        ]

        mgr.open_position(
            "ETH/USDT", "LONG", 5.0,
            entry=2000, sl=1950, tp1=2100, tp2=2200,
        )

        # SL call
        sl_call = mock_client.exchange.create_order.call_args_list[1]
        assert "reduceOnly" in sl_call.kwargs["params"]
        assert sl_call.kwargs["params"]["reduceOnly"] is True
        assert "positionSide" not in sl_call.kwargs["params"]

        # TP1 call
        tp1_call = mock_client.exchange.create_order.call_args_list[2]
        assert "reduceOnly" in tp1_call.kwargs["params"]
        assert "positionSide" not in tp1_call.kwargs["params"]
```

**Step 2: Run test**

```bash
python -m pytest backend/tests/test_hedge_mode_orders.py -v --import-mode=importlib
```

Expected: PASS (existing code already handles this correctly).

**Step 3: Commit**

```bash
git add backend/tests/test_hedge_mode_orders.py
git commit -m "test: add hedge mode order parameter validation tests

Verify that:
- hedge_mode=True → positionSide injected, reduceOnly omitted
- hedge_mode=False → reduceOnly injected, positionSide omitted

These tests lock in the correct behavior that PR #1 (main.py wiring)
depends on. Without these, a regression in parameter injection could
silently break SL/TP delivery in hedge mode."
```

### Task 4.2: Integration test for SL repair during reconcile

**Objective:** Verify SL repair is triggered during full reconcile cycle.

**Files:**
- Modify: `backend/tests/test_sl_retry.py` (add integration test)

**Step 1: Add integration test**

```python
class TestSLRepairIntegration:
    """End-to-end test: position with missing SL gets repaired during reconcile."""

    def test_reconcile_detects_and_repairs_missing_sl(self, mgr, mock_client):
        """Full reconcile cycle repairs missing SL."""
        # Setup: position open on exchange with missing SL
        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=94000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="",
            tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        # Mock exchange responses
        mock_client.get_open_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "contracts": 1.0, "side": "long"}
        ]
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "TP1-1", "type": "TAKE_PROFIT_MARKET"},
            {"id": "TP2-1", "type": "TAKE_PROFIT_MARKET"},
        ]
        # Simulate algo orders fetch (CCXT bug workaround)
        mock_client.exchange.fapiPrivateGetOpenAlgoOrders.return_value = [
            {"algoId": "TP1-1"},
            {"algoId": "TP2-1"},
        ]
        # Mock SL repair order
        mock_client.exchange.create_order.return_value = {"id": "SL-REPAIRED"}

        # Run reconcile
        closed = mgr.reconcile()

        # Verify SL was repaired
        assert pos.sl_order_id == "SL-REPAIRED"
        assert len(closed) == 0  # Position still open
        # Verify repair order was a STOP_MARKET with correct stopPrice
        repair_call = mock_client.exchange.create_order.call_args
        assert repair_call.args[1] == "STOP_MARKET"
        assert repair_call.kwargs["params"]["stopPrice"] == 94000
```

**Step 2: Run test**

```bash
python -m pytest backend/tests/test_sl_retry.py::TestSLRepairIntegration -v --import-mode=importlib
```

Expected: PASS.

**Step 3: Run full test suite**

```bash
python -m pytest backend/tests/ --ignore=external_repos --import-mode=importlib -q
```

Expected: All tests pass.

**Step 4: Commit**

```bash
git add backend/tests/test_sl_retry.py
git commit -m "test: add SL repair integration test with full reconcile

End-to-end test verifying:
- Position with sl_order_id='' is detected during reconcile
- _repair_missing_protection_orders places new SL
- SL repair uses correct STOP_MARKET type and stopPrice

Locks in the complete SL recovery path from exhaustion to repair."
```

---

## Verification Checklist

After implementing all 4 PRs:

- [ ] PR #1: main.py passes hedge_mode, state_dir, orphan_protector to OM
- [ ] PR #2: SL placement retries on transient errors (3 attempts)
- [ ] PR #2: SL repair added to _repair_missing_protection_orders
- [ ] PR #3: _move_sl_to_breakeven retries new SL placement
- [ ] PR #3: On exhaustion, sl_order_id='' for reconcile repair
- [ ] PR #4: Hedge mode tests verify positionSide injection
- [ ] PR #4: Integration test verifies SL repair during reconcile
- [ ] All existing tests still pass (no regressions)
- [ ] Each PR has atomic commit with descriptive message
- [ ] No changes to config.yaml, docker-compose, or production files

---

## Summary

This plan fixes 5 bugs across 3 critical areas:

1. **CLI wiring gap** (PR #1): main.py now matches bot_runner.py wiring
2. **SL resilience** (PR #2): SL gets same retry protection as TP + repair on reconcile
3. **Breakeven safety** (PR #3): TP1-hit SL move retries + repair fallback

All changes are non-breaking for production (bot_runner.py unaffected).
CLI mode (python main.py) becomes production-safe with hedge mode support.

**Timeline:** ~2 hours for full implementation (16 tasks × 7-8 min each).

**Risk:** Low — atomic PRs, comprehensive tests, no config changes.
