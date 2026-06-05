"""reverse_from_risk sizing must realize the configured max-loss (bug-hunt #6).

CustomRiskCalculator.calculate_position_size returns MARGIN (max_loss /
(stop_pct*leverage)). The orchestrator divided that margin figure by entry price as
if it were notional, so the opened position was leverage-x too small (5x
under-risked at leverage=5). The new calculate_contract_size() converts margin →
notional (× leverage) before dividing by entry, so the loss at the configured stop
equals max_loss.
"""
import pytest

from engine.risk.custom_calculator import CustomRiskCalculator


def test_contract_size_realizes_full_max_loss_not_a_leverage_fraction():
    calc = CustomRiskCalculator(max_loss_usdt=10.0, leverage=5, target_stop_pct=0.05)
    entry = 100.0
    size = calc.calculate_contract_size(available_balance=10_000.0, entry_price=entry)
    # notional = max_loss/(stop*lev) * lev = 40 * 5 = 200; size = 200/100 = 2.0
    assert size == pytest.approx(2.0)
    # Loss at the configured 5% stop must equal max_loss (NOT 2.0 = 1/leverage of it).
    loss_at_stop = size * entry * 0.05
    assert loss_at_stop == pytest.approx(10.0)


def test_contract_size_scales_with_leverage_at_fixed_risk():
    # Same max_loss + stop; higher leverage → larger notional/size (smaller margin),
    # but loss-at-stop stays pinned at max_loss.
    for lev in (1, 3, 5, 10):
        calc = CustomRiskCalculator(max_loss_usdt=20.0, leverage=lev, target_stop_pct=0.10)
        size = calc.calculate_contract_size(available_balance=10_000.0, entry_price=50.0)
        loss_at_stop = size * 50.0 * 0.10
        assert loss_at_stop == pytest.approx(20.0), f"leverage={lev}"


def test_contract_size_zero_or_negative_entry_is_safe():
    calc = CustomRiskCalculator(max_loss_usdt=10.0, leverage=5, target_stop_pct=0.05)
    assert calc.calculate_contract_size(10_000.0, 0.0) == 0.0
    assert calc.calculate_contract_size(10_000.0, -5.0) == 0.0
