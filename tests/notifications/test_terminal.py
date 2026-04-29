import pytest
from io import StringIO
import sys
from unittest.mock import patch, Mock
from engine.notifications.terminal import NotificationManager

def test_send_readonly_signal_formats_correctly():
    """Test terminal notification formatting for read-only signals"""
    manager = NotificationManager()

    signal_data = {
        'direction': 'BULLISH',
        'entry_price': 43250.75,
        'tp1': 45500.0,
        'sl': 41800.0,
        'confidence': 75
    }

    # Capture stdout
    captured_output = StringIO()
    with patch('sys.stdout', captured_output):
        manager.send_readonly_signal('BTC/USDT', signal_data)

    output = captured_output.getvalue()
    expected = "🔍 [READONLY] BTC/USDT: BULLISH SIGNAL | Entry: 43,251 | TP1: 45,500 | SL: 41,800"

    assert expected in output

def test_send_readonly_signal_handles_bearish():
    """Test notification formatting for bearish signals"""
    manager = NotificationManager()

    signal_data = {
        'direction': 'BEARISH',
        'entry_price': 2150.25,
        'tp1': 2050.0,
        'sl': 2250.0,
        'confidence': 68
    }

    captured_output = StringIO()
    with patch('sys.stdout', captured_output):
        manager.send_readonly_signal('ETH/USDT', signal_data)

    output = captured_output.getvalue()
    expected = "🔍 [READONLY] ETH/USDT: BEARISH SIGNAL | Entry: 2,150 | TP1: 2,050 | SL: 2,250"

    assert expected in output

@patch('engine.notifications.terminal.log')
def test_send_readonly_signal_logs_to_file(mock_logger):
    """Test that signals are also logged to file"""
    manager = NotificationManager()

    signal_data = {
        'direction': 'BULLISH',
        'entry_price': 100.0,
        'tp1': 110.0,
        'sl': 95.0
    }

    manager.send_readonly_signal('TEST/USDT', signal_data)

    # Verify logger was called with the signal message
    assert mock_logger.info.call_count == 2  # Initialization + signal message
    # Check the signal message call (second call)
    signal_call = mock_logger.info.call_args_list[1]
    expected_message = "🔍 [READONLY] TEST/USDT: BULLISH SIGNAL | Entry: 100 | TP1: 110 | SL: 95"
    assert signal_call[0][0] == expected_message

def test_format_price_handles_various_ranges():
    """Test price formatting for different price ranges"""
    manager = NotificationManager()

    # High price (BTC range)
    assert manager._format_price(43250.75) == "43,251"

    # Medium price (ETH range)
    assert manager._format_price(2150.25) == "2,150"

    # Low price (altcoin range)
    assert manager._format_price(0.12345) == "0.123"

    # Very low price
    assert manager._format_price(0.000123) == "0.000123"