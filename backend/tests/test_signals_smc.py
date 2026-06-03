"""Unit tests for the SMC telemetry heuristic (no network / no engine needed).

Run:
    .venv\\Scripts\\pytest backend/tests/test_signals_smc.py -v
"""
from __future__ import annotations

from backend.signals_smc import compute_smc_heuristic


def _ramp_candles(n: int = 80) -> list[dict]:
    """Gentle uptrend; insert one clean bullish 3-candle FVG near the middle."""
    candles = []
    price = 100.0
    t0 = 1_700_000_000  # arbitrary epoch seconds
    step = 900  # 15m
    for i in range(n):
        o = price
        c = price + 0.4
        h = c + 0.3
        low = o - 0.3
        # Insert a bullish imbalance at i == 40: candle[39].high < candle[41].low
        if i == 41:
            o += 4.0
            c = o + 0.5
            h = c + 0.3
            low = o - 0.1  # low stays above candle[39].high → gap
        candles.append({"time": t0 + i * step, "open": o, "high": h, "low": low, "close": c})
        price = c
    return candles


def test_shape_keys():
    smc = compute_smc_heuristic(_ramp_candles())
    for key in ("structure", "fvgs", "obs", "pdh", "pdl", "range"):
        assert key in smc
    assert isinstance(smc["structure"], list)
    assert isinstance(smc["fvgs"], list)
    assert isinstance(smc["obs"], list)


def test_too_few_candles_is_empty():
    smc = compute_smc_heuristic([{"time": i, "open": 1, "high": 1, "low": 1, "close": 1} for i in range(5)])
    assert smc == {"structure": [], "fvgs": [], "obs": [], "pdh": None, "pdl": None, "range": None}


def test_bullish_fvg_detected():
    smc = compute_smc_heuristic(_ramp_candles())
    bull = [f for f in smc["fvgs"] if f["dir"] == "bull"]
    # the engineered imbalance should surface at least one bullish FVG
    assert len(bull) >= 1
    f = bull[0]
    assert f["top"] > f["bottom"]
    assert "startTime" in f and isinstance(f["mitigated"], bool)


def test_range_and_equilibrium():
    smc = compute_smc_heuristic(_ramp_candles())
    rng = smc["range"]
    assert rng is not None
    assert rng["high"] >= rng["low"]
    assert rng["low"] <= rng["eq"] <= rng["high"]


def test_structure_entries_valid():
    smc = compute_smc_heuristic(_ramp_candles())
    for s in smc["structure"]:
        assert s["kind"] in ("BOS", "CHOCH")
        assert s["dir"] in ("bull", "bear")
        assert isinstance(s["time"], int)
        assert isinstance(s["price"], float)
