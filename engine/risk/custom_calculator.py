"""
Custom Risk Calculator for Efloud Mainnet Trading
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Reverse-calculates position size from maximum acceptable loss.
Ensures proper risk management for live trading with real money.
"""
import logging
from typing import Dict

log = logging.getLogger("efloud.risk")


class CustomRiskCalculator:
    """
    Calculates position sizes based on maximum acceptable loss tolerance.

    Formula: position_size = max_loss / (stop_distance * leverage)
    This ensures the maximum loss never exceeds the configured tolerance.
    """

    def __init__(self, max_loss_usdt: float = 20.0, leverage: int = 3, target_stop_pct: float = 0.10):
        """
        Initialize risk calculator with safety parameters.

        Args:
            max_loss_usdt: Maximum acceptable loss per trade in USDT
            leverage: Trading leverage multiplier
            target_stop_pct: Target stop loss distance as percentage (0.10 = 10%)
        """
        # Critical input validation
        if max_loss_usdt <= 0:
            raise ValueError("max_loss_usdt must be positive")
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        if target_stop_pct <= 0 or target_stop_pct >= 1:
            raise ValueError("target_stop_pct must be between 0 and 1")

        self.max_loss_usdt = max_loss_usdt
        self.leverage = leverage
        self.target_stop_pct = target_stop_pct

        log.info(f"Risk Calculator initialized: {max_loss_usdt} USDT max loss, {leverage}x leverage, {target_stop_pct*100}% target stop")

    def calculate_position_size(self, available_balance: float) -> float:
        """
        Calculate position size from maximum acceptable loss.

        Args:
            available_balance: Current available balance in USDT

        Returns:
            Position size in USDT
        """
        # Reverse calculation: position_size = max_loss / (stop_distance * leverage)
        calculated_size = self.max_loss_usdt / (self.target_stop_pct * self.leverage)

        # Safety cap: never use more than 80% of available balance
        max_allowed = available_balance * 0.80

        position_size = min(calculated_size, max_allowed)

        log.debug(f"Position size calculated: {position_size:.2f} USDT (from {available_balance:.2f} available)")

        return position_size

    def calculate_notional_exposure(self, position_size: float) -> float:
        """
        Calculate total notional exposure with leverage.

        Args:
            position_size: Position size in USDT

        Returns:
            Notional exposure in USDT
        """
        return position_size * self.leverage

    def validate_risk_parameters(self, position_size: float, current_price: float, stop_price: float) -> Dict:
        """
        Validate that trade parameters meet risk requirements.

        Args:
            position_size: Intended position size in USDT
            current_price: Current asset price
            stop_price: Intended stop loss price

        Returns:
            Dict with validation results and metrics
        """
        # Division by zero protection
        if current_price <= 0:
            log.error(f"Invalid current_price: {current_price}")
            return {'valid': False, 'error': 'Invalid current price'}

        actual_stop_distance = abs(current_price - stop_price) / current_price

        # Sanity check: stop distance should be reasonable
        if actual_stop_distance > 0.5:  # More than 50% stop is unrealistic
            log.warning(f"Unrealistic stop distance: {actual_stop_distance*100:.1f}%")

        notional = self.calculate_notional_exposure(position_size)
        potential_loss = notional * actual_stop_distance

        is_valid = potential_loss <= self.max_loss_usdt

        result = {
            'valid': is_valid,
            'potential_loss_usdt': potential_loss,
            'stop_distance_pct': actual_stop_distance * 100,
            'max_allowed_loss': self.max_loss_usdt,
            'notional_exposure': notional
        }

        if not is_valid:
            log.warning(f"Risk validation FAILED: {potential_loss:.2f} USDT loss exceeds {self.max_loss_usdt} limit")

        return result