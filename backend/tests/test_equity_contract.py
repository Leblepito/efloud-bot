"""/api/equity alan-adı sözleşmesi (2026-08-12 audit).

İki veri yolu iki FARKLI şema yayıyordu:
  - DB yolu:      {ts, balance}   → frontend EquityChart bunu okur
  - journal yolu: {t, equity}     → birleşik panel bunu okur
Sonuç: DB'siz prod'da frontend grafiği boş; DB'li kurulumda panel grafiği boş.
Endpoint artık HER İKİ yolda da iki şemanın alanlarını birlikte yayar.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import backend.api as api_mod


@pytest.mark.asyncio
async def test_journal_fallback_emits_both_schemas(tmp_path, monkeypatch):
    jf = tmp_path / "trade_journal.jsonl"
    rows = [
        {"trade_id": "a", "realized_pnl": 10.0, "exit_timestamp": "2026-06-01T01:00:00Z"},
        {"trade_id": "b", "realized_pnl": -4.0, "exit_timestamp": "2026-06-01T02:00:00Z"},
    ]
    jf.write_text("\n".join(json.dumps(r) for r in rows))
    monkeypatch.setenv("EFLOUD_TRADE_JOURNAL", str(jf))

    async def no_db(days: int = 7):
        return []

    monkeypatch.setattr(api_mod.db, "fetch_equity_history", no_db)

    series = await api_mod.equity(days=7)

    assert len(series) == 2
    for p in series:
        assert p["t"] == p["ts"]
        assert p["equity"] == p["balance"]
    # kümülatif: 10, sonra 10-4=6
    assert series[0]["equity"] == 10.0
    assert series[1]["equity"] == 6.0


@pytest.mark.asyncio
async def test_db_path_emits_both_schemas(monkeypatch):
    ts = datetime(2026, 8, 1, tzinfo=timezone.utc)

    async def fake_db(days: int = 7):
        return [{"ts": ts, "balance": 1234.5, "open_positions_count": 2}]

    monkeypatch.setattr(api_mod.db, "fetch_equity_history", fake_db)

    series = await api_mod.equity(days=7)

    assert len(series) == 1
    p = series[0]
    assert p["balance"] == 1234.5
    assert p["equity"] == 1234.5          # panel alias'ı
    assert p["t"] == p["ts"]              # panel alias'ı
    assert p["open_positions_count"] == 2  # mevcut alanlar korunur
