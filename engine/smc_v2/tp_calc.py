"""TP1 / TP2 target computation for SMC v2.

Spec §5.2:
  TP1 candidates (priority chain, with explicit source precedence on ties):
    1. Liquidity: EQH/EQL clusters + HTF swing extrema on the correct side
    2. FVG_NEAR: counter-direction HTF FVG near-edge on the correct side
    Pick the nearest candidate whose distance from entry >= min_rr * risk.
    If candidates exist but none qualify → InsufficientTPDistanceError.
    If no candidates at all → RR_PROJECTION (entry ± min_rr * risk).

  TP2:
    1. HTF FVG far-edge beyond TP1
    2. Fallback: fib_ext * risk projection, but only if it lies beyond TP1
    Else → None (single-target mode; lifecycle in PR #S5 handles TP1 = full close).

  Precedence on price ties (LIQUIDITY > FVG_NEAR) is explicit via a priority
  dict so a future refactor reordering list-comp blocks cannot silently flip it.
"""
from typing import Protocol, Tuple, Optional

from engine.smc import FVG, EqLevel
from engine.smc_v2.exceptions import InsufficientTPDistanceError


class RiskConfigLike(Protocol):
    min_rr: float
    fib_ext: float
    # BT-19 (2026-07-26, OPTIONAL — read via getattr, default 0.0 = OFF):
    #   max_tp_gap_r: ceiling on the TP1->TP2 distance in R multiples.
    # There has always been an implicit FLOOR (TP2 must lie beyond TP1) and no
    # CEILING, so TP2 lands wherever fib_ext puts it regardless of whether the
    # position can live long enough to get there. Measured on the 30d/10sym
    # scalp run (report 90143864): TP2 at 2.618R = 5.925% of price, median MFE
    # over the entire 4h max-hold window 0.478%. TP2 was attached to 28/28
    # trades and filled on 0 of them.


# Explicit source precedence — guards against float-equality misattribution.
# Lower number = higher priority on a tie.
# Unknown sources fall back to 99 (lowest priority) so future callers adding
# new source labels degrade gracefully instead of KeyError-crashing.
_SOURCE_PRIORITY = {"LIQUIDITY": 0, "FVG_NEAR": 1}
_UNKNOWN_PRIORITY = 99


def calc_tp_targets(
    direction: str,
    entry_price: float,
    sl_price: float,
    htf_swings: dict,            # {"swing_highs": [...], "swing_lows": [...]}
    htf_fvgs: list,              # List[FVG]
    eq_levels: list,             # List[EqLevel]
    config: RiskConfigLike,
) -> Tuple[float, Optional[float], dict]:
    """Compute TP1 + TP2 + source tags."""
    risk = abs(entry_price - sl_price)
    min_rr = config.min_rr
    min_dist = min_rr * risk
    # BT-19: optional TP2 reachability ceiling. 0.0 / missing attr = OFF, which
    # is byte-identical to pre-BT-19 behaviour for every existing caller.
    max_tp_gap_r = float(getattr(config, "max_tp_gap_r", 0.0) or 0.0)

    if direction == "LONG":
        # Liquidity ABOVE entry
        labeled = [(e.price, "LIQUIDITY") for e in eq_levels
                   if e.kind == "EQH" and e.price > entry_price]
        labeled += [(s.price, "LIQUIDITY") for s in htf_swings["swing_highs"]
                    if s.price > entry_price]
        labeled += [(f.bot, "FVG_NEAR") for f in htf_fvgs
                    if f.direction == "BEAR" and f.bot > entry_price]
        # Dedup by price with explicit precedence
        seen = {}
        for p, src in labeled:
            if (p not in seen
                    or _SOURCE_PRIORITY.get(src, _UNKNOWN_PRIORITY)
                       < _SOURCE_PRIORITY.get(seen[p], _UNKNOWN_PRIORITY)):
                seen[p] = src
        candidates = sorted(seen.items(), key=lambda x: x[0])  # ascending

        tp1_pair = next(((p, s) for p, s in candidates
                         if (p - entry_price) >= min_dist), None)
        if tp1_pair is None and candidates:
            raise InsufficientTPDistanceError(
                nearest=candidates[0][0], required=min_dist,
            )
        if tp1_pair is None:
            tp1, tp1_source = entry_price + min_dist, "RR_PROJECTION"
        else:
            tp1, tp1_source = tp1_pair

        # TP2: HTF FVG far edge beyond TP1, fallback fib_ext (strict > TP1)
        fvg_far = [f.top for f in htf_fvgs if f.direction == "BEAR" and f.top > tp1]
        if fvg_far:
            tp2, tp2_source = min(fvg_far), "FVG_FAR"
        else:
            fib_tp2 = entry_price + config.fib_ext * risk
            if fib_tp2 > tp1:
                tp2, tp2_source = fib_tp2, "FIB_EXT"
            else:
                tp2, tp2_source = None, "NONE"

    else:  # SHORT — mirror
        labeled = [(e.price, "LIQUIDITY") for e in eq_levels
                   if e.kind == "EQL" and e.price < entry_price]
        labeled += [(s.price, "LIQUIDITY") for s in htf_swings["swing_lows"]
                    if s.price < entry_price]
        labeled += [(f.top, "FVG_NEAR") for f in htf_fvgs
                    if f.direction == "BULL" and f.top < entry_price]
        seen = {}
        for p, src in labeled:
            if (p not in seen
                    or _SOURCE_PRIORITY.get(src, _UNKNOWN_PRIORITY)
                       < _SOURCE_PRIORITY.get(seen[p], _UNKNOWN_PRIORITY)):
                seen[p] = src
        candidates = sorted(seen.items(), key=lambda x: x[0], reverse=True)  # descending

        tp1_pair = next(((p, s) for p, s in candidates
                         if (entry_price - p) >= min_dist), None)
        if tp1_pair is None and candidates:
            raise InsufficientTPDistanceError(
                nearest=candidates[0][0], required=min_dist,
            )
        if tp1_pair is None:
            tp1, tp1_source = entry_price - min_dist, "RR_PROJECTION"
        else:
            tp1, tp1_source = tp1_pair

        fvg_far = [f.bot for f in htf_fvgs if f.direction == "BULL" and f.bot < tp1]
        if fvg_far:
            tp2, tp2_source = max(fvg_far), "FVG_FAR"
        else:
            fib_tp2 = entry_price - config.fib_ext * risk
            if fib_tp2 < tp1:
                tp2, tp2_source = fib_tp2, "FIB_EXT"
            else:
                tp2, tp2_source = None, "NONE"

    # ── BT-19: drop an unreachable TP2 ──
    # A TP2 further than max_tp_gap_r * risk beyond TP1 is not a target, it is
    # decoration: it never fills, it holds half the position hostage until the
    # max-hold force-close, and it inflates any blended-R:R gate that averages
    # TP1 and TP2. Dropping it returns tp2=None = single-target mode, which the
    # lifecycle already supports end-to-end (PR #S5 / #S5.5 / #S5.6): TP1 takes
    # full size, partial_close full-closes, orphan SL is cancelled.
    if max_tp_gap_r > 0 and tp2 is not None:
        if abs(tp2 - tp1) > max_tp_gap_r * risk:
            tp2, tp2_source = None, "DROPPED_UNREACHABLE"

    return tp1, tp2, {"tp1_source": tp1_source, "tp2_source": tp2_source}
