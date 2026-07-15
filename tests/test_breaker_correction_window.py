"""B3 (W1.3, 2026-07-11 review): record_trade_correction tail-recompute
consecutive-loss serisini KISALTABİLİYORDU.

İki kusur (ikisi de trades_today'in 24h rolling pencere olmasından):
1. Seri pencereyi aşıyorsa (kayıplar >24h önce başladı) recompute yalnız
   bugünkü kuyruğu sayar → sayaç 3→1 gibi KISALIR (guard zayıflar). Oysa
   record_trade'in sayacı yalnız GERÇEK bir win ile sıfırlanır.
2. Düzeltilen trade 24h penceresinden düşmüşse match loop'u onu hiç bulamaz
   → ledger güncellenmez, recompute alakasız kuyruğu sayar.

Fix: match + recompute trades_this_week (7g) üzerinden; kuyruk yürüyüşü
win görmeden ledger'ı tüketirse sayaç ASLA aşağı çekilmez (fail-closed,
max(mevcut, recomputed)). Görünür trailing win varsa recomputed esastır
(loss→win düzeltmesi doğru şekilde sıfırlar/azaltır).
"""
from datetime import datetime, timedelta, timezone

from engine.safety.breaker import CircuitBreaker


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_same_sign_correction_must_not_shorten_cross_window_streak():
    """Kayıplar: -30h, -29h (pencere dışına yaşlanacak), -1h. Sayaç 3.
    Bugünkü tek kayba same-sign düzeltme geliyor → sayaç 3 KALMALI (eski kod
    bugünkü kuyruktan 1'e kısaltıyordu)."""
    b = CircuitBreaker(consecutive_loss_limit=10, starting_balance=2000.0)
    now = _now()
    b.record_trade(-5.0, timestamp=now - timedelta(hours=30))
    b.record_trade(-5.0, timestamp=now - timedelta(hours=29))
    b.record_trade(-7.0, timestamp=now - timedelta(hours=1))
    assert b.consecutive_losses == 3
    b.check()  # _cleanup_old_trades: -30h/-29h trades_today'den düşer (week'te kalır)
    assert len(b.trades_today) == 1

    b.record_trade_correction(old_pnl=-7.0, new_pnl=-8.5)  # hâlâ kayıp, daha büyük
    assert b.consecutive_losses == 3, (
        "trailing win yokken düzeltme seriyi kısaltamaz (fail-closed)"
    )


def test_correction_of_aged_out_trade_matches_week_ledger():
    """Sign-flip düzeltmesi 24h penceresinden düşmüş trade'e geliyor:
    kayıp(-30h), kayıp(-29h), est-WIN(-26h, sayacı sıfırladı), kayıp(-1h) → sayaç 1.
    Audit -26h'teki win'i kayba çevirir → gerçek trailing seri 4."""
    b = CircuitBreaker(consecutive_loss_limit=10, starting_balance=2000.0)
    now = _now()
    b.record_trade(-5.0, timestamp=now - timedelta(hours=30))
    b.record_trade(-5.0, timestamp=now - timedelta(hours=29))
    b.record_trade(+1.0, timestamp=now - timedelta(hours=26))  # fee-naive yanlış win
    assert b.consecutive_losses == 0
    b.record_trade(-3.0, timestamp=now - timedelta(hours=1))
    assert b.consecutive_losses == 1
    b.check()  # eski üçlü trades_today'den düştü
    assert len(b.trades_today) == 1

    bal = b.current_balance
    b.record_trade_correction(old_pnl=+1.0, new_pnl=-0.40)
    assert b.current_balance == bal + (-0.40 - 1.0), "balance delta her durumda uygulanır"
    assert b.consecutive_losses == 4, (
        "hafta ledger'ında eşleşip düzeltilmeli ve seri 4'e çıkmalı "
        "(eski kod today'de eşleşemeyip 1'de bırakıyordu)"
    )


def test_trailing_win_still_authoritative():
    """Görünür trailing win varsa recomputed esas — loss→win düzeltmesi
    seriyi meşru şekilde sıfırlar (mevcut davranış korunur, max() burada devreye girmez)."""
    b = CircuitBreaker(consecutive_loss_limit=10, starting_balance=2000.0)
    b.record_trade(-5.0)
    b.record_trade(-5.0)
    assert b.consecutive_losses == 2
    b.record_trade_correction(old_pnl=-5.0, new_pnl=+2.0)  # en son kayıp aslında win
    assert b.consecutive_losses == 0
