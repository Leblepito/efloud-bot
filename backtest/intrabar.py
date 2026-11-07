"""Intrabar SL/TP fill resolution with explicit tie-break.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §6.3
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float


def resolve_fill(
    pos, bar: Bar, tie_break: str = "pessimistic",
) -> Tuple[Optional[str], Optional[float]]:
    """Return (level, fill_price) for the position, or (None, None) if no level hit.

    ``pos`` must expose: .direction ("LONG"|"SHORT"), .entry, .sl, .tp1

    Tie-break when both SL and TP are touched in the same bar (BT-17):
      "pessimistic" (DEFAULT) → SL wins. OHLC cannot tell us which came first.
      "open_heuristic"        → legacy: bar.open side of entry decides. OPTIMISTIC,
                                inflates win_rate when both levels fit inside one
                                bar's range. Kept only to reproduce old reports.
      "optimistic"            → TP always wins. Upper bound of the uncertainty band.

    Fill formula (pessimistic / realistic gap handling):
      SL fill: min(bar.open, sl)  for LONG   — gap-down worsens fill
               max(bar.open, sl)  for SHORT  — gap-up worsens fill
      TP fill: max(bar.open, tp1) for LONG   — open already past target → fill at open
               min(bar.open, tp1) for SHORT  — open already past target → fill at open
    """
    sl_hit = (
        (pos.direction == "LONG" and bar.low <= pos.sl) or
        (pos.direction == "SHORT" and bar.high >= pos.sl)
    )
    tp_hit = (
        (pos.direction == "LONG" and bar.high >= pos.tp1) or
        (pos.direction == "SHORT" and bar.low <= pos.tp1)
    )

    if not sl_hit and not tp_hit:
        return (None, None)

    if sl_hit and not tp_hit:
        return ("SL", _adverse_fill(bar.open, pos.sl, pos.direction, "SL"))

    if tp_hit and not sl_hit:
        return ("TP1", _adverse_fill(bar.open, pos.tp1, pos.direction, "TP"))

    # ---- Both hit in the SAME bar: order is UNKNOWABLE from OHLC ----
    # BT-17 (2026-07-25): the old rule was "LONG + bar.open >= entry -> TP won".
    # That is an OPTIMISTIC guess, and it is catastrophic exactly where it is
    # used most: when SL and TP are both narrower than one bar's range, EVERY
    # trade resolves on the first bar and roughly half the ambiguous ones are
    # handed to TP for free. Measured on 2026-07-25 (scalp config, smc v1 leg):
    # median SL 0.15% / TP1 0.297% -> 252 TP1 vs 29 SL, win_rate 84.3%,
    # PF 7.22, median hold ONE 5m bar, median MAE 0.0%. None of that is real;
    # it is this tie-break. The smc v2 leg (SL 2.33% / TP1 2.23%, far wider
    # than a 5m bar) was unaffected, so the comparison gate was scoring an
    # honest strategy against a fabricated baseline and REJECTing everything.
    #
    # Convention now: SL wins ties (pessimistic). Standard for OHLC backtests
    # and the only choice that cannot flatter a strategy. Pass
    # tie_break="open_heuristic" to reproduce the old behaviour; the spread
    # between the two IS the intrabar uncertainty of the result.
    if tie_break == "open_heuristic":
        if pos.direction == "LONG":
            if bar.open < pos.entry:
                return ("SL", _adverse_fill(bar.open, pos.sl, pos.direction, "SL"))
            return ("TP1", _adverse_fill(bar.open, pos.tp1, pos.direction, "TP"))
        if bar.open > pos.entry:
            return ("SL", _adverse_fill(bar.open, pos.sl, pos.direction, "SL"))
        return ("TP1", _adverse_fill(bar.open, pos.tp1, pos.direction, "TP"))

    if tie_break == "optimistic":
        return ("TP1", _adverse_fill(bar.open, pos.tp1, pos.direction, "TP"))

    return ("SL", _adverse_fill(bar.open, pos.sl, pos.direction, "SL"))


def _adverse_fill(bar_open: float, trigger: float, direction: str, kind: str) -> float:
    """Pessimistic/realistic fill price.

    SL: min(open, trigger) for LONG, max(open, trigger) for SHORT — gap-through worsens fill.
    TP: max(open, trigger) for LONG, min(open, trigger) for SHORT — fill at open if past target.
    """
    if kind == "SL":
        return min(bar_open, trigger) if direction == "LONG" else max(bar_open, trigger)
    # TP
    return max(bar_open, trigger) if direction == "LONG" else min(bar_open, trigger)
