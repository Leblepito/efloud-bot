# tests/config/test_phase_configs.py
import pytest
import yaml
from pathlib import Path

def load_phase_config(phase: int) -> dict:
    """Helper to load phase configuration with proper path resolution and error handling"""
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / f"configs/config.phase{phase}.yaml"

    if not config_path.exists():
        pytest.skip(f"Config file not found: {config_path}")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Validate that essential sections exist
        if not isinstance(config, dict):
            pytest.fail(f"Invalid config format in {config_path}: expected dict, got {type(config)}")

        required_sections = ['operation', 'risk', 'safety', 'exchange']
        missing_sections = [section for section in required_sections if section not in config]
        if missing_sections:
            pytest.fail(f"Missing required sections in {config_path}: {missing_sections}")

        return config

    except yaml.YAMLError as e:
        pytest.fail(f"YAML parsing error in {config_path}: {e}")
    except Exception as e:
        pytest.fail(f"Error loading config {config_path}: {e}")

def test_phase1_is_dry_run_only():
    """Phase 1 must be dry run for safety"""
    config = load_phase_config(1)

    assert config['operation']['dry_run'] is True
    assert config['exchange']['testnet'] is False  # Mainnet data
    assert config['risk']['max_loss_per_trade_usdt'] == 20

def test_phase2_is_live_with_reduced_risk():
    """Phase 2 should be live trading with reduced risk"""
    config = load_phase_config(2)

    assert config['operation']['dry_run'] is False  # Live trading
    assert config['risk']['max_loss_per_trade_usdt'] == 10  # Reduced risk
    assert config['risk']['max_open_positions'] == 2  # Limited positions

def test_phase3_is_full_scale_live():
    """Phase 3 should be full scale live trading"""
    config = load_phase_config(3)

    assert config['operation']['dry_run'] is False  # Live trading
    assert config['risk']['max_loss_per_trade_usdt'] == 20  # Full risk
    assert config['risk']['max_open_positions'] == 4  # Full positions

def test_all_phases_use_correct_risk_calculation():
    """All phases should use reverse_from_risk calculation method"""
    for phase in [1, 2, 3]:
        config = load_phase_config(phase)
        assert config['risk']['position_size_calculation'] == 'reverse_from_risk'
        assert config['risk']['target_stop_distance_pct'] == 10
        assert config['exchange']['margin_mode'] == 'isolated'

def test_safety_progression_across_phases():
    """Safety settings should get progressively less restrictive"""
    phase1 = load_phase_config(1)
    phase2 = load_phase_config(2)
    phase3 = load_phase_config(3)

    # Daily loss limits should progress appropriately
    assert phase1['safety']['daily_loss_limit_pct'] == 2.0
    assert phase2['safety']['daily_loss_limit_pct'] == 1.5  # More conservative for live
    assert phase3['safety']['daily_loss_limit_pct'] == 2.0  # Back to normal

    # Emergency thresholds
    assert phase2['safety']['emergency_balance_threshold'] == 975  # Tighter
    assert phase3['safety']['emergency_balance_threshold'] == 950  # Normal