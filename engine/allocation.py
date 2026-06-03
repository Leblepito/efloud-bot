"""S5 — expected-value slot allocation primitive.

When the open-position slots are full, the orchestrator fills them
first-come-first-served (symbol-loop order), so a weak signal can occupy a slot
a stronger one then can't take. These helpers rank candidate signals by an EV
proxy (confluence × R:R) and pick the best for the available slots.

Pure functions; accept Signal objects or plain dicts. Wiring this into the live
cycle (buffer all candidates across the symbol loop, then allocate) is a
separate, backtest-validated adoption step.
"""
from __future__ import annotations

from typing import Any


def _field(s: Any, key: str, default: float = 0.0):
    if isinstance(s, dict):
        return s.get(key, default)
    return getattr(s, key, default)


def signal_ev(s: Any) -> float:
    """Expected-value proxy for ranking: ``confluence × max(R:R, 0)``. Reads
    ``rr`` then falls back to ``rr1`` (the Signal field name). Higher = better."""
    conf = float(_field(s, "confluence", 0.0) or 0.0)
    rr = _field(s, "rr", None)
    if rr is None:
        rr = _field(s, "rr1", 0.0)
    rr = float(rr or 0.0)
    return conf * max(rr, 0.0)


def rank_signals_by_ev(signals: list) -> list:
    """Signals sorted by EV descending (stable for equal EV)."""
    return sorted(signals, key=signal_ev, reverse=True)


def allocate_slots(signals: list, free_slots: int) -> list:
    """The top ``free_slots`` signals by EV — the ones to actually open this
    cycle. Empty when no free slots."""
    if free_slots <= 0:
        return []
    return rank_signals_by_ev(signals)[:free_slots]
