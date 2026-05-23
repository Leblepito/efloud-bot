"""Trigger phase for SMC v2: CHoCH detection → SetupCandidate emission.

Per spec §4.3 step 3:
  For each new CHoCH on LTF (15m) aligned with HTF (4h) bias:
    1. select_htf_swing_anchor → structural SL reference
    2. build_pullback_zones → target zone (HTF FVG priority, OTE fallback)
    3. Emit SetupCandidate(state=AWAITING_PULLBACK, bars_waited=0)

Pure function. Returns list of new candidates. Caller (orchestrator) appends
to SetupStateStore — store.add() enforces per-symbol cap.

Scope limited to CHoCH events (BOS deferred — matches v1 signals.py
recency-tighter BOS handling, see signals.py:200-204).
"""
from typing import List, Tuple

from engine.smc import StructBreak, Swing, FVG
from engine.smc_v2.setup_state import SetupCandidate
from engine.smc_v2.swing_anchor import select_htf_swing_anchor
from engine.smc_v2.zones import build_pullback_zones


def generate_setup_candidates(
    symbol: str,
    htf_bias: str,
    ltf_structure_breaks: List[StructBreak],
    htf_swings: dict,
    htf_bars: list,
    htf_fvgs: List[FVG],
    ote_band: Tuple[float, float],
    ltf_trigger_idx_min: int,
) -> List[SetupCandidate]:
    """Emit SetupCandidate instances for new aligned CHoCH events.

    Args:
        symbol: trading pair
        htf_bias: "BULL" | "BEAR" | "UNDEF" — HTF directional bias
        ltf_structure_breaks: LTF (15m) structure breaks (CHoCH/BOS) from
            SMCEngine.structure() on df_15m
        htf_swings: {"swing_highs": [...], "swing_lows": [...]} for SL anchor
        htf_bars: HTF OHLC bars with .ordinal/.high/.low (for swing_anchor
            unbroken check). Caller enumerates df_htf to produce these.
        htf_fvgs: unmitigated HTF FVGs for build_pullback_zones priority
        ote_band: (low, high) of HTF OTE 0.618-0.786 fib region (fallback zone)
        ltf_trigger_idx_min: int — only consider breaks with idx >= this
            (recency filter; mirrors v1 signals.py:198 recency_cutoff)

    Returns:
        List of new SetupCandidate instances (state=AWAITING_PULLBACK,
        bars_waited=0). Caller must add each to SetupStateStore.add()
        which applies per-symbol cap.
    """
    if htf_bias == "UNDEF":
        return []

    out: List[SetupCandidate] = []
    for brk in ltf_structure_breaks:
        # PR #S3c-1 emits only for CHoCH (reversal). BOS (continuation)
        # deferred — v1 signals.py handles BOS with a tighter recency
        # window (signals.py:200-204).
        if brk.kind != "CHoCH":
            continue

        # Aligned with HTF bias only
        if brk.direction != htf_bias:
            continue

        # Recency filter
        if brk.idx < ltf_trigger_idx_min:
            continue

        # Map BULL → LONG, BEAR → SHORT
        direction = "LONG" if brk.direction == "BULL" else "SHORT"

        # Select structural SL anchor (most-recent-unbroken HTF swing)
        anchor = select_htf_swing_anchor(
            htf_swings=htf_swings,
            direction=direction,
            trigger_idx=brk.idx,
            htf_bars=htf_bars,
        )
        if anchor is None:
            # No valid HTF anchor → can't compute structural SL → skip
            continue

        # Build pullback zone (HTF FVG priority, OTE fallback)
        zone = build_pullback_zones(
            htf_fvgs=htf_fvgs,
            ote_band=ote_band,
            direction=direction,
            trigger_price=brk.price,
        )

        out.append(SetupCandidate(
            symbol=symbol,
            direction=direction,
            trigger_bar_ts=brk.idx,  # ordinal axis (matches swing_anchor)
            trigger_price=brk.price,
            htf_bias=htf_bias,
            target_zone=zone,
            htf_swing_anchor=anchor,
            bars_waited=0,
            state="AWAITING_PULLBACK",
            confluence_score=0,  # PR #S3c-2 may add confluence scoring
            reasons=[f"CHoCH {brk.direction} aligned with HTF {htf_bias}"],
        ))

    return out
