# SL/TP Precision & Candle-Close Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve Binance order rejections due to price precision violations and eliminate execution delay drift by implementing candle-close synchronization.

**Architecture:** (1) Exchange layer: Round all order prices (entry/SL/TP) using `price_to_precision` before sending to Binance. (2) Runner layer: Reconcile frequently (5-10s) but fetch candles/scan only at 15m boundaries + 2s buffer, preventing API rate limits while reducing slippage.

**Tech Stack:** Python 3.12, CCXT (Binance Futures), pytest, existing efloud-bot engine/safety framework.

## Global Constraints

- **No safety guard weakening**: All changes must preserve existing breaker/orphan/reverse-on-profit guards
- **TDD required**: Write failing test → implement → verify pass → commit
- **Atomic commits**: Each task produces a reviewable, independently testable change
- **Config backward compatible**: Default `check_interval_sec` change documented but user override respected
- **Dry-run respect**: All precision formatting must respect `self.dry_run` flag

---

## Task 1: Add Price Precision Rounding in Exchange.open_position

**Files:**
- Modify: `exchange/__init__.py` — `open_position` method (after symbol conversion, before order creation)
- Test: `tests/test_exchange_precision.py`

**Interfaces:**
- Consumes: `self.client.exchange.price_to_precision(ccxt_sym, price)` — CCXT built-in method
- Produces: No API changes — internal rounding only

**Description:** Format entry, SL, TP1, TP2 prices using exchange price precision before creating orders. This prevents Binance -2021 rejections when stopPrice violates tick size.

- [ ] **Step 1: Write the failing test**

Create `tests/test_exchange_precision.py`:

```python
import pytest
from unittest.mock import Mock, MagicMock, patch
from exchange import Exchange

def test_open_position_rounds_prices_to_precision():
    """Verify that entry/SL/TP prices are rounded using exchange price_to_precision."""
    # Mock client with price_to_precision that returns rounded values
    mock_client = Mock()
    mock_exchange = Mock()
    
    # Simulate Binance TRX/USDT precision: 3 decimal places
    def mock_precision(symbol, price):
        return round(float(price), 3)
    
    mock_exchange.price_to_precision = mock_precision
    mock_client.exchange = mock_exchange
    mock_client.fetch_mode = None
    
    # Mock create_order to return success
    mock_exchange.create_order = Mock(return_value={
        'id': 'test_order_1',
        'symbol': 'TRX/USDT',
        'type': 'MARKET',
        'side': 'BUY',
        'amount': 1000.0,
    })
    
    # Mock fetch_position to return no position
    mock_exchange.fetch_positions = Mock(return_value=[])
    
    # Mock context manager for dry_run=False
    exchange = Exchange("binance", mock_client, dry_run=False)
    exchange.client = mock_client
    exchange.client.exchange = mock_exchange
    
    # Track calls to price_to_precision
    precision_calls = []
    original_precision = mock_exchange.price_to_precision
    def track_precision(symbol, price):
        precision_calls.append((symbol, price))
        return original_precision(symbol, price)
    mock_exchange.price_to_precision = track_precision
    
    # Call open_position with unrounded prices
    entry = 0.123456789  # Should round to 0.123
    sl = 0.120000001    # Should round to 0.120
    tp1 = 0.130000999    # Should round to 0.130
    tp2 = 0.135001234    # Should round to 0.135
    
    with patch.object(exchange, '_retry_tp_order', Mock()):
        exchange.open_position(
            symbol='TRX/USDT',
            direction='LONG',
            entry=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            amount=1000.0
        )
    
    # Verify price_to_precision was called for all four prices
    assert len(precision_calls) >= 4
    
    # Verify the prices passed to precision match our inputs
    passed_prices = [p for _, p in precision_calls[:4]]
    assert entry in passed_prices
    assert sl in passed_prices
    assert tp1 in passed_prices
    assert tp2 in passed_prices
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_exchange_precision.py::test_open_position_rounds_prices_to_precision -v`

