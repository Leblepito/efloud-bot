---
id: T-20261107-05
title: SL koruması başarısız olduğunda Telegram uyarısı (alerter kuralları)
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: abacus
parent: T-20261107-03
created: 2026-11-07
touches_live: false
---

## Amaç
TP uyarısının (T-20261107-03, #308) devamı: pozisyon stop'suz kaldığında ya da SL
konamadığı için giriş geri alındığında operatör Telegram'dan haber alsın.
Trading koduna dokunulmadan, alerter'a log kuralı eklenerek yapılır. #308 branch'inin
üstüne kuruldu (`_esc`, `_tries`, `_flag_on` yardımcıları ortak).

## Girdi
- `exchange/__init__.py` yapısal event'leri: `repair_missing_sl`, `tp_placement_failed_after_sl` (tp_leg=SL_REPAIR), `sl_repair_unreachable_closing`, `fallback_close_failed` (reason=SL_REPAIR_UNREACHABLE), `entry_rollback_after_sl_failure`, `entry_rollback_failed`.
- `ops/alerter/rules.py`, `docker-compose.prod.yml` `alerter` servisi.

## Beklenen çıktı (Definition of Done)
- [x] `SlUnprotectedRule` (CRITICAL, pozisyon başına 15 dk): SL_REPAIR başarısız, rollback başarısız, stop'suz pozisyon kapatılamadı.
- [x] `SlProtectionEventRule` (WARNING, 1 saat): SL eksik → yeniden gönderiliyor, fiyat SL'yi geçmiş → kapatılıyor, giriş geri alındı.
- [x] Kodda default OFF: `EFLOUD_ALERTER_SL_ALERTS`.
- [x] Prod açma satırı ayrı commit (yalnız alerter env).
- [x] Testler: kural birim testleri + gerçek `OrderManager` + `JsonFormatter` sözleşme testleri (open rollback ok/başarısız, SL_REPAIR hatası, -2021 + kapatma hatası, verify rollback).
- [ ] Operatör: #308 ve bu PR merge + alerter image build + `up -d --no-deps alerter`.

## Kısıtlar
- Trading kodu (exchange/engine/configs) DEĞİŞMEDİ.
- Yalnız mid bot logu (operatör: long/scalp çalışmıyor, kapsam gerekmiyor).

## Log
- 2026-11-07 claude-code: SL alerter kuralları + testler + compose flag; #308 üstüne stacked PR açıldı.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
