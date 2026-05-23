"""Stop-hunt rate metric (PR #S4, spec §8.2).

A stop hunt is when SL fires and then price immediately reaches the original
tp1 within a short window — evidence the market just swept the stop and
reverted toward the intended target.

For LONG: stop-hunt if any high in next N bars >= original tp1.
For SHORT: stop-hunt if any low in next N bars <= original tp1.
"""
from __future__ import annotations

import pandas as pd

from backtest.metrics import compute_stop_hunt_rate


def _trade(symbol, direction, sl, tp1, exit_reason, closed_at):
    return {
        "symbol": symbol,
        "direction": direction,
        "entry": 100.0,
        "sl": sl,
        "tp1": tp1,
        "pnl": -10.0 if exit_reason == "SL" else 10.0,
        "exit_reason": exit_reason,
        "closed_at": closed_at,
        "exit": sl if exit_reason == "SL" else tp1,
    }


def _data(symbol, highs_after, lows_after, freq="15min"):
    """Build df with 10 bars after the synthetic close time."""
    idx = pd.date_range("2025-01-01 00:15", periods=10, freq=freq, tz="UTC")
    n = 10
    h = (highs_after + [100.0] * n)[:n]
    lo = (lows_after + [100.0] * n)[:n]
    return {
        symbol: {
            "15m": pd.DataFrame(
                {
                    "open": [100.0] * n,
                    "high": h,
                    "low": lo,
                    "close": [100.0] * n,
                    "volume": [1.0] * n,
                },
                index=idx,
            )
        }
    }


def test_no_sl_exits_returns_zero():
    trades = [_trade("ETH/USDT", "LONG", 95.0, 110.0, "TP1", "2025-01-01 00:00:00+00:00")]
    assert compute_stop_hunt_rate(trades, _data("ETH/USDT", [], [])) == 0.0


def test_no_trades_returns_zero():
    assert compute_stop_hunt_rate([], _data("ETH/USDT", [], [])) == 0.0


def test_pure_stop_hunt_returns_one():
    # SL at 95, tp1 at 110, LONG. Next 4 bars: high reaches 112 → stop hunt.
    trades = [_trade("ETH/USDT", "LONG", 95.0, 110.0, "SL", "2025-01-01 00:00:00+00:00")]
    data = _data("ETH/USDT", [105.0, 108.0, 112.0, 113.0], [94.0, 93.0, 95.0, 96.0])
    assert compute_stop_hunt_rate(trades, data, lookback_bars=4) == 1.0


def test_clean_sl_not_counted():
    # Price keeps going against original direction → no stop hunt.
    trades = [_trade("ETH/USDT", "LONG", 95.0, 110.0, "SL", "2025-01-01 00:00:00+00:00")]
    data = _data("ETH/USDT", [94.0, 93.0, 92.0, 91.0], [90.0, 89.0, 88.0, 87.0])
    assert compute_stop_hunt_rate(trades, data, lookback_bars=4) == 0.0


def test_short_direction_uses_low():
    # SHORT trade: SL at 105, tp1 at 90. Stop hunt = low reaches 90 after SL exit.
    trades = [_trade("ETH/USDT", "SHORT", 105.0, 90.0, "SL", "2025-01-01 00:00:00+00:00")]
    data = _data("ETH/USDT", [106.0, 107.0, 108.0, 109.0], [100.0, 95.0, 89.0, 88.0])
    assert compute_stop_hunt_rate(trades, data, lookback_bars=4) == 1.0


def test_mixed_sl_and_tp_only_sl_counted():
    # 2 SL exits (1 stop-hunt, 1 clean) + 1 TP exit → rate = 0.5
    trades = [
        _trade("ETH/USDT", "LONG", 95.0, 110.0, "SL", "2025-01-01 00:00:00+00:00"),
        _trade("ETH/USDT", "LONG", 95.0, 110.0, "TP1", "2025-01-01 00:00:00+00:00"),
    ]
    # Stop-hunt: high reaches 112 within 4 bars
    data = _data("ETH/USDT", [105.0, 108.0, 112.0, 113.0], [94.0, 93.0, 95.0, 96.0])
    # 1 SL → 1 hunt → 1.0
    assert compute_stop_hunt_rate(trades, data, lookback_bars=4) == 1.0


def test_lookback_window_respected():
    # tp1 reached at bar 5, lookback=4 → not counted; lookback=6 → counted.
    trades = [_trade("ETH/USDT", "LONG", 95.0, 110.0, "SL", "2025-01-01 00:00:00+00:00")]
    data = _data("ETH/USDT", [99.0, 99.0, 99.0, 99.0, 112.0, 99.0], [98.0] * 6)
    assert compute_stop_hunt_rate(trades, data, lookback_bars=4) == 0.0
    assert compute_stop_hunt_rate(trades, data, lookback_bars=6) == 1.0
