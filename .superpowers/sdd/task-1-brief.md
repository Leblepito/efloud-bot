# Task Brief: Task 1

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