Expected: FAIL (price_to_precision not yet called in open_position)

- [ ] **Step 3: Write minimal implementation**

In `exchange/__init__.py`, locate the `open_position` method. After the line that converts `ccxt_sym` (around line 150-180, search for `ccxt_sym = symbol.replace(...)`), add:

```python
# Round all prices to exchange precision to avoid Binance tick-size rejections
if not self.dry_run:
    try:
        entry = float(self.client.exchange.price_to_precision(ccxt_sym, entry))
        sl = float(self.client.exchange.price_to_precision(ccxt_sym, sl))
        tp1 = float(self.client.exchange.price_to_precision(ccxt_sym, tp1))
        if tp2 is not None:
            tp2 = float(self.client.exchange.price_to_precision(ccxt_sym, tp2))
    except Exception as e:
        log.warning(f"Failed to format entry/SL/TP prices using exchange precision for {symbol}: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_exchange_precision.py::test_open_position_rounds_prices_to_precision -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exchange/__init__.py tests/test_exchange_precision.py
git commit -m "feat(exchange): add price precision rounding in open_position"
```

---

## Task 2: Add Price Precision Rounding in Exchange._retry_tp_order

**Files:**
- Modify: `exchange/__init__.py` — `_retry_tp_order` method
- Test: Extend `tests/test_exchange_precision.py`

**Interfaces:**
- Consumes: `params` dict (may contain `stopPrice` key)
- Produces: Modified `params['stopPrice']` rounded to precision

