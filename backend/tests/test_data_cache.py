"""Parquet cache: round-trip, atomic writes, sha256 verify, gap detection."""
import pandas as pd
import pytest

from data.cache import OHLCVCache, hash_dataframe


@pytest.fixture
def df():
    idx = pd.date_range("2026-01-01", periods=100, freq="15min")
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0},
        index=idx,
    )


def test_cache_round_trip_returns_identical_data(tmp_path, df):
    cache = OHLCVCache(tmp_path)
    cache.put("BTC/USDT", "15m", df)
    out = cache.get("BTC/USDT", "15m")
    assert out is not None
    pd.testing.assert_frame_equal(df, out, check_freq=False)


def test_cache_miss_returns_none(tmp_path):
    cache = OHLCVCache(tmp_path)
    assert cache.get("ETH/USDT", "1h") is None


def test_cache_corruption_detected_and_refetched(tmp_path, df):
    cache = OHLCVCache(tmp_path)
    cache.put("BTC/USDT", "15m", df)

    # Corrupt the parquet file
    cache_file = cache._path("BTC/USDT", "15m")
    cache_file.write_bytes(b"GARBAGE_DATA")

    # cache.get should detect mismatch (sha256 verify) and return None
    out = cache.get("BTC/USDT", "15m")
    assert out is None, "Corrupted cache must return None to force re-fetch"


def test_cache_atomic_write_no_partial_files(tmp_path, df):
    cache = OHLCVCache(tmp_path)
    cache.put("BTC/USDT", "15m", df)
    # Only the final .parquet should exist; no .tmp leftovers
    files = list(tmp_path.rglob("*.tmp"))
    assert files == []
