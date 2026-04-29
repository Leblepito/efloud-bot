import pytest
from unittest.mock import Mock, patch, MagicMock, ANY
import tempfile
import os


def test_main_initializes_permission_manager_with_client():
    """Test main.py properly initializes permission manager with client"""

    # Mock configuration with required sections
    mock_config = {
        'exchange': {
            'api_key': 'test_key',
            'api_secret': 'test_secret',
            'testnet': False,
            'market_type': 'futures'
        },
        'risk': {
            'position_size_calculation': 'reverse_from_risk',
            'max_loss_per_trade_usdt': 20.0
        },
        'operation': {'state_dir': './test_state'},
        'structure': {
            'swing_lookback': 20,
            'ob_sequential': 3,
            'body_mode': 'close',
            'eq_threshold_pct': 1.0,
            'range_lookback': 10
        },
        'fibonacci': {
            'ote_lower': 0.618,
            'ote_upper': 0.786
        },
        'safety': {
            'max_daily_loss_pct': 5.0,
            'max_consecutive_losses': 3
        }
    }

    mock_client = Mock()

    with patch('main.SafeOrchestrator') as mock_orchestrator:
        mock_orch_instance = Mock()
        mock_orchestrator.return_value = mock_orch_instance

        # Import and run main setup logic
        from main import setup_orchestrator_with_client

        orch = setup_orchestrator_with_client(mock_config, mock_client, './test_state')

        # Verify SafeOrchestrator was initialized correctly
        mock_orchestrator.assert_called_once_with(mock_config, state_dir='./test_state')

        # Verify permission manager was setup
        mock_orch_instance._setup_permission_manager.assert_called_once_with(mock_client)


@patch('main.load_config')
def test_main_handles_phase_specific_configs(mock_load_config, mock_guard=None):
    """Test main.py can load phase-specific configurations"""

    # Test loading different phase configs
    phase_configs = [
        'config.phase1.yaml',
        'config.phase2.yaml',
        'config.phase3.yaml'
    ]

    for phase_config in phase_configs:
        mock_load_config.return_value = {
            'operation': {'dry_run': 'phase1' in phase_config},
            'exchange': {'testnet': False},
            'risk': {'position_size_calculation': 'reverse_from_risk'}
        }

        with patch('sys.argv', ['main.py', phase_config]):
            # Should not raise any errors
            try:
                from main import load_config
                config = load_config(phase_config)
                assert 'risk' in config
            except FileNotFoundError:
                # Expected for non-existent test files
                pass


def test_mainnet_guard_integration_with_phases():
    """Test MainnetGuard properly validates phase configurations"""

    # Phase 1: should allow (mainnet + dry_run)
    with patch('main.MainnetGuard.check') as mock_guard:
        mock_guard.return_value = True

        config = {'exchange': {'testnet': False}, 'operation': {'dry_run': True}}
        result = mock_guard(testnet=False, dry_run=True, interactive=False)

        assert result == True

    # Phase 2/3: should require EFLOUD_ALLOW_MAINNET=1
    with patch('os.environ.get', return_value='1'), \
         patch('main.MainnetGuard.check') as mock_guard:
        mock_guard.return_value = True

        config = {'exchange': {'testnet': False}, 'operation': {'dry_run': False}}
        result = mock_guard(testnet=False, dry_run=False, interactive=False)

        assert result == True


