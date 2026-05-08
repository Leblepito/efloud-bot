"""Binance public OHLCV fetcher via CCXT — range fetch + gap detection."""
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from data.fetcher import OHLCVFetcher, FetchResult


@pytest.fixture
def fetcher():
    """Fetcher with mocked CCXT client to avoid real network."""
    f = OHLCVFetcher.__new__(OHLCVFetcher)
    f.client = MagicMock()
    f.client.exchange = MagicMock()
    f.tf_minutes = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    return f


def test_fetch_complete_range_no_gaps(fetcher):
    # Mock CCXT returning 100 contiguous bars
    bars = [[1700000000000 + i * 900_000, 100, 101, 99, 100.5, 1.0] for i in range(100)]
    fetcher.client.exchange.fetch_ohlcv.return_value = bars

    result = fetcher.fetch_ohlcv_range("BTC/USDT", "15m",
                                          start_ms=1700000000000,
                                          end_ms=1700000000000 + 100 * 900_000)
    assert isinstance(result, FetchResult)
    assert len(result.df) == 100
    assert result.gaps == []


def test_fetch_with_gap_returns_gap_list(fetcher):
    # 50 bars, then a 30min gap (2 bars), then 48 more = 98 actual of 100 expected
    bars_1 = [[1700000000000 + i * 900_000, 100, 101, 99, 100, 1.0] for i in range(50)]
    bars_2 = [[1700000000000 + (52 + i) * 900_000, 100, 101, 99, 100, 1.0] for i in range(48)]
    fetcher.client.exchange.fetch_ohlcv.return_value = bars_1 + bars_2

    result = fetcher.fetch_ohlcv_range("BTC/USDT", "15m",
                                          start_ms=1700000000000,
                                          end_ms=1700000000000 + 100 * 900_000,
                                          max_gap_pct=10.0)  # allow the deliberate 2% gap
    assert len(result.df) == 98
    assert len(result.gaps) >= 1
    gap_start, gap_end = result.gaps[0]
    assert gap_end - gap_start == 30 * 60 * 1000  # 30 min gap


def test_fetch_refuses_excessive_gaps(fetcher):
    # Mock: only 50 of 100 expected bars (50% gap)
    bars = [[1700000000000 + i * 900_000, 100, 101, 99, 100, 1.0] for i in range(50)]
    fetcher.client.exchange.fetch_ohlcv.return_value = bars
    with pytest.raises(ValueError, match="exceeds max"):
        fetcher.fetch_ohlcv_range("BTC/USDT", "15m",
                                     start_ms=1700000000000,
                                     end_ms=1700000000000 + 100 * 900_000,
                                     max_gap_pct=1.0)
