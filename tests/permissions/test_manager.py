import pytest
from unittest.mock import Mock, MagicMock
from engine.permissions.manager import PermissionManager

@pytest.fixture
def mock_client():
    client = Mock()
    client.get_futures_account.return_value = {'canTrade': True}
    client.get_exchange_info.return_value = {
        'symbols': [
            {
                'symbol': 'BTCUSDT',
                'status': 'TRADING',
                'filters': [
                    {'filterType': 'LOT_SIZE', 'minQty': '0.001'},
                    {'filterType': 'PRICE_FILTER'},
                    {'filterType': 'PERCENT_PRICE'},
                    {'filterType': 'MIN_NOTIONAL', 'minNotional': '10.0'},
                    {'filterType': 'ICEBERG_PARTS'},
                    {'filterType': 'MIN_NOTIONAL', 'minNotional': '10.0'}  # Index 5
                ]
            },
            {
                'symbol': 'ETHUSDT',
                'status': 'BREAK',  # Not trading
                'filters': [
                    {'filterType': 'LOT_SIZE', 'minQty': '0.001'},
                    {'filterType': 'PRICE_FILTER'},
                    {'filterType': 'PERCENT_PRICE'},
                    {'filterType': 'MIN_NOTIONAL', 'minNotional': '10.0'},
                    {'filterType': 'ICEBERG_PARTS'},
                    {'filterType': 'MIN_NOTIONAL', 'minNotional': '1000.0'}  # Too high minimum
                ]
            }
        ]
    }
    return client

def test_detect_permissions_separates_tradeable_and_readonly(mock_client):
    """Test permission detection separates symbols correctly"""
    manager = PermissionManager(mock_client)
    symbols = ['BTC/USDT', 'ETH/USDT']

    permissions = manager.detect_permissions(symbols)

    assert permissions['BTC/USDT'] == 'tradeable'
    assert permissions['ETH/USDT'] == 'readonly'
    assert 'BTC/USDT' in manager.tradeable_symbols
    assert 'ETH/USDT' in manager.readonly_symbols

def test_can_trade_symbol_validates_trading_status(mock_client):
    """Test symbol trading status validation"""
    manager = PermissionManager(mock_client)
    account_info = {'canTrade': True}

    # BTC should be tradeable (status: TRADING)
    can_trade_btc = manager.can_trade_symbol('BTC/USDT', account_info)
    assert can_trade_btc == True

    # ETH should not be tradeable (status: BREAK)
    can_trade_eth = manager.can_trade_symbol('ETH/USDT', account_info)
    assert can_trade_eth == False

def test_can_trade_symbol_validates_account_permissions(mock_client):
    """Test account trading permission validation"""
    manager = PermissionManager(mock_client)
    account_info = {'canTrade': False}  # No trading permission

    can_trade = manager.can_trade_symbol('BTC/USDT', account_info)
    assert can_trade == False

def test_can_trade_symbol_validates_minimum_notional(mock_client):
    """Test minimum notional requirement validation"""
    manager = PermissionManager(mock_client)
    account_info = {'canTrade': True}

    # ETH has 1000 USDT minimum notional, our test position (67 * 3 = 201) is too small
    can_trade = manager.can_trade_symbol('ETH/USDT', account_info)
    assert can_trade == False

def test_can_trade_symbol_handles_api_errors(mock_client):
    """Test graceful handling of API errors"""
    mock_client.get_exchange_info.side_effect = Exception("API Error")
    manager = PermissionManager(mock_client)
    account_info = {'canTrade': True}

    can_trade = manager.can_trade_symbol('BTC/USDT', account_info)
    assert can_trade == False  # Fail safe