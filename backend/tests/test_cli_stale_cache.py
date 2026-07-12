"""BT-15: cli._load_data_for_period stale-cache kontrolü.

Periyot [now - period_days, now] istenir ama cache'in gerçekten periyot SONUNU
kapsayıp kapsamadığı hiç kontrol edilmiyordu — haftalar önce fetch edilmiş
cache ile "son 30 gün" backtest'i sessizce eski bir pencerede koşuyordu.

Fix: manifest max_ts periyot sonundan 2×TF'den fazla gerideyse yüksek sesle
log.warning (davranış kırılmaz; offline koşular çalışmaya devam eder).
"""
from __future__ import annotations

import logging

import pandas as pd
import pytest

from backtest.cli import _load_data_for_period
from data.cache import OHLCVCache


def _put(cache_dir, symbol, tf, end_ts, n=200, freq="15min"):
    idx = pd.date_range(end=end_ts, periods=n, freq=freq)
    df = pd.DataFrame({
        "open": [100.0] * n, "high": [101.0] * n, "low": [99.0] * n,
        "close": [100.0] * n, "volume": [1.0] * n,
    }, index=idx)
    OHLCVCache(cache_dir).put(symbol, tf, df)


def test_stale_cache_emits_loud_warning(tmp_path, caplog):
    stale_end = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=10)
    _put(tmp_path, "BTC/USDT", "15m", stale_end)
    with caplog.at_level(logging.WARNING, logger="efloud.backtest.cli"):
        data = _load_data_for_period(["BTC/USDT"], ["15m"], period_days=30,
                                     cache_dir=str(tmp_path))
    assert "BTC/USDT" in data
    stale_msgs = [r.message for r in caplog.records if "STALE" in r.message.upper()]
    assert stale_msgs, "10 gün eski cache sessizce kabul edildi"
    assert "15m" in stale_msgs[0]


def test_fresh_cache_no_warning(tmp_path, caplog):
    fresh_end = pd.Timestamp.utcnow().tz_localize(None)
    _put(tmp_path, "BTC/USDT", "15m", fresh_end)
    with caplog.at_level(logging.WARNING, logger="efloud.backtest.cli"):
        _load_data_for_period(["BTC/USDT"], ["15m"], period_days=30,
                              cache_dir=str(tmp_path))
    assert not [r for r in caplog.records if "STALE" in r.message.upper()]


def test_missing_cache_still_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        _load_data_for_period(["ETH/USDT"], ["15m"], period_days=30,
                              cache_dir=str(tmp_path))
