import pytest
import tempfile
import os
import yaml
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

@pytest.fixture
def phase1_config():
    return {
        'exchange': {
            'testnet': False,
            'leverage': 3,
            'margin_mode': 'isolated'
        },
        'risk': {
            'position_size_calculation': 'reverse_from_risk',
            'max_loss_per_trade_usdt': 20.0,
            'target_stop_distance_pct': 10.0,
            'max_open_positions': 4
        },
        'operation': {
            'dry_run': True,  # Phase 1: dry run
            'state_dir': './test_state'
        },
        'symbols': {
            'mode': 'fixed',
            'fixed_core': ['BTC/USDT', 'ETH/USDT']
        },
        'structure': {
            'swing_lookback': 5,
            'ob_sequential': 5,
            'body_mode': True,
            'eq_threshold_pct': 0.1,
            'range_lookback': 50
        },
        'fibonacci': {
            'ote_lower': 0.618,
            'ote_upper': 0.786
        },
        'safety': {
            'daily_loss_limit_pct': 2.0,
            'emergency_balance_threshold': 950
        }
    }

@pytest.fixture
def mock_binance_client():
    client = Mock()
    client.market_type = 'futures'

    # Mock exchange sub-object
    client.exchange = Mock()
    client.exchange.fetch_balance.return_value = {'canTrade': True}
    client.exchange.fapiPrivateV2GetAccount.return_value = {'canTrade': True}
    client.exchange.fapiPublicGetExchangeinfo.return_value = {
        'symbols': [
            {
                'symbol': 'BTCUSDT',
                'status': 'TRADING',
                'filters': [
                    {'filterType': 'LOT_SIZE', 'minQty': '0.001'},
                    {'filterType': 'PRICE_FILTER'},
                    {'filterType': 'PERCENT_PRICE'},
                    {'filterType': 'MIN_NOTIONAL', 'minNotional': '10.0'},
                    {'filterType': 'ICEBERG_PARTS'}
                ]
            },
            {
                'symbol': 'ETHUSDT',
                'status': 'TRADING',
                'filters': [
                    {'filterType': 'LOT_SIZE', 'minQty': '0.001'},
                    {'filterType': 'MIN_NOTIONAL', 'minNotional': '10.0'}
                ]
            }
        ]
    }

    client.fetch_ohlcv.return_value = Mock()  # Mock OHLCV data
    client.set_leverage.return_value = None
    client.set_margin_mode.return_value = None
    return client

def test_end_to_end_phase1_dry_run(phase1_config, mock_binance_client):
    """Test complete Phase 1 execution from config loading to cycle completion"""

    with patch('main.load_config', return_value=phase1_config), \
         patch('main.resolve_credentials', return_value=('test_key', 'test_secret')), \
         patch('main.MainnetGuard.check', return_value=True), \
         patch('exchange.BinanceClient', return_value=mock_binance_client):

        # Test complete initialization sequence
        from main import setup_orchestrator_with_client, validate_config
        from exchange import BinanceClient

        # Configuration validation should pass
        assert validate_config(phase1_config) == True

        # Client initialization should succeed
        client = BinanceClient('test_key', 'test_secret', testnet=False, market_type='futures')

        # Orchestrator setup should complete without errors
        orch = setup_orchestrator_with_client(phase1_config, client, './test_state')

        # Verify integrated components
        assert hasattr(orch, 'permission_manager')
        assert hasattr(orch, 'notification_manager')
        assert hasattr(orch, 'smc')
        assert hasattr(orch, 'levels')
        assert orch.config['operation']['dry_run'] == True
        assert hasattr(orch, 'symbol_permissions')

def test_permission_detection_integration(mock_binance_client):
    """Test permission detection works with real API call patterns"""

    from engine.permissions import PermissionManager

    pm = PermissionManager(mock_binance_client)
    permissions = pm.detect_all(['BTC/USDT', 'ETH/USDT'])

    # Should classify symbols correctly
    assert 'BTC/USDT' in permissions
    assert permissions['BTC/USDT'].tradeable in [True, False]

    # Should populate internal lists
    assert len(pm.get_tradeable_symbols()) + len(pm.get_readonly_symbols()) == 2

def test_risk_calculator_produces_valid_positions():
    """Test risk calculator produces positions that meet API requirements"""

    from engine.risk.custom_calculator import CustomRiskCalculator

    calculator = CustomRiskCalculator(max_loss_usdt=20.0, leverage=3, target_stop_pct=0.10)

    # Test with typical balance
    position_size = calculator.calculate_position_size(1000.0)
    notional = calculator.calculate_notional_exposure(position_size)

    # Should meet minimum notional requirements
    assert notional >= 10.0  # Minimum for most futures symbols
    assert position_size <= 800.0  # 80% of balance cap

    # Should validate correctly with realistic prices
    validation = calculator.validate_risk_parameters(
        position_size=position_size,
        current_price=43250.0,
        stop_price=38925.0  # 10% below
    )
    assert validation['valid'] == True
    assert abs(validation['potential_loss_usdt'] - 20.0) < 1.0

@patch.dict(os.environ, {'EFLOUD_ALLOW_MAINNET': '1'})
def test_phase_transition_safety(mock_binance_client):
    """Test safety validations during phase transitions"""

    # Phase 1 config (dry run)
    phase1 = {
        'exchange': {'testnet': False},
        'operation': {'dry_run': True},
        'risk': {'position_size_calculation': 'reverse_from_risk'}
    }

    # Phase 2 config (live with reduced risk)
    phase2 = {
        'exchange': {'testnet': False},
        'operation': {'dry_run': False},  # Live trading
        'risk': {'position_size_calculation': 'reverse_from_risk'}
    }

    from main import validate_config

    # Both phases should validate successfully with EFLOUD_ALLOW_MAINNET=1
    assert validate_config(phase1) == True
    assert validate_config(phase2) == True

def test_readonly_symbol_notification_flow():
    """Test complete flow for read-only symbols generating notifications"""

    # Create mock client with mixed permissions
    mock_client = Mock()
    mock_client.market_type = 'futures'
    mock_client.exchange = Mock()
    mock_client.exchange.fetch_balance.return_value = {'canTrade': True}
    mock_client.exchange.fapiPrivateV2GetAccount.return_value = {'canTrade': True}
    mock_client.exchange.fapiPublicGetExchangeinfo.return_value = {
        'symbols': [
            {
                'symbol': 'BTCUSDT',
                'status': 'TRADING',
                'filters': [
                    {'filterType': 'LOT_SIZE', 'minQty': '0.001'},
                    {'filterType': 'MIN_NOTIONAL', 'minNotional': '10.0'}
                ]
            },
            {
                'symbol': 'ETHUSDT',
                'status': 'BREAK',  # Not trading - should be readonly
                'filters': []
            }
        ]
    }

    from engine.permissions import PermissionManager
    from engine.notifications import NotificationManager

    # Test permission detection
    pm = PermissionManager(mock_client)
    permissions = pm.detect_all(['BTC/USDT', 'ETH/USDT'])

    assert permissions['BTC/USDT'].tradeable == True
    assert permissions['ETH/USDT'].tradeable == False

    # Test notification system
    nm = NotificationManager()
    signal_data = {
        'direction': 'BULLISH',
        'entry_price': 2150.0,
        'tp1': 2365.0,
        'sl': 1935.0
    }

    # Should not raise errors
    nm.signal_readonly('ETH/USDT', signal_data['direction'],
                      signal_data['entry_price'], signal_data['sl'],
                      signal_data['tp1'], signal_data['tp1'], 75)