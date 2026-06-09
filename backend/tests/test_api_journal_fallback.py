import json
from backend.api import read_journal_history


def test_read_journal_history_returns_reconciled_closes(tmp_path):
    jf = tmp_path / "trade_journal.jsonl"
    rows = [
        {"trade_id": "a", "symbol": "BTC/USDT", "direction": "LONG",
         "realized_pnl": -2.5, "pnl_source": "exchange",
         "exit_timestamp": "2026-06-01T01:00:00Z"},
        {"trade_id": "b", "symbol": "SOL/USDT", "direction": "SHORT",
         "realized_pnl": 4.0, "pnl_source": "exchange",
         "exit_timestamp": "2026-06-01T02:00:00Z"},
    ]
    jf.write_text("\n".join(json.dumps(r) for r in rows))

    out = read_journal_history(str(jf), limit=10)

    assert len(out) == 2
    assert out[0]["symbol"] == "SOL/USDT"   # newest first
    assert out[1]["realized_pnl"] == -2.5
    assert out[0]["id"] == "b"
    assert out[0]["pnl_usdt"] == 4.0
    assert out[0]["closed_at"] == "2026-06-01T02:00:00Z"


def test_read_journal_history_missing_file_returns_empty():
    assert read_journal_history("/no/such/file.jsonl", limit=10) == []


def test_read_journal_history_skips_open_trades(tmp_path):
    jf = tmp_path / "trade_journal.jsonl"
    rows = [
        {"trade_id": "open", "symbol": "BTC/USDT", "exit_timestamp": None},
        {"trade_id": "closed", "symbol": "ETH/USDT",
         "exit_timestamp": "2026-06-01T03:00:00Z", "realized_pnl": 1.0},
    ]
    jf.write_text("\n".join(json.dumps(r) for r in rows))
    out = read_journal_history(str(jf), limit=10)
    assert len(out) == 1
    assert out[0]["trade_id"] == "closed"
