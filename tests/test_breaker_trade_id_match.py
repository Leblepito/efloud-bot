"""E-5 (2026-07-18): record_trade_correction float-value match → trade_id-match.

Eski eşleşme YALNIZ float değerle yapılıyordu (`abs(pnl - old_pnl) < 1e-9`,
en-yeniden geriye ilk eşleşen). Ledger'da AYNI pnl değerli iki kayıt varsa
(iki break-even 0.0, ya da aynı tahminle kapanan iki trade) düzeltme YANLIŞ
(en yeni) kaydı mutasyona uğratır; tail-recompute yanlış kayıttan yürür ve
sayaç gerçek seriden KISA çıkabilir (guard zayıflar — aşağıdaki para testi).

Fix: audit sweep zaten (trade_id, old, new) üretiyor (exchange/__init__.py
audit_realized_pnl → `pos.order_id or f"{symbol}-{opened_at}"`). Artık:
  * record_trade(pnl, ts, trade_id=None) ledger dict'ine "trade_id" yazar,
  * record_trade_correction(old, new, trade_id=None) önce id ile eşler,
    id yoksa / bulunamazsa ESKİ değer-eşleşmesine düşer (fallback) —
    id'siz eski kayıtlar ve orchestrator STEP5 (logical pos, id yok)
    için davranış birebir korunur.

Fail-closed max() recompute'a (B3/W1.3) DOKUNULMAZ — burada invariant testi var.
"""
import json

import pytest

from engine.safety.breaker import CircuitBreaker


def _breaker(limit=10):
    return CircuitBreaker(consecutive_loss_limit=limit, starting_balance=2000.0)


def test_id_match_targets_correct_entry_among_equal_values():
    """PARA TESTİ — eski kod bu senaryoda sayacı DÜŞÜK sayar (guard zayıflar).

    Ledger (eski→yeni): A=-3.0, B=-3.0, C=-1.0 → seri 3.
    Audit ESKİ A'yı loss→win düzeltir (örn. funding iadesi): gerçek ledger
    [+1(A), -3(B), -1(C)] → kuyruk C,B = 2 kayıp, sonra A win → seri 2.
    Eski değer-eşleşmesi reversed'da B'yi (en yeni -3.0) bulurdu:
    [-3(A), +1(B), -1(C)] → kuyruk C=1, B win'de durur → seri 1 (YANLIŞ, kısa).
    """
    b = _breaker()
    b.record_trade(-3.0, trade_id="A")
    b.record_trade(-3.0, trade_id="B")
    b.record_trade(-1.0, trade_id="C")
    assert b.consecutive_losses == 3
    bal = b.current_balance

    b.record_trade_correction(old_pnl=-3.0, new_pnl=+1.0, trade_id="A")

    by_id = {t["trade_id"]: t["pnl"] for t in b.trades_this_week}
    assert by_id == {"A": +1.0, "B": -3.0, "C": -1.0}, \
        "düzeltme id'nin gösterdiği A'ya uygulanmalı, değer-ikizi B'ye değil"
    assert b.consecutive_losses == 2, \
        "gerçek kuyruk [C,B]=2; değer-eşleşmesi 1'e düşürüyordu (zayıflama)"
    assert b.current_balance == pytest.approx(bal + (1.0 - -3.0))


def test_equal_value_breakeven_twins_id_match():
    """İki BE 0.0 ikizi: id ile ESKİ olan hedeflenir, yeni olan bozulmaz."""
    b = _breaker()
    b.record_trade(0.0, trade_id="BE-old")
    b.record_trade(0.0, trade_id="BE-new")
    b.record_trade_correction(old_pnl=0.0, new_pnl=-1.0, trade_id="BE-old")
    by_id = {t["trade_id"]: t["pnl"] for t in b.trades_this_week}
    assert by_id == {"BE-old": -1.0, "BE-new": 0.0}


def test_value_fallback_when_no_id_given():
    """id verilmezse ESKİ davranış birebir: en-yeni değer eşleşmesi mutasyonlanır
    (orchestrator STEP5 logical yolunda id yok — bu yol değişmemeli)."""
    b = _breaker()
    b.record_trade(-5.0, trade_id="A")
    b.record_trade(-5.0, trade_id="B")
    b.record_trade_correction(old_pnl=-5.0, new_pnl=+2.0)  # id yok
    by_id = {t["trade_id"]: t["pnl"] for t in b.trades_this_week}
    assert by_id == {"A": -5.0, "B": +2.0}, "id'siz düzeltme en-yeniyi bulmalı (eski davranış)"
    assert b.consecutive_losses == 0


def test_unknown_id_falls_back_to_value_match():
    """id verildi ama ledger'da yok (karışık-sürüm kayıt / restart sonrası) →
    değer-eşleşmesine düş; balance deltası TEK kez uygulanır."""
    b = _breaker()
    b.record_trade(-5.0, trade_id="X")
    bal = b.current_balance
    b.record_trade_correction(old_pnl=-5.0, new_pnl=-6.5, trade_id="UNKNOWN")
    assert b.trades_this_week[0]["pnl"] == -6.5
    assert b.current_balance == pytest.approx(bal + (-6.5 - -5.0))
    assert b.consecutive_losses == 1


def test_legacy_entries_without_id_key_no_crash():
    """Pre-E5 ledger dict'lerinde "trade_id" anahtarı YOK — .get() ile okunmalı,
    KeyError atmamalı; değer-fallback eskisi gibi çalışmalı."""
    b = _breaker()
    b.record_trade(-4.0)  # id'siz çağrı (eski imza uyumu)
    legacy = {"pnl": -7.0, "ts": b.trades_this_week[0]["ts"]}  # anahtar hiç yok
    b.trades_today.append(legacy)
    b.trades_this_week.append(legacy)
    b.record_trade_correction(old_pnl=-7.0, new_pnl=-8.0, trade_id="Z")
    assert legacy["pnl"] == -8.0
    b.record_trade_correction(old_pnl=-4.0, new_pnl=-4.5)
    assert b.trades_this_week[0]["pnl"] == -4.5


def test_fail_closed_max_recompute_unchanged_with_id_match():
    """B3/W1.3 invariantı: yürüyüş win görmeden ledger'ı tüketirse sayaç
    max(recomputed, mevcut) — id-match bunu ZAYIFLATAMAZ. Ledger'dan düşmüş
    eski kayıpları temsilen sayaç 5'te; ledger'da tek kayıp var."""
    b = _breaker()
    b.record_trade(-1.0, trade_id="A")
    b.consecutive_losses = 5  # daha eski kayıplar 7g penceresinden düşmüş senaryosu
    b.record_trade_correction(old_pnl=-1.0, new_pnl=-2.0, trade_id="A")
    assert b.consecutive_losses == 5, "win görülmedi → sayaç aşağı çekilemez"


def test_record_trade_default_id_none_and_to_dict_json_safe():
    """İmza geriye uyumlu: trade_id verilmeyen kayıt None taşır; to_dict()
    ledger'ı zaten serialize ETMİYOR — payload json.dumps ile aynen çalışmalı."""
    b = _breaker()
    b.record_trade(-1.0)
    b.record_trade(+2.0, trade_id="T1")
    assert b.trades_this_week[0]["trade_id"] is None
    assert b.trades_this_week[1]["trade_id"] == "T1"
    payload = b.to_dict()
    json.dumps(payload)  # raise etmemeli
    assert "trades_this_week" not in payload  # ledger persist edilmiyor (bilinçli)
