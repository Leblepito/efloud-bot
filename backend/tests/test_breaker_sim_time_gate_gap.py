"""XFAIL regresyon pini — backtest'te breaker sim-time tutarsızlığı (2026-08-12 audit).

⚠️ Bu dosya engine/safety davranışını DEĞİŞTİRMEZ. İki gerçek defect'i
belgeler ve düzeltme operatör + risk-ops onayı beklediği için xfail(strict)
olarak pinler. Onay sonrası fix landing yaptığında xfail KIRILIR (strict),
böylece testin güncellenmesi zorunlu olur — sessizce yeşile kaymaz.

CANLI MOD ETKİLENMEZ: live'da check(now=None) ve record_trade(timestamp=None)
duvar-saatini kullanır; bu gap sadece backtest (sim-time) yolundadır.

Defect 1 — can_trade duvar-saatinden çözer:
  CircuitBreaker.check(now=sim) cooldown'u sim-time'da çözer AMA TRIPPED durum
  nesnesini döndürür; orchestrator .can_trade üstünden gate'ler (safe_orchestrator
  1206/1368) ve BreakerStatus.can_trade resume'u datetime.now() DUVAR-SAATİ ile
  karşılaştırır (breaker.py:54). Tarihsel backtest'te sim resume_at < duvar-saati
  now olduğundan can_trade daima True → daily/consecutive TRIP hiçbir şeyi
  bloklamaz (yalnız HALTED bloklar).

Defect 2 — record_trade timestamp'siz:
  safe_orchestrator.py:1304 record_trade(pnl) timestamp'siz çağırır; breaker
  duvar-saati damgalar; check(now=sim) günlük pencereyi sim gece-yarısına göre
  filtreler → duvar-saati damgalı trade'ler her zaman sim penceresinde kalır,
  daily_pnl tüm koşu boyunca birikir (günlük limit kümülatife dejenere olur).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from engine.safety.breaker import CircuitBreaker, BreakerState


@pytest.mark.xfail(
    strict=True,
    reason="engine/safety fix operatör + risk-ops onayı bekliyor (2026-08-12 audit). "
           "Onay sonrası can_trade sim-time tutarlı olunca bu xfail kırılır.",
)
def test_tripped_breaker_blocks_in_sim_time():
    """Sim-time'da TRIP edilen breaker, cooldown dolmadan sim-now ile
    can_trade=False dönmeli. Bugün duvar-saati resume'u geçtiği için True."""
    sim_now = datetime(2020, 1, 1, 12, 0, 0)  # geçmiş → duvar-saati bunu çoktan geçti
    br = CircuitBreaker(daily_loss_pct_limit=3.0, starting_balance=1000.0)

    # Sim gece-yarısından sonra günü -%5 zarara sok (limit -%3)
    br.record_trade(-50.0, timestamp=sim_now)
    status = br.check(now=sim_now)
    assert status.state == BreakerState.TRIPPED

    # 5 dk sonra hâlâ cooldown'da (resume = ertesi sim gece-yarısı)
    later = sim_now + timedelta(minutes=5)
    status2 = br.check(now=later)
    # DOĞRU davranış: sim-time'da hâlâ TRIPPED, trade bloklanmalı.
    # Bugünkü hata: can_trade duvar-saatinden çözüp True döndürüyor.
    assert status2.can_trade is False


@pytest.mark.xfail(
    strict=True,
    reason="engine/safe_orchestrator:1304 record_trade timestamp'siz — fix "
           "operatör + risk-ops onayı bekliyor (2026-08-12 audit).",
)
def test_daily_window_uses_trade_sim_timestamp():
    """record_trade sim-timestamp taşımazsa günlük pencere yanlış çalışır:
    dünkü bir zarar bugünkü günlük PnL'e sızmamalı."""
    day1 = datetime(2020, 1, 1, 12, 0, 0)
    day2 = datetime(2020, 1, 2, 12, 0, 0)
    br = CircuitBreaker(daily_loss_pct_limit=3.0, starting_balance=1000.0)

    # Dün -%2.5 zarar (timestamp'siz → breaker duvar-saati damgalar = BUGÜN)
    br.record_trade(-25.0)  # orchestrator:1304 ile aynı: timestamp yok
    # Bugün check: dünkü zarar bugünün penceresine SIZMAMALI
    status = br.check(now=day2)
    daily_pnl = status.metrics.get("daily_pnl")
    # DOĞRU: gün2 penceresi gün1 trade'ini görmez → daily_pnl ~ 0
    assert daily_pnl == 0 or daily_pnl is None
