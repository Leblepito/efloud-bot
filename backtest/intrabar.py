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


def resolve_fill(pos, bar: Bar) -> Tuple[Optional[str], Optional[float]]:
    """Return (level, fill_price) for the position, or (None, None) if no level hit.

    ``pos`` must expose: .direction ("LONG"|"SHORT"), .entry, .sl, .tp1

    Tie-break when both SL and TP are touched in the same bar:
      LONG:  bar.open < entry → SL fired first; bar.open >= entry → TP fired first.
      SHORT: bar.open > entry → SL fired first; bar.open <= entry → TP fired first.

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

    # Both hit — tie-break by bar.open proximity to entry
    if pos.direction == "LONG":
        if bar.open < pos.entry:
            return ("SL", _adverse_fill(bar.open, pos.sl, pos.direction, "SL"))
        return ("TP1", _adverse_fill(bar.open, pos.tp1, pos.direction, "TP"))
    else:  # SHORT
        if bar.open > pos.entry:
            return ("SL", _adverse_fill(bar.open, pos.sl, pos.direction, "SL"))
        return ("TP1", _adverse_fill(bar.open, pos.tp1, pos.direction, "TP"))


def _adverse_fill(bar_open: float, trigger: float, direction: str, kind: str) -> float:
    """Pessimistic/realistic fill price.

    SL: min(open, trigger) for LONG, max(open, trigger) for SHORT — gap-through worsens fill.
    TP: max(open, trigger) for LONG, min(open, trigger) for SHORT — fill at open if past target.
    """
    if kind == "SL":
        return min(bar_open, trigger) if direction == "LONG" else max(bar_open, trigger)
    # TP
    return max(bar_open, trigger) if direction == "LONG" else min(bar_open, trigger)
