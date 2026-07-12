"""Journal: update_adaptation _persist çağırmıyordu (2026-07-11 review, ertelenen).

Piramit ekleme / partial exit / hedge güncellemeleri yalnız in-memory cache'e
yazılıyordu — restart/crash sonrası adaptasyon geçmişi kayboluyordu (record_exit
tesadüfen aynı snapshot'ı persist ederse kurtuluyordu, açık pozisyonda asla).
"""
from __future__ import annotations

from engine.journal import TradeJournal, TradeSnapshot


def _snap(trade_id="T1"):
    return TradeSnapshot(
        trade_id=trade_id, symbol="BTC/USDT", direction="LONG", timeframe="15m",
        entry_timestamp="2026-07-12T00:00:00", entry_price=100.0,
        sl_initial=95.0, tp1_initial=110.0, tp2_initial=120.0,
        position_size=1.0, htf_bias="BULL", intent_score_entry=70,
        intent_label_entry="BULLISH", confluence_score=60,
    )


def test_addition_survives_restart(tmp_path):
    path = str(tmp_path / "journal.jsonl")
    j1 = TradeJournal(path)
    j1.record_entry(_snap())
    j1.update_adaptation("T1", "addition", {"price": 102.0, "size": 0.5})

    j2 = TradeJournal(path)  # restart simülasyonu — yalnız diskteki görülür
    snap = j2.get("T1")
    assert snap is not None
    assert len(snap.additions) == 1, "addition diske persist edilmedi"
    assert snap.additions[0]["price"] == 102.0


def test_partial_and_hedge_survive_restart(tmp_path):
    path = str(tmp_path / "journal.jsonl")
    j1 = TradeJournal(path)
    j1.record_entry(_snap())
    j1.update_adaptation("T1", "partial", {"price": 108.0, "size": 0.5})
    j1.update_adaptation("T1", "hedge_open", {})
    j1.update_adaptation("T1", "hedge_close", {"pnl": -3.0})

    snap = TradeJournal(path).get("T1")
    assert len(snap.partial_exits) == 1
    assert snap.hedge_opened is True
    assert snap.hedge_pnl == -3.0


def test_unknown_trade_id_still_noop(tmp_path):
    j = TradeJournal(str(tmp_path / "journal.jsonl"))
    j.update_adaptation("YOK", "addition", {"price": 1.0})  # crash yok
    assert j.get("YOK") is None
