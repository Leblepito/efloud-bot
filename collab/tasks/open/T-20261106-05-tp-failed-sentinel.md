---
id: T-20261106-05
title: Ana klondaki TP_FAILED-sentinel WIP'inin incelenmesi + TP-tükenme regresyon testi
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: abacus
parent: null
created: 2026-11-06
touches_live: false
---

## Amaç
Ana klonda (`master@6d70ae0`) commit'lenmemiş bir `exchange/__init__.py` değişikliği
bulundu: TP yerleştirme retry'ları tükenince `""` yerine `TP_FAILED` sentinel'i
yazıyor, repair döngüsü bu sentinel'i de yeniden gönderiyor, ayrıca kullanılmayan bir
`notification_mgr` parametresi ekliyor. Amaç: niyeti bulmak, gerçek bir hatayı
düzeltip düzeltmediğini kanıtlamak, gerekiyorsa tamamlamak.

## Girdi
- Ana klon `git diff exchange/__init__.py` (WIP; dokunulmadı, operatör kararı bekliyor)
- `exchange/__init__.py`: `_is_real_oid`, `_retry_tp_order`, `_repair_missing_protection_orders`, `open_position`, `reconcile`, `_cancel_position_siblings`, `_estimate_exit_price`

## Beklenen çıktı (Definition of Done)
- [x] Niyet + kanıt: WIP'in iddia ettiği hata master'da YOK — `""` zaten repair'i tetikliyor ve `_is_real_oid("")` zaten False.
- [x] Uçtan uca regresyon testi: `backend/tests/test_tp_exhausted_retry_repair_e2e.py` (4 test, gösterimden bağımsız; mutasyonla doğrulandı).
- [x] WIP port EDİLMEDİ (gerekçe PR'da): mevcut 6 testi kırıyor, rollback'te sahte TP1 atfı riski, `notification_mgr` için niyet/çağıran yok.
- [ ] Operatör: ana klondaki WIP'i atma/saklama kararı.

## Kısıtlar
- Canlı emir yolu kodu DEĞİŞMEDİ (yalnız test + collab dosyaları) → deploy etkisi yok.
- `configs/*.yaml`, `pine/efloud_signals.pine`, safety/risk blokları dokunulmadı.

## Log
- 2026-11-06 claude-code: WIP incelendi, port edilmedi; e2e regresyon testi + bulgular PR'da.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
