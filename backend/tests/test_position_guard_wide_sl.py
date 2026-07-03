"""H3 (algorithm audit 2026-06-20): v1 SL-width hard cap.

v1 (live) historically only WARNED when sl_atr_mult > max_sl_atr while v2
hard-rejects (SLTooFarError). The `reject_wide_sl` toggle (default OFF per
dev-contract: new behavior fail-closed/default-OFF) makes v1 match v2 when
enabled. These tests pin both sides of the toggle.
"""
from __future__ import annotations

from engine.safety.position_guard import PositionGuard


def _open(guard: PositionGuard, sl: float):
    """Small LONG @100 with the given SL; leverage=1 keeps the
    liquidation-distance check (5b) out of the way."""
    return guard.can_open_position(
        balance=10_000.0, entry=100.0, size=1.0, sl=sl,
        atr=1.0, direction="LONG", symbol="BTC/USDT",
        existing_positions=[], leverage=1,
    )


def test_wide_sl_warn_only_by_default():
    """Default (reject_wide_sl=False): 10-ATR SL passes with a warning —
    preserves historical v1 behavior."""
    guard = PositionGuard(max_sl_distance_atr=5.0)
    res = _open(guard, sl=90.0)  # 10 ATR
    assert res.allowed is True
    assert any("SL very wide" in w for w in res.warnings)


def test_wide_sl_hard_reject_when_flag_on():
    """reject_wide_sl=True: 10-ATR SL is a hard REJECT (matches v2 SLTooFar)."""
    guard = PositionGuard(max_sl_distance_atr=5.0, reject_wide_sl=True)
    res = _open(guard, sl=90.0)  # 10 ATR
    assert res.allowed is False
    assert "SL too wide" in res.reason


def test_normal_sl_unaffected_by_flag():
    """A within-cap SL (2 ATR) passes regardless of the toggle."""
    for flag in (False, True):
        guard = PositionGuard(max_sl_distance_atr=5.0, reject_wide_sl=flag)
        res = _open(guard, sl=98.0)  # 2 ATR
        assert res.allowed is True, f"flag={flag}: {res.reason}"


def test_too_tight_sl_still_rejected():
    """min_sl_distance_atr rejection is independent of reject_wide_sl."""
    guard = PositionGuard(min_sl_distance_atr=0.5, reject_wide_sl=True)
    res = _open(guard, sl=99.9)  # 0.1 ATR
    assert res.allowed is False
    assert "SL too tight" in res.reason