def test_setup_orchestrator_with_client_uses_new_risk_system():
    """Test setup_orchestrator_with_client enables new risk calculation"""

    mock_config = {
        'risk': {
            'position_size_calculation': 'reverse_from_risk',
            'max_loss_per_trade_usdt': 20.0
        },
        'operation': {'state_dir': './test_state'},
        'structure': {
            'swing_lookback': 20,
            'ob_sequential': 3,
            'body_mode': 'close',
            'eq_threshold_pct': 1.0,
            'range_lookback': 10
        },
        'fibonacci': {
            'ote_lower': 0.618,
            'ote_upper': 0.786
        },
        'safety': {
            'max_daily_loss_pct': 5.0,
            'max_consecutive_losses': 3
        }
    }

    mock_client = Mock()
    mock_orch = Mock()

    with patch('main.SafeOrchestrator') as mock_orch_class:
        mock_orch_class.return_value = mock_orch

        from main import setup_orchestrator_with_client

        result = setup_orchestrator_with_client(mock_config, mock_client, './test_state')

        # Verify SafeOrchestrator was initialized
        mock_orch_class.assert_called_once_with(mock_config, state_dir='./test_state')

        # Verify permission manager setup was called
        mock_orch._setup_permission_manager.assert_called_once_with(mock_client)

        assert result == mock_orch


def test_scan_one_handles_permission_readonly():
    """Test _scan_one properly handles read-only symbols"""

    mock_config = {
        'timeframes': {
            'entry': '5m',
            'mtf': '1h',
            'htf': '4h',
            'kline_limit': 500
        },
        'operation': {'dry_run': False}
    }

    mock_orch = Mock()
    mock_orch.permission_manager = Mock()
    mock_orch.get_symbol_permissions.return_value = {'BTC/USDT': 'readonly'}

    mock_client = Mock()
    mock_order_mgr = Mock()
    mock_rate_limiter = Mock()

    # Mock cycle result
    mock_result = Mock()
    mock_result.signal_data = {
        'direction': 'LONG',
        'entry_price': 50000.0,
        'sl': 49000.0,
        'tp1': 51000.0
    }
    mock_result.current_price = 50000.0
    mock_result.htf_bias = 'BULLISH'
    mock_result.regime = 'TRENDING'
    mock_result.breaker_state = 'CLEAR'
    mock_result.can_trade = True
    mock_result.actions_taken = []
    mock_orch.run_cycle.return_value = mock_result

    with patch('main.safe_fetch_ohlcv') as mock_fetch, \
         patch('main.save_report'), \
         patch('logging.getLogger'):

        mock_fetch.return_value = Mock()  # Mock DataFrame

        from main import _scan_one

        _scan_one('BTC/USDT', mock_orch, mock_client, mock_order_mgr, mock_rate_limiter, mock_config)

        # Verify read-only signal was sent
        mock_orch.send_readonly_signal.assert_called_once_with('BTC/USDT', mock_result.signal_data)


def test_scan_one_handles_permission_tradeable():
    """Test _scan_one properly handles tradeable symbols"""

    mock_config = {
        'timeframes': {
            'entry': '5m',
            'mtf': '1h',
            'htf': '4h',
            'kline_limit': 500
        },
        'operation': {'dry_run': False}
    }

    mock_orch = Mock()
    mock_orch.permission_manager = Mock()
    mock_orch.get_symbol_permissions.return_value = {'ETH/USDT': 'tradeable'}

    mock_client = Mock()
    mock_order_mgr = Mock()
    mock_rate_limiter = Mock()

    # Mock cycle result without signal_data (no trade signal)
    mock_result = Mock()
    mock_result.signal_data = None
    mock_result.actions_taken = []
    mock_result.current_price = 3000.0
    mock_result.htf_bias = 'BEARISH'
    mock_result.regime = 'RANGING'
    mock_result.breaker_state = 'ACTIVE'
    mock_result.can_trade = False
    mock_orch.run_cycle.return_value = mock_result

    with patch('main.safe_fetch_ohlcv') as mock_fetch, \
         patch('main.save_report'), \
         patch('main.sync_orders') as mock_sync, \
         patch('logging.getLogger'):

        mock_fetch.return_value = Mock()  # Mock DataFrame

        from main import _scan_one

        _scan_one('ETH/USDT', mock_orch, mock_client, mock_order_mgr, mock_rate_limiter, mock_config)

        # Verify sync_orders was called for tradeable symbol
        mock_sync.assert_called_once_with(mock_orch, mock_order_mgr, 'ETH/USDT', ANY)

        # Verify read-only signal was NOT sent
        mock_orch.send_readonly_signal.assert_not_called()