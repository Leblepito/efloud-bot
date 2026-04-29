import pytest
import yaml
from pathlib import Path
import tempfile
import os

def test_config_validates_new_risk_settings():
    """Test configuration validation for new risk management settings"""

    valid_config = {
        'risk': {
            'position_size_calculation': 'reverse_from_risk',
            'max_loss_per_trade_usdt': 20.0,
            'target_stop_distance_pct': 10.0,
            'max_open_positions': 4,
            'min_rr': 2.0
        },
        'exchange': {
            'leverage': 3,
            'margin_mode': 'isolated'
        }
    }

    # This should not raise any errors
    from main import validate_config
    assert validate_config(valid_config) == True

def test_config_rejects_invalid_risk_settings():
    """Test configuration rejects invalid risk parameters"""

    invalid_configs = [
        {
            'risk': {
                'max_loss_per_trade_usdt': -10.0,  # Negative loss
                'position_size_calculation': 'reverse_from_risk'
            }
        },
        {
            'risk': {
                'target_stop_distance_pct': 150.0,  # >100% stop
                'position_size_calculation': 'reverse_from_risk'
            }
        },
        {
            'exchange': {
                'leverage': 0  # Invalid leverage
            }
        }
    ]

    from main import validate_config

    for invalid_config in invalid_configs:
        with pytest.raises(ValueError):
            validate_config(invalid_config)

def test_phase_config_loading():
    """Test loading of phase-specific configurations"""

    # Create temporary phase config
    phase_config = {
        'exchange': {
            'testnet': False,
            'leverage': 3,
            'margin_mode': 'isolated'
        },
        'risk': {
            'position_size_calculation': 'reverse_from_risk',
            'max_loss_per_trade_usdt': 10.0,
            'target_stop_distance_pct': 10.0
        },
        'operation': {
            'dry_run': False
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(phase_config, f)
        temp_path = f.name

    try:
        from main import load_config
        loaded_config = load_config(temp_path)

        assert loaded_config['risk']['position_size_calculation'] == 'reverse_from_risk'
        assert loaded_config['exchange']['margin_mode'] == 'isolated'
        assert loaded_config['operation']['dry_run'] == False

    finally:
        os.unlink(temp_path)

def test_backwards_compatibility_with_legacy_config():
    """Test system works with legacy configuration format"""

    legacy_config = {
        'risk': {
            'risk_per_trade_pct': 0.75,  # Legacy percentage-based
            'max_open_positions': 7,
            'min_rr': 2.0
        },
        'exchange': {
            'leverage': 3
            # No margin_mode specified (legacy)
        }
    }

    from main import validate_config

    # Should not raise errors and use legacy mode
    assert validate_config(legacy_config) == True