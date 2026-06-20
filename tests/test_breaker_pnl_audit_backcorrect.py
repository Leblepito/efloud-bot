"""M4: PnL-audit back-correction of the breaker consecutive-loss counter (default-OFF).

A sign-flipped local estimate (a near-break-even trade fed as a WIN that was
actually a net LOSS after fees/funding) RESETS the consecutive-loss counter,
weakening the consecutive_loss_limit guard. The exchange-truth audit sweep
corrects pnl_usdt; record_trade_correction re-feeds the corrected sign so the
counter — and an earlier breaker trip — is restored. Fail-CLOSED: it can only
add a loss (earlier trip), never remove a real one below zero.
"""
from unittest.mock import MagicMock

import pandas as pd
import pytest
import yaml

from engine import SafeOrchestrator
from engine.safety.breaker import CircuitBreaker


def _breaker():
    return CircuitBreaker(consecutive_loss_limit=3, starting_balance=2000.0)


def test_audit_sign_flip_re_increments_consecutive_losses():
    b = _breaker()
    b.record_trade(-5.0)
    b.record_trade(-5.0)
    assert b.consecutive_losses == 2
    # third trade fed as a WIN (sign-flipped fee-naive estimate) → counter resets
    b.record_trade(+1.0)
    assert b.consecutive_losses == 0
    bal_before = b.current_balance
    # audit corrects that trade to exchange-truth net loss
    b.record_trade_correction(old_pnl=+1.0, new_pnl=-0.40)
    assert b.consecutive_losses == 3, "win→loss correction must re-count the loss"
    assert b.current_balance == pytest.approx(bal_before + (-0.40 - 1.0))


def test_loss_to_win_correction_decrements_clamped_at_zero():
    b = _breaker()
    b.record_trade(-5.0)
    assert b.consecutive_losses == 1
    b.record_trade_correction(old_pnl=-5.0, new_pnl=+2.0)
    assert b.consecutive_losses == 0
    # never below zero, never fabricates a trip
    b.record_trade_correction(old_pnl=-1.0, new_pnl=+1.0)
    assert b.consecutive_losses == 0


def test_same_sign_correction_adjusts_balance_only():
    b = _breaker()
    b.record_trade(-5.0)
    assert b.consecutive_losses == 1
    bal = b.current_balance
    b.record_trade_correction(old_pnl=-5.0, new_pnl=-6.5)  # still a loss, bigger
    assert b.consecutive_losses == 1, "same-sign correction must not touch the counter"
    assert b.current_balance == pytest.approx(bal + (-6.5 - -5.0))


def _flat_df():
    idx = pd.date_range("2026-01-01", periods=300, freq="15min")
    return pd.DataFrame(
        {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1.0}, index=idx
    )


def _run_cycle_with_correction(tmp_path, monkeypatch, flag):
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["operation"]["dry_run"] = True
    cfg["safety"]["breaker_backcorrect_consecutive"] = flag
    orch = SafeOrchestrator(cfg, state_dir=str(tmp_path / str(flag)),
                            freshness_check=False, persist=False)
    om = MagicMock()
    om._last_pnl_corrections = [("X1", 1.0, -0.40)]  # a win→loss sign flip
    orch.order_manager = om
    calls = []
    monkeypatch.setattr(orch.breaker, "record_trade_correction",
                        lambda o, n: calls.append((o, n)))
    df = _flat_df()
    orch.run_cycle("BTC/USDT", df, df, df, df, balance=2000.0)
    return calls, om._last_pnl_corrections


def test_orchestrator_drain_off_by_default(tmp_path, monkeypatch):
    """Flag OFF (default): STEP5 drains the corrections list (no leak) but does
    NOT touch the breaker — byte-identical breaker behavior."""
    calls, drained = _run_cycle_with_correction(tmp_path, monkeypatch, flag=False)
    assert calls == []
    assert drained == []


def test_orchestrator_drain_applies_when_enabled(tmp_path, monkeypatch):
    """Flag ON: the sign-flipped correction is re-fed to the breaker, and the
    list is drained."""
    calls, drained = _run_cycle_with_correction(tmp_path, monkeypatch, flag=True)
    assert calls == [(1.0, -0.40)]
    assert drained == []
