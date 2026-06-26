# Task Brief: Task 2

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