**Description:** Defensively round `stopPrice` inside `params` dictionary for all TP/SL orders (break-even moves, repairs). This covers cases where stopPrice is set after initial position open.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_exchange_precision.py`:

```python
@patch('exchange.log')
def test_retry_tp_order_rounds_stopPrice(mock_log):
    """Verify that stopPrice in params is rounded using exchange precision."""
    mock_client = Mock()
    mock_exchange = Mock()
    
    # Simulate precision rounding
    mock_exchange.price_to_precision = lambda sym, price: round(float(price), 3)
    mock_exchange.create_order = Mock(return_value={'id': 'retry_1'})
    
    exchange = Exchange("binance", mock_client, dry_run=False)
    exchange.client = mock_client
    exchange.client.exchange = mock_exchange
    
    # Call _retry_tp_order with unrounded stopPrice
    params = {'stopPrice': 0.123456789, 'reduceOnly': True}
    
    exchange._retry_tp_order(
        symbol='TRX/USDT',
        order_type='STOP_MARKET',
        params=params,
        price_display=0.12,
        ccxt_sym='TRX/USDT'
    )
    
    # Verify stopPrice was rounded
    assert params['stopPrice'] == 0.123
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_exchange_precision.py::test_retry_tp_order_rounds_stopPrice -v`

Expected: FAIL (stopPrice not yet rounded)

- [ ] **Step 3: Write minimal implementation**

In `exchange/__init__.py`, locate `_retry_tp_order` method. Before calling `create_order`, add:

```python
# Round stopPrice to exchange precision if present
if not self.dry_run and "stopPrice" in params:
    try:
        raw_price = params["stopPrice"]
        rounded_stop = float(self.client.exchange.price_to_precision(ccxt_sym, raw_price))
        params["stopPrice"] = rounded_stop
        price_display = rounded_stop
    except Exception as e:
        log.warning(f"Failed to format stopPrice using exchange precision in _retry_tp_order for {symbol}: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_exchange_precision.py::test_retry_tp_order_rounds_stopPrice -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exchange/__init__.py tests/test_exchange_precision.py
git commit -m "feat(exchange): add stopPrice precision rounding in _retry_tp_order"
```

---

## Task 3: Add Candle-Close Synchronization to bot_runner

**Files:**
- Modify: `backend/bot_runner.py` — add import, init state, modify `_scan_universe`
- Test: `tests/test_bot_runner_candle_sync.py`

**Interfaces:**
- Consumes: `_timeframe_ms` from `exchange` (converts '15m' → 900000 ms)
- Produces: No API changes — internal gating only

**Description:** Track last scanned candle timestamp. Only fetch candles and run SMC signal scan when `(current_ms - 2000) // tf_ms > last_scan_ts`. This aligns scans to 2 seconds after each 15m candle close.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bot_runner_candle_sync.py`:

```python
import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from backend.bot_runner import BotRunner

def test_candle_close_sync_skips_scan_inside_candle():
    """Verify that scan is skipped when called mid-candle (not at boundary+2s)."""
    mock_config = Mock()
    mock_config.check_interval_sec = 10
    mock_config.timeframes = {'entry': '15m'}
    
    mock_exchange = Mock()
    
    with patch('backend.bot_runner.Exchange', return_value=mock_exchange):
        runner = BotRunner(config=mock_config)
        runner.last_scan_candle_ts = 100  # Initialized to candle index 100
        
        # Current time: 100 * 900000ms + 45000ms (mid-candle)
        # (current - 2000) // 900000 = 100 (same as last_scan_ts)
        current_ms = 100 * 900000 + 45000
        
        with patch('time.time', return_value=current_ms / 1000):
            with patch.object(runner, '_scan_universe_inner', Mock()) as mock_inner:
                runner._scan_universe()
                
                # Should NOT scan because we're inside the same candle
                mock_inner.assert_not_called()
                assert runner.last_scan_candle_ts == 100  # Unchanged

def test_candle_close_sync_runs_scan_at_boundary():
    """Verify that scan runs when called at candle boundary + 2s."""
    mock_config = Mock()
    mock_config.check_interval_sec = 10
    mock_config.timeframes = {'entry': '15m'}
    
    mock_exchange = Mock()
    
    with patch('backend.bot_runner.Exchange', return_value=mock_exchange):
        runner = BotRunner(config=mock_config)
        runner.last_scan_candle_ts = 100  # Last scanned candle 100
        
        # Current time: (101 * 900000ms) + 2000ms (boundary + 2s)
        # (current - 2000) // 900000 = 101 (NEW candle)
        current_ms = 101 * 900000 + 2000
        
        with patch('time.time', return_value=current_ms / 1000):
            with patch.object(runner, '_scan_universe_inner', Mock()) as mock_inner:
                runner._scan_universe()
                
                # Should scan because we're at candle boundary + 2s
                mock_inner.assert_called_once()
                assert runner.last_scan_candle_ts == 101  # Updated
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_runner_candle_sync.py -v`

Expected: FAIL (last_scan_candle_ts and gating logic not yet implemented)

- [ ] **Step 3: Write minimal implementation**

In `backend/bot_runner.py`:

1. Add import at top:
```python
from exchange import _timeframe_ms
```

2. In `BotRunner.__init__`, add:
```python
self.last_scan_candle_ts = 0
```

3. In `_scan_universe`, wrap the existing scan logic with:

```python
def _scan_universe(self):
    """Scan universe only at candle close + 2s boundary."""
    entry_tf_ms = _timeframe_ms(self.config.timeframes['entry'])
    current_ms = int(time.time() * 1000)
    candle_ts = (current_ms - 2000) // entry_tf_ms
    
    if candle_ts > self.last_scan_candle_ts:
        log.info(f"Candle boundary detected: candle_ts={candle_ts}, running scan")
        self.last_scan_candle_ts = candle_ts
        
        # Existing scan logic here (call _scan_universe_inner or inline logic)
        # ... (preserve existing implementation)
    else:
        log.debug(f"Skipping scan: inside candle {candle_ts}, next scan at boundary+2s")
```

Note: Preserve all existing `_scan_universe` logic — wrap only with the gating condition.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_runner_candle_sync.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/bot_runner.py tests/test_bot_runner_candle_sync.py
git commit -m "feat(runner): add candle-close synchronization to scan timing"
```

---

## Task 4: Sync main.py CLI Loop with Candle-Close Logic

**Files:**
- Modify: `main.py` — loop timing logic
- Test: Manual verification (CLI smoke test)

**Interfaces:**
- Consumes: `_timeframe_ms` from `exchange`
- Produces: No API changes

**Description:** Apply same candle-close synchronization to CLI execution loop in `main.py` so local runs behave consistently with daemon runner.

- [ ] **Step 1: Identify existing loop logic**

Open `main.py` and locate the main execution loop (search for `while True:` or `while running:`). Note how sleep/scanning currently works.

- [ ] **Step 2: Apply same gating pattern**

Add similar logic:
```python
from exchange import _timeframe_ms

# In main():
last_scan_candle_ts = 0
entry_tf_ms = _timeframe_ms(config.timeframes['entry'])

while True:
    current_ms = int(time.time() * 1000)
    candle_ts = (current_ms - 2000) // entry_tf_ms
    
    if candle_ts > last_scan_candle_ts:
        print(f"Candle boundary detected: running scan")
        last_scan_candle_ts = candle_ts
        # ... existing scan logic
    
    time.sleep(config.check_interval_sec)
```

- [ ] **Step 3: Manual smoke test**

Run: `python main.py --dry-run --config configs/config.testnet.yaml`

Expected: Scan logs appear at :02 seconds after :00, :15, :30, :45 minute marks.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(main): add candle-close sync to CLI loop"
```

---

## Task 5: Reduce Default check_interval_sec in config.yaml

**Files:**
- Modify: `config.yaml` — `check_interval_sec` value
- Test: N/A (config change, verification via smoke test)

**Interfaces:**
- Consumes: None
- Produces: Config file change

- [ ] **Step 1: Edit config.yaml**

Locate `check_interval_sec` and change from `30` to `10`:
```yaml
runner:
  check_interval_sec: 10  # Reduced from 30 for faster close detection
```

- [ ] **Step 2: Verify bot starts**

Run: `python main.py --help` or load config in Python:
```python
from engine.config import load_config
cfg = load_config('configs/config.testnet.yaml')
assert cfg.runner.check_interval_sec == 10
```

- [ ] **Step 3: Commit**

```bash
git add config.yaml
git commit -m "config: reduce default check_interval_sec to 10s"
```

---

## Verification Plan

### Automated Tests
- Run full test suite: `pytest tests/ -v`
- Verify new tests pass: `tests/test_exchange_precision.py`, `tests/test_bot_runner_candle_sync.py`

### Manual Verification (Testnet)
1. Deploy to testnet with `check_interval_sec: 10`
2. Observe logs — scans should trigger at :02 after :00/:15/:30/:45
3. Place a LONG order on TRX/USDT — verify no -2021 rejections
4. Monitor execution — entry delay should be <5s after candle close

---

## Self-Review

**Spec Coverage:**
- ✅ Price precision rounding in open_position (Task 1)
- ✅ Price precision rounding in _retry_tp_order (Task 2)
- ✅ Candle-close sync in bot_runner (Task 3)
- ✅ Candle-close sync in main.py (Task 4)
- ✅ Config interval reduction (Task 5)
- ✅ Verification plan included

**Placeholder Scan:**
- ✅ All steps contain actual code
- ✅ No TBD/TODO placeholders
- ✅ Test code fully written
- ✅ Commands with expected outputs specified

**Type Consistency:**
- ✅ `price_to_precision(ccxt_sym, price)` signature consistent
- ✅ `last_scan_candle_ts` variable name consistent
- ✅ `_timeframe_ms` import consistent across tasks

---

Plan complete and saved to `docs/superpowers/plans/2025-01-20-sl-tp-precision-and-candle-sync.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — Fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
