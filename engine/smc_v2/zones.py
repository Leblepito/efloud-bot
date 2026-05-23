"""Pullback zone builder for SMC v2.

Selects the price band where a pullback entry is expected after a CHoCH
trigger. Priority order per spec §4.1:

  1. Nearest unmitigated counter-direction HTF FVG on the pullback side
     (BULL FVGs above price for SHORT; BEAR FVGs below price for LONG).
  2. Fallback: OTE band (caller passes the band).

All functions are pure — no I/O, no logging.
"""
from dataclasses import dataclass
from typing import List, Literal, Tuple

from engine.smc import FVG


@dataclass
class ZoneSpec:
    """A pullback target region."""
    low: float
    high: float
    source: Literal["HTF_FVG", "OTE"]


def build_pullback_zones(
    htf_fvgs: List[FVG],
    ote_band: Tuple[float, float],
    direction: str,
    trigger_price: float,
) -> ZoneSpec:
    """Pick the pullback target zone for a fresh setup.

    Args:
        htf_fvgs: list of FVGs from the HTF (4h/1h) — typically unmitigated only,
            but this function does not filter; pass pre-filtered list.
        ote_band: (low, high) tuple of the OTE 0.618-0.786 band; used as fallback.
        direction: "LONG" or "SHORT" — the direction of the trade being prepared.
        trigger_price: the CHoCH break price; reference for "which side is pullback".

    Returns:
        ZoneSpec with source="HTF_FVG" if a counter-direction FVG exists on the
        pullback side, else source="OTE" using the supplied band.
    """
    if direction == "SHORT":
        # SHORT pullback = price retraces UP into a BULL gap above trigger
        candidates = [
            f for f in htf_fvgs
            if f.direction == "BULL" and f.bot > trigger_price
        ]
        if candidates:
            # Nearest = smallest distance from trigger to FVG bot
            nearest = min(candidates, key=lambda f: f.bot - trigger_price)
            return ZoneSpec(low=nearest.bot, high=nearest.top, source="HTF_FVG")
    else:  # LONG
        # LONG pullback = price retraces DOWN into a BEAR gap below trigger
        candidates = [
            f for f in htf_fvgs
            if f.direction == "BEAR" and f.top < trigger_price
        ]
        if candidates:
            # Nearest = smallest distance from FVG top to trigger
            nearest = max(candidates, key=lambda f: f.top)
            return ZoneSpec(low=nearest.bot, high=nearest.top, source="HTF_FVG")
    # Fallback
    return ZoneSpec(low=ote_band[0], high=ote_band[1], source="OTE")


def is_price_in_zone(price: float, zone: ZoneSpec) -> bool:
    """Inclusive membership check."""
    return zone.low <= price <= zone.high
