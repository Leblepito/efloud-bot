# B1 (W1.4) — OrderManager.positions Thread-Lock Tasarım Notu

## Problem
`exchange.OrderManager.positions` (List[Position]) iki bağlamdan erişilir:
bot cycle thread'i (open/close/reconcile/SL-repair/force-close) ve backend API
tarafı (dashboard okumaları + `_persist` snapshot'ı üzerinden dosya tüketimi).
Kilit yoktu; CPython GIL tekil liste op'larını atomik yapar ama BİLEŞİK diziler
yarışa açıktı.

## Kritik Bölge Envanteri (56ec005 itibarıyla 16 site)

| Tür | Siteler | Yarış riski |
|-----|---------|-------------|
| append | open_position dry (~1059), live (~1267) | persist/yürüyüş sırasında ekleme → tutarsız snapshot |
| kontrol-et-ve-sil | rollback finally (~1968), close_position ön-kontrol (~2204) + remove (~2194), reconcile remove (~1445) | çifte-silme → ValueError (canlı loop crash) |
| yürü-ve-mutasyona-uğrat | verify_sltp (~744), reconcile (~1415), SL-repair (~2129), force-close (~2334) | `[:]` kopya thread-içi güvenliydi; kopyalama anı kilitlendi |
| küme/üyelik/len okumaları | orphan detect (~1360), cancel sweep (~1516), open_count (~2358) | hafif — snapshot'a normalize edildi |
| persist/restore | `_persist` payload (~2371), `_restore` atama (~2394, ~2410) | mutasyon-altında serialization; restore ataması |

Dış erişim: `safe_orchestrator.py` 797/886 — AYNI bot thread'inde read-only
generator; değişiklik gerekmedi.

## Tasarım Kararları
1. **Tek RLock + 3 yardımcı:** `_positions_add`, `_positions_discard`
   (atomik kontrol-et-ve-sil, bool döner), `_positions_snapshot` (tutarlı kopya).
   16 site mekanik olarak bu üçüne yönlendirildi — kilit mantığı tek yerde.
2. **Kilit altında ASLA I/O yok:** ağ çağrıları, `asdict()` serialization ve
   json yazımı kilit DIŞINDA; kilit yalnız liste işlemini sarar (deadlock ve
   latency riski yok — canlı davranış nötr).
3. **RLock (Lock değil):** yardımcılar ileride kilitli bileşik akışlardan
   çağrılabilir; re-entrancy ucuz sigorta.
4. **Bilinen sınır (kapsam dışı):** Position ALAN mutasyonları (örn. tp1_hit)
   kilitsizdir — snapshot liste-tutarlılığı garantiler, alan-seviyesi tearing
   ayrı iş (gerekirse Position-içi kilit/immutable güncelleme deseni).

## Doğrulama
`backend/tests/test_order_manager_positions_lock.py`: atomik discard sözleşmesi
(deterministik) + 50-tur çifte-silme yarışı (tam 1 kazanan) + 4-rol hammer
(add/discard/snapshot/persist eşzamanlı; invariant + persist dosyası tutarlı).
Not: eşzamanlılık testleri doğası gereği deterministik RED üretmez — bu dosya
kilitli implementasyonun sözleşmesini sabitleyen regresyon ağıdır.
