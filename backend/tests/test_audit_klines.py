"""Tests for backend.audit.klines."""
from unittest.mock import MagicMock, patch

import pytest

from backend.audit.klines import fetch_klines, symbol_to_binance


def _binance_kline_row(open_time_ms, open_, high, low, close, volume):
    """Binance returns klines as 12-element arrays. We only use the first 6."""
    return [open_time_ms, str(open_), str(high), str(low), str(close), str(volume),
            0, 0, 0, 0, 0, 0]


def test_fetch_klines_returns_normalized_candles():
    fake_response = [
        _binance_kline_row(1715200000000, 65000.0, 65500.0, 64800.0, 65200.0, 1234.5),
        _binance_kline_row(1715203600000, 65200.0, 65800.0, 65100.0, 65700.0, 987.6),
    ]
    with patch("backend.audit.klines.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: fake_response)
        candles = fetch_klines("BTCUSDT", "1h", 1715200000000, 1715203600000)

    assert len(candles) == 2
    assert candles[0]["open_time"] == 1715200000000
    assert candles[0]["high"] == 65500.0
    assert candles[0]["low"] == 64800.0
    assert candles[0]["close"] == 65200.0
    assert candles[1]["volume"] == 987.6


def test_fetch_klines_passes_correct_params():
    with patch("backend.audit.klines.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        fetch_klines("ETHUSDT", "5m", 100, 200)

    call = mock_get.call_args
    params = call.kwargs["params"]
    assert params["symbol"] == "ETHUSDT"
    assert params["interval"] == "5m"
    assert params["startTime"] == 100
    assert params["endTime"] == 200
    assert params["limit"] == 1500


def test_fetch_klines_handles_http_error():
    with patch("backend.audit.klines.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=429, text="rate limit hit")
        candles = fetch_klines("BTCUSDT", "1h", 0, 1)
    assert candles == []


def test_fetch_klines_handles_500_error():
    with patch("backend.audit.klines.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=500, text="internal error")
        candles = fetch_klines("BTCUSDT", "1h", 0, 1)
    assert candles == []


def test_fetch_klines_handles_network_exception():
    with patch("backend.audit.klines.requests.get", side_effect=ConnectionError("network down")):
        candles = fetch_klines("BTCUSDT", "1h", 0, 1)
    assert candles == []


def test_fetch_klines_handles_timeout():
    import requests as _requests
    with patch("backend.audit.klines.requests.get", side_effect=_requests.Timeout("timed out")):
        candles = fetch_klines("BTCUSDT", "1h", 0, 1)
    assert candles == []


def test_fetch_klines_handles_malformed_json():
    with patch("backend.audit.klines.requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(side_effect=ValueError("bad json")),
        )
        candles = fetch_klines("BTCUSDT", "1h", 0, 1)
    assert candles == []


def test_fetch_klines_empty_response_returns_empty_list():
    with patch("backend.audit.klines.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        candles = fetch_klines("BTCUSDT", "1h", 0, 1)
    assert candles == []


@pytest.mark.parametrize("internal,binance", [
    ("BTC/USDT:USDT", "BTCUSDT"),
    ("ETH/USDT", "ETHUSDT"),
    ("SOL/USDT:USDT", "SOLUSDT"),
    ("BTCUSDT", "BTCUSDT"),
    ("BTC/USDT:BUSD", "BTCUSDT"),
])
def test_symbol_to_binance(internal, binance):
    assert symbol_to_binance(internal) == binance
