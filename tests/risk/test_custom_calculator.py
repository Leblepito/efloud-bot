# tests/risk/test_custom_calculator.py
import pytest
from engine.risk.custom_calculator import CustomRiskCalculator

def test_calculate_position_size_with_default_params():
    """Test position size calculation from max loss tolerance"""
    calculator = CustomRiskCalculator(max_loss_usdt=20.0, leverage=3, target_stop_pct=0.10)
    available_balance = 1000.0

    position_size = calculator.calculate_position_size(available_balance)

    # Expected: 20 / (0.10 * 3) = 66.67 USDT
    assert abs(position_size - 66.67) < 0.01

def test_position_size_respects_balance_limit():
    """Test position size never exceeds 80% of available balance"""
    calculator = CustomRiskCalculator(max_loss_usdt=1000.0, leverage=3, target_stop_pct=0.10)  # Unrealistically high
    available_balance = 100.0

    position_size = calculator.calculate_position_size(available_balance)

    # Should be capped at 80% of balance
    assert position_size <= 80.0

def test_calculate_notional_exposure():
    """Test notional exposure calculation with leverage"""
    calculator = CustomRiskCalculator()
    position_size = 66.67

    notional = calculator.calculate_notional_exposure(position_size)

    assert abs(notional - 200.01) < 0.1  # 66.67 * 3 = 200.01

def test_validate_risk_parameters_within_limits():
    """Test risk validation when trade is within limits"""
    calculator = CustomRiskCalculator(max_loss_usdt=20.0)

    result = calculator.validate_risk_parameters(
        position_size=66.66,  # Use 66.66 to stay under 20.0 limit (66.66 * 3 * 0.10 = 19.998)
        current_price=100.0,
        stop_price=90.0  # 10% stop distance
    )

    assert result['valid'] == True
    assert abs(result['potential_loss_usdt'] - 20.0) < 0.1
    assert abs(result['stop_distance_pct'] - 10.0) < 0.1

def test_validate_risk_parameters_exceeds_limits():
    """Test risk validation when trade exceeds limits"""
    calculator = CustomRiskCalculator(max_loss_usdt=20.0)

    result = calculator.validate_risk_parameters(
        position_size=100.0,  # Too large
        current_price=100.0,
        stop_price=85.0  # 15% stop distance
    )

    assert result['valid'] == False
    assert result['potential_loss_usdt'] > 20.0

def test_risk_calculator_input_validation():
    """Test input validation in constructor"""
    with pytest.raises(ValueError, match="max_loss_usdt must be positive"):
        CustomRiskCalculator(max_loss_usdt=-10.0)

    with pytest.raises(ValueError, match="leverage must be positive"):
        CustomRiskCalculator(leverage=0)

    with pytest.raises(ValueError, match="target_stop_pct must be between 0 and 1"):
        CustomRiskCalculator(target_stop_pct=1.5)

def test_validate_risk_handles_invalid_price():
    """Test validation handles invalid current price"""
    calculator = CustomRiskCalculator()

    result = calculator.validate_risk_parameters(
        position_size=66.67,
        current_price=0.0,  # Invalid price
        stop_price=90.0
    )

    assert result['valid'] == False
    assert 'error' in result