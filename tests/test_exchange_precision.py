"""
Price precision rounding tests for Exchange.open_position.

TDD: Test verifies that entry/SL/TP prices are rounded using exchange
price_to_precision before orders are created, preventing Binance -2021
rejections when stopPrice violates tick size requirements.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from exchange import OrderManager


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
        'price': 0.123,  # Fill price
    })

    # Mock fetch_positions to return no position
    mock_exchange.fetch_positions = Mock(return_value=[])

    # Mock get_price for entry-drift guard (return exact entry to pass guard)
    mock_client.get_price = Mock(return_value=0.123456789)

    # Mock to_ccxt_symbol
    mock_client.to_ccxt_symbol = Mock(return_value='TRX/USDT')

    # Mock context manager for dry_run=False
    order_mgr = OrderManager(mock_client, dry_run=False)
    order_mgr.client = mock_client
    order_mgr.client.exchange = mock_exchange
    order_mgr.hedge_mode = False  # One-way mode
    order_mgr.max_entry_drift_pct = 0  # Disable drift guard

    # Track calls to price_to_precision
    precision_calls = []
    original_precision = mock_exchange.price_to_precision

    def track_precision(symbol, price):
        precision_calls.append((symbol, price))
        return original_precision(symbol, price)

    mock_exchange.price_to_precision = track_precision

    # Mock _retry_tp_order to avoid actual order creation
    with patch.object(order_mgr, '_retry_tp_order', Mock(return_value='mock_sl_order')):
        # Call open_position with unrounded prices
        entry = 0.123456789  # Should round to 0.123
        sl = 0.120000001    # Should round to 0.120
        tp1 = 0.130000999    # Should round to 0.130
        tp2 = 0.135001234    # Should round to 0.135

        order_mgr.open_position(
            symbol='TRX/USDT',
            direction='LONG',
            entry=entry,
            size=1000.0,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
        )

    # Verify price_to_precision was called for all four prices
    assert len(precision_calls) >= 4, f"Expected at least 4 precision calls, got {len(precision_calls)}"

    # Verify the prices passed to precision match our inputs
    passed_prices = [p for _, p in precision_calls[:4]]
    assert entry in passed_prices, f"Entry {entry} not found in {passed_prices}"
    assert sl in passed_prices, f"SL {sl} not found in {passed_prices}"
    assert tp1 in passed_prices, f"TP1 {tp1} not found in {passed_prices}"
    assert tp2 in passed_prices, f"TP2 {tp2} not found in {passed_prices}"

    print("✓ Test passed: price_to_precision called for entry, SL, TP1, TP2")
