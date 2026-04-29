import pytest
import tempfile
import yaml
import os
from pathlib import Path
from unittest.mock import Mock, patch

def create_temp_config(config_data: dict) -> str:
    """Helper to create temporary config file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        return f.name

def test_phase1_execution_requirements():
    """Test Phase 1 meets all safety requirements"""

    phase1_config = {
        'exchange': {'testnet': False, 'leverage': 3, 'margin_mode': 'isolated'},
        'risk': {
            'position_size_calculation': 'reverse_from_risk',
            'max_loss_per_trade_usdt': 20.0,
            'target_stop_distance_pct': 10.0
        },
        'operation': {'dry_run': True}  # MUST be dry run
    }

    config_path = create_temp_config(phase1_config)

    try:
        from main import load_config, validate_config

        config = load_config(config_path)

        # Phase 1 validations
        assert config['operation']['dry_run'] == True  # No real trades
        assert config['exchange']['testnet'] == False  # Real market data
        assert validate_config(config) == True

    finally:
        os.unlink(config_path)

def test_phase2_execution_requirements():
    """Test Phase 2 meets reduced risk requirements"""

    with patch.dict(os.environ, {'EFLOUD_ALLOW_MAINNET': '1'}):
        phase2_config = {
            'exchange': {'testnet': False, 'leverage': 3, 'margin_mode': 'isolated'},
            'risk': {
                'position_size_calculation': 'reverse_from_risk',
                'max_loss_per_trade_usdt': 10.0,  # REDUCED risk
                'target_stop_distance_pct': 10.0,
                'max_open_positions': 2  # LIMITED positions
            },
            'operation': {'dry_run': False},  # Live trading
            'safety': {
                'daily_loss_limit_pct': 1.5,
                'emergency_balance_threshold': 975
            }
        }

        config_path = create_temp_config(phase2_config)

        try:
            from main import load_config, validate_config

            config = load_config(config_path)

            # Phase 2 validations
            assert config['operation']['dry_run'] == False  # Live trading
            assert config['risk']['max_loss_per_trade_usdt'] == 10.0  # Reduced risk
            assert config['risk']['max_open_positions'] == 2  # Limited exposure
            assert validate_config(config) == True

        finally:
            os.unlink(config_path)

def test_phase3_execution_requirements():
    """Test Phase 3 meets full scale requirements"""

    with patch.dict(os.environ, {'EFLOUD_ALLOW_MAINNET': '1'}):
        phase3_config = {
            'exchange': {'testnet': False, 'leverage': 3, 'margin_mode': 'isolated'},
            'risk': {
                'position_size_calculation': 'reverse_from_risk',
                'max_loss_per_trade_usdt': 20.0,  # FULL risk
                'target_stop_distance_pct': 10.0,
                'max_open_positions': 4  # FULL positions
            },
            'operation': {'dry_run': False},
            'safety': {
                'daily_loss_limit_pct': 2.0,
                'emergency_balance_threshold': 950
            }
        }

        config_path = create_temp_config(phase3_config)

        try:
            from main import load_config, validate_config

            config = load_config(config_path)

            # Phase 3 validations
            assert config['operation']['dry_run'] == False  # Live trading
            assert config['risk']['max_loss_per_trade_usdt'] == 20.0  # Full risk
            assert config['risk']['max_open_positions'] == 4  # Full exposure
            assert validate_config(config) == True

        finally:
            os.unlink(config_path)

def test_phase_transition_prevents_skip():
    """Test system prevents skipping phases unsafely"""

    # Attempt to go directly to Phase 3 without environment variable
    with patch.dict(os.environ, {}, clear=True):  # No EFLOUD_ALLOW_MAINNET
        phase3_config = {
            'exchange': {'testnet': False},
            'operation': {'dry_run': False},  # Live trading without permission
            'risk': {'position_size_calculation': 'reverse_from_risk'}
        }

        from main import validate_config

        # Should raise ValueError for missing permission
        with pytest.raises(ValueError, match="EFLOUD_ALLOW_MAINNET"):
            validate_config(phase3_config)

def test_emergency_stop_integration():
    """Test emergency stop mechanisms work across all phases"""

    from engine.safety.guard import MainnetGuard

    # Test MainnetGuard properly validates different phase combinations

    # Phase 1: mainnet + dry_run should be allowed
    assert MainnetGuard.check(testnet=False, dry_run=True, interactive=False) == True

    # Phase 2/3: mainnet + live requires environment variable
    with patch.dict(os.environ, {'EFLOUD_ALLOW_MAINNET': '1'}):
        assert MainnetGuard.check(testnet=False, dry_run=False, interactive=False) == True

    # Should block without environment variable
    with patch.dict(os.environ, {}, clear=True):
        assert MainnetGuard.check(testnet=False, dry_run=False, interactive=False) == False