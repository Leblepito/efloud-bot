"""Regression: a floor-widened v2 SL must pass PositionGuard's strict ATR check.

Bug (2026-11-05): calc_sl widens a too-tight structural stop to EXACTLY
``entry -/+ min_sl_atr * atr``. PositionGuard.can_open_position then
recomputes ``abs(entry - sl) / atr`` and rejects when the result is
``< min_sl_atr``. Floating-point round-trip error makes that recomputed
multiple 1.9999999999... for about half of all price/ATR magnitudes, so
roughly half of the floor-widened setups were rejected with "SL too tight"
even though calc_sl had just placed them ON the floor.

The fix lives in calc_sl (widen a hair past the floor). PositionGuard's
``sl_atr_mult < self.min_sl_atr`` check is untouched and stays strict; this
test constructs a real PositionGuard with the live phase2_1k values
(min_sl_atr=2.0, max_sl_atr=5.0, reject_wide_sl=True).
"""
import random
from dataclasses import dataclass

import pytest

from engine.safety.position_guard import PositionGuard
from engine.smc_v2.sl_calc import calc_sl
from engine.smc_v2.zones import ZoneSpec


@dataclass
class LiveSafetyConfig:
    # configs/config.phase2_1k.yaml: risk.sl_atr_buffer, safety.min/max_sl_atr
    sl_atr_buffer: float = 0.5
    min_sl_atr: float = 2.0
    max_sl_atr: float = 5.0


def _live_guard() -> PositionGuard:
    return PositionGuard(
        min_sl_distance_atr=2.0,
        max_sl_distance_atr=5.0,
        reject_wide_sl=True,
    )


def _narrow_zone_sl(direction: str, entry: float, atr: float) -> float:
    """Structural stop = 0.1 ATR zone edge + 0.5 ATR buffer = 0.6 ATR < 2.0 floor."""
    if direction == "LONG":
        zone = ZoneSpec(low=entry - 0.1 * atr, high=entry, source="HTF_FVG")
        anchor = zone.low
    else:
        zone = ZoneSpec(low=entry, high=entry + 0.1 * atr, source="HTF_FVG")
        anchor = zone.high
    return calc_sl(
        direction=direction,
        entry_price=entry,
        zone=zone,
        htf_swing_anchor=anchor,
        atr_15m=atr,
        config=LiveSafetyConfig(),
    )


def _guard_verdict(guard: PositionGuard, direction: str, entry: float, sl: float, atr: float):
    # Notional $10 on a $10k balance: size cap / exposure / risk-% never bind,
    # so the only check that can reject is the SL-ATR distance under test.
    return guard.can_open_position(
        balance=10_000.0,
        entry=entry,
        size=10.0 / entry,
        sl=sl,
        atr=atr,
        direction=direction,
        symbol="TEST/USDT",
        existing_positions=[],
        leverage=1,
    )


def _cases():
    """Deterministic magnitude grid + seeded random sweep (spec: 0.05-120000, ATR 0.1-1%)."""
    entries = [0.05, 0.0731, 0.1234, 0.5, 1.0, 3.7, 17.3, 99.99, 250.0,
               1234.5, 3_456.78, 30_000.0, 64_321.09, 95_000.0, 120_000.0]
    atr_pcts = [0.001, 0.0017, 0.0025, 0.005, 0.0073, 0.01]
    cases = [(d, e, e * p) for d in ("LONG", "SHORT") for e in entries for p in atr_pcts]
    rng = random.Random(20261105)
    for _ in range(20_000):
        e = rng.uniform(0.05, 120_000.0)
        cases.append((rng.choice(("LONG", "SHORT")), e, e * rng.uniform(0.001, 0.01)))
    return cases


def test_floor_widened_sl_is_accepted_by_position_guard():
    guard = _live_guard()
    rejected = []
    cases = _cases()
    for direction, entry, atr in cases:
        sl = _narrow_zone_sl(direction, entry, atr)
        verdict = _guard_verdict(guard, direction, entry, sl, atr)
        if not verdict.allowed:
            rejected.append((direction, entry, atr, abs(entry - sl) / atr, verdict.reason))
    assert not rejected, (
        f"{len(rejected)}/{len(cases)} floor-widened SLs rejected by PositionGuard; "
        f"first: {rejected[0]}"
    )


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_floor_widened_sl_stays_on_the_floor(direction):
    """The fix must only nudge past the floor, not move the stop materially."""
    for _, entry, atr in _cases()[:2_000]:
        sl = _narrow_zone_sl(direction, entry, atr)
        mult = abs(entry - sl) / atr
        assert mult == pytest.approx(2.0, rel=1e-6), (entry, atr, mult)
        # Correct side of entry
        assert (sl < entry) if direction == "LONG" else (sl > entry)
