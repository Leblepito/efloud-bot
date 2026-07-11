"""Structural SL computation with ATR buffer + clamp.

Spec §5.1:
  structural_sl_SHORT = max(zone.high, htf_swing_anchor) + sl_atr_buffer * ATR
  structural_sl_LONG  = min(zone.low,  htf_swing_anchor) - sl_atr_buffer * ATR
  stop_dist = |entry - structural_sl|
  if stop_dist < min_sl_atr * ATR: widen to min_dist
  if stop_dist > max_sl_atr * ATR: raise SLTooFarError (reject setup)
"""
import math
from typing import Protocol

from engine.smc_v2.exceptions import SLTooFarError
from engine.smc_v2.zones import ZoneSpec


class SafetyConfigLike(Protocol):
    """Structural shape consumed by calc_sl. Matches engine.safety config attrs."""
    sl_atr_buffer: float
    min_sl_atr: float
    max_sl_atr: float


def calc_sl(
    direction: str,
    entry_price: float,
    zone: ZoneSpec,
    htf_swing_anchor: float,
    atr_15m: float,
    config: SafetyConfigLike,
) -> float:
    """Compute structural SL price with ATR buffer and clamp bounds.

    Args:
        direction: "LONG" or "SHORT".
        entry_price: confirmed entry price (from confirmation.py).
        zone: the pullback zone the entry happened inside.
        htf_swing_anchor: HTF swing price on the "wrong side" of the trade
            (i.e. above for SHORT, below for LONG). Selected by
            select_htf_swing_anchor in PR #S3.
        atr_15m: current 15m ATR(14) — drives both buffer and clamp.
        config: must have sl_atr_buffer, min_sl_atr, max_sl_atr (floats).

    Returns:
        SL price (float).

    Raises:
        SLTooFarError: when structural stop distance exceeds max_sl_atr * ATR.
    """
    # F13 (2026-07-11 spec): NaN/0 ATR (warmup/kısa df) NaN SL üretip emir
    # yoluna sızıyordu — fail-closed: setup reddi (çağıran SLTooFarError'ı
    # zaten "reject setup" olarak ele alıyor; yeni exception tipi yok).
    if atr_15m is None or not math.isfinite(atr_15m) or atr_15m <= 0:
        raise SLTooFarError(stop_dist=float("inf"), max_dist=0.0)

    buffer = config.sl_atr_buffer * atr_15m
    if direction == "LONG":
        structural_sl = min(zone.low, htf_swing_anchor) - buffer
    else:  # SHORT
        structural_sl = max(zone.high, htf_swing_anchor) + buffer

    stop_dist = abs(entry_price - structural_sl)
    min_dist = config.min_sl_atr * atr_15m
    max_dist = config.max_sl_atr * atr_15m

    if stop_dist > max_dist:
        raise SLTooFarError(stop_dist=stop_dist, max_dist=max_dist)
    if stop_dist < min_dist:
        # Widen to ATR floor — same direction as structural
        return (entry_price - min_dist) if direction == "LONG" else (entry_price + min_dist)
    return structural_sl
