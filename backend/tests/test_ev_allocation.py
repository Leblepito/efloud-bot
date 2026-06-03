"""S5: expected-value slot allocation primitive.

When the open-position slots are full, signals are taken first-come-first-served
(symbol-loop order) — a weak BTC signal can occupy a slot a strong ETH signal
then can't take. This module ranks candidate signals by an EV proxy
(confluence × R:R) and allocates the free slots to the highest-EV signals.

Pure functions; works on Signal objects or plain dicts. Live wiring (buffering
all candidate signals across the symbol loop, then allocating) is a separate,
backtest-validated adoption step.
"""
from types import SimpleNamespace

from engine.allocation import allocate_slots, rank_signals_by_ev, signal_ev


def test_signal_ev_dict():
    assert signal_ev({"confluence": 80, "rr": 2.0}) == 160.0


def test_signal_ev_object_uses_rr1_fallback():
    s = SimpleNamespace(confluence=70, rr1=1.5)  # no `rr` attr → fall back to rr1
    assert signal_ev(s) == 70 * 1.5


def test_signal_ev_handles_missing_and_none():
    assert signal_ev({"confluence": 0}) == 0.0
    assert signal_ev({"confluence": 60, "rr": None, "rr1": 0}) == 0.0


def test_rank_orders_high_ev_first():
    a = {"confluence": 60, "rr": 1.5}   # 90
    b = {"confluence": 80, "rr": 2.0}   # 160
    c = {"confluence": 55, "rr": 2.0}   # 110
    ranked = rank_signals_by_ev([a, b, c])
    assert ranked == [b, c, a]


def test_allocate_slots_picks_top_n():
    a = {"id": "a", "confluence": 60, "rr": 1.5}
    b = {"id": "b", "confluence": 80, "rr": 2.0}
    c = {"id": "c", "confluence": 55, "rr": 2.0}
    chosen = allocate_slots([a, b, c], free_slots=2)
    assert [s["id"] for s in chosen] == ["b", "c"]


def test_allocate_zero_slots_is_empty():
    assert allocate_slots([{"confluence": 99, "rr": 9}], free_slots=0) == []
