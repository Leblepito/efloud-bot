import pytest
from unittest.mock import Mock, patch
from engine.safe_orchestrator import SafeOrchestrator
from engine.risk.custom_calculator import CustomRiskCalculator

@pytest.fixture
def mock_config():
    return {
        'risk': {
            'max_loss_per_trade_usdt': 20.0,
            'target_stop_distance_pct': 10.0,
            'position_size_calculation': 'reverse_from_risk',
            'max_open_positions': 4,
            'min_rr': 2.0,
            'risk_per_trade_pct': 0.75,
            'min_confluence': 55,
            'recency_bars': 40,
            'sl_atr_buffer': 0.5,
            'daily_filter_strict': False
        },
        'exchange': {
            'leverage': 3,
            'margin_mode': 'isolated'
        },
        'symbols': {
            'mode': 'fixed',
            'fixed_core': ['BTC/USDT', 'ETH/USDT']
        },
        'operation': {
            'dry_run': True,
            'watch_only': False
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
            'ote_upper': 0.786,
            'ext_tp2': 1.618
        },
        'timeframes': {
            'htf': '4h',
            'mtf': '1h',
            'entry': '15m',
            'kline_limit': 500
        },
        'safety': {
            'daily_loss_limit_pct': 3.0,
            'weekly_drawdown_limit_pct': 8.0,
            'consecutive_loss_limit': 3,
            'consecutive_pause_min': 120,
            'starting_balance': 10000,
            'adx_trend_threshold': 25,
            'adx_range_threshold': 20,
            'volatile_atr_mult': 2.5,
            'max_position_notional_pct': 3.0,
            'max_total_exposure': 3.0,
            'max_holding_hours': 48,
            'max_pyramid_adds': 2,
            'min_sl_atr': 0.5,
            'max_sl_atr': 5.0,
            'emergency_balance_threshold': None,
            'reserve_balance': 0
        }
    }

def test_orchestrator_initializes_custom_risk_calculator(mock_config):
    """Test SafeOrchestrator properly initializes CustomRiskCalculator"""
    orchestrator = SafeOrchestrator(mock_config, state_dir="./test_state")

    assert hasattr(orchestrator, 'risk_calculator')
    assert isinstance(orchestrator.risk_calculator, CustomRiskCalculator)
    assert orchestrator.risk_calculator.max_loss_usdt == 20.0
    assert orchestrator.risk_calculator.leverage == 3
    assert orchestrator.risk_calculator.target_stop_pct == 0.10

def test_orchestrator_uses_custom_position_sizing():
    """Test orchestrator uses new position sizing calculation"""
    config = {
        'risk': {
            'max_loss_per_trade_usdt': 10.0,  # Reduced for testing
            'target_stop_distance_pct': 10.0,
            'position_size_calculation': 'reverse_from_risk',
            'risk_per_trade_pct': 0.75,
            'min_confluence': 55,
            'recency_bars': 40,
            'sl_atr_buffer': 0.5,
            'daily_filter_strict': False
        },
        'exchange': {'leverage': 3},
        'structure': {
            'swing_lookback': 5,
            'ob_sequential': 5,
            'body_mode': True,
            'eq_threshold_pct': 0.1,
            'range_lookback': 50
        },
        'fibonacci': {
            'ote_lower': 0.618,
            'ote_upper': 0.786,
            'ext_tp2': 1.618
        },
        'timeframes': {
            'htf': '4h',
            'mtf': '1h',
            'entry': '15m',
            'kline_limit': 500
        },
        'safety': {
            'daily_loss_limit_pct': 3.0,
            'weekly_drawdown_limit_pct': 8.0,
            'consecutive_loss_limit': 3,
            'consecutive_pause_min': 120,
            'starting_balance': 10000,
            'adx_trend_threshold': 25,
            'adx_range_threshold': 20,
            'volatile_atr_mult': 2.5,
            'max_position_notional_pct': 3.0,
            'max_total_exposure': 3.0,
            'max_holding_hours': 48,
            'max_pyramid_adds': 2,
            'min_sl_atr': 0.5,
            'max_sl_atr': 5.0,
            'emergency_balance_threshold': None,
            'reserve_balance': 0
        }
    }

    orchestrator = SafeOrchestrator(config, state_dir="./test_state")

    # Test position size calculation
    available_balance = 1000.0
    position_size = orchestrator.calculate_position_size('BTC/USDT', available_balance)

    # Expected: 10 / (0.10 * 3) = 33.33 USDT
    assert abs(position_size - 33.33) < 0.1

@patch('engine.permissions.PermissionManager')
def test_orchestrator_integrates_permission_manager(mock_permission_manager, mock_config):
    """Test SafeOrchestrator integrates PermissionManager"""
    mock_pm_instance = Mock()
    mock_permission_manager.return_value = mock_pm_instance
    mock_pm_instance.detect_all.return_value = {
        'BTC/USDT': Mock(tradeable=True),
        'ETH/USDT': Mock(tradeable=False)
    }

    orchestrator = SafeOrchestrator(mock_config, state_dir="./test_state")
    orchestrator._setup_permission_manager(Mock())  # Mock client

    permissions = orchestrator.get_symbol_permissions(['BTC/USDT', 'ETH/USDT'])

    assert 'BTC/USDT' in permissions
    assert 'ETH/USDT' in permissions
    mock_pm_instance.detect_all.assert_called_once()

@patch('engine.notifications.NotificationManager')
def test_orchestrator_sends_readonly_notifications(mock_notification_manager, mock_config):
    """Test SafeOrchestrator sends notifications for read-only symbols"""
    mock_nm_instance = Mock()
    mock_notification_manager.return_value = mock_nm_instance

    orchestrator = SafeOrchestrator(mock_config, state_dir="./test_state")

    # Setup notification manager
    orchestrator.notification_manager = mock_nm_instance

    # Simulate readonly signal
    signal_data = {
        'direction': 'BULLISH',
        'entry_price': 43250.0,
        'tp1': 45500.0,
        'sl': 41800.0,
        'confidence': 75
    }

    orchestrator.send_readonly_signal('ETH/USDT', signal_data)

    mock_nm_instance.signal_readonly.assert_called_once_with(
        symbol='ETH/USDT',
        direction='BULLISH',
        entry=43250.0,
        sl=41800.0,
        tp1=45500.0,
        tp2=0.0,
        confluence=75,
        reasons=[]
    )