import json
from pathlib import Path
from unittest.mock import MagicMock
from scripts.routines import _base

def test_load_config_reads_safety_block(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("safety:\n  weekly_drawdown_limit_pct: 8\nsymbols: [BTC/USDT]\n", encoding="utf-8")
    out = _base.load_config(str(cfg))
    assert out["safety"]["weekly_drawdown_limit_pct"] == 8
    assert out["symbols"] == ["BTC/USDT"]

def test_snapshot_roundtrip_stamps_last_checked(tmp_path):
    p = tmp_path / "state" / "demo_snapshot.json"
    _base.write_snapshot(str(p), {"foo": 1})
    data = _base.read_snapshot(str(p))
    assert data["foo"] == 1
    assert "last_checked" in data  # ISO8601 stamp auto-added

def test_read_snapshot_missing_returns_empty(tmp_path):
    assert _base.read_snapshot(str(tmp_path / "nope.json")) == {}

def test_write_report_creates_dirs(tmp_path):
    rp = tmp_path / "reports" / "demo.md"
    _base.write_report(str(rp), "# Hello")
    assert rp.read_text(encoding="utf-8") == "# Hello"

def test_make_future_client_is_injectable():
    fake = object()
    assert _base.make_future_client(client=fake) is fake  # injection short-circuits ccxt

def test_get_api_logs_in_and_gets(monkeypatch):
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    # Mock post response (login)
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_client.post.return_value = mock_post_res
    mock_client.cookies = {"efloud_session": "token123"}
    
    # Mock get response
    mock_get_res = MagicMock()
    mock_get_res.status_code = 200
    mock_get_res.json.return_value = {"hello": "world"}
    mock_client.get.return_value = mock_get_res
    
    # Inject mock client into httpx.Client
    monkeypatch.setattr("httpx.Client", lambda *args, **kwargs: mock_client)
    
    monkeypatch.setenv("DASHBOARD_PASSWORD", "testpass")
    
    res = _base.get_api("/api/status")
    assert res == {"hello": "world"}
    mock_client.post.assert_called_once_with("http://localhost:8080/api/login", json={"password": "testpass"})
    mock_client.get.assert_called_once_with("http://localhost:8080/api/status", params=None)
