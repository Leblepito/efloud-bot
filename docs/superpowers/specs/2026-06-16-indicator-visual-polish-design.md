# İndikatör Görsel Polish (Wave-1) — Design Spec

**Date:** 2026-06-16
**Status:** Approved (brainstorm, approach A) → ready for implementation (Pine + TV iteration)
**Owner:** Claude (TV MCP). **File:** `pine/u2algo/wave1_signals.pine` (507 satır, 12 input, 4 box / 7 label / 10 line / 1 table / 8 bgcolor)

## Sorun (TV'de doğrulandı, 2026-06-16)
Operatör feedback + screenshot: indikatör "çizgileri ve signals'ı tam anlaşılır/kullanıcı-dostu değil". Kök sebepler (capture'dan):
- **bgcolor duvarları (8 adet)** + tüm-geçmiş box/zone çizimi → grafik kutu-duvarı.
- **Etiket yoğunluğu** (FH/LL/HH her yerde, küçük) → okunamaz.
- **Renk/opaklık karmaşası** (üst üste yarı-saydam).
- **Sinyal sunumu** (SHORT/LONG %) net değil; legend/rehber yok.
- (Ek: kullanıcı chart'ında 5 indikatör üst üsteydi — bu ayrı; bizimki tek başına da yoğun.)

## Yaklaşım A — Temiz-default + layer toggle (onaylandı)
Default görünüm temiz + screenshot-hazır; power-user'a toggle esnekliği. **SADECE GÖRSEL — sinyal/SL/TP/entry LOGIC'i DEĞİŞMEZ.**

### Değişiklikler
1. **Layer toggle input'ları** (gruplu, "Görünüm" başlığı): `show_zones`, `show_labels`, `show_signals`, `show_bgcolor` (default: bgcolor OFF veya çok düşük opaklık), `show_table`. Her çizim bu flag'lere gate'lenir.
2. **Tarihsel limit:** sadece AKTİF/yakın zone'lar çizilir (örn. son N bar veya untested/active zone'lar). `box.new`/`bgcolor` geçmişe yayılmaz → duvar gider. `max_boxes_count`/`max_labels_count` ayarı.
3. **bgcolor azalt/kaldır:** 8 bgcolor → kaldır veya tek/çok-düşük-opaklık; yerine kenarlıklı (border) düşük-opaklık `box` kullan (daha okunur).
4. **Etiket cila:** label sayısını azalt (sadece kilit swing/setup), boyut/renk netleştir, çakışma azalt.
5. **Renk semantiği:** net + tutarlı (bullish=yeşil tonu, bearish=kırmızı tonu, zone=nötr/mavi; opaklık düşük). Tek bir palet.
6. **Info table cila:** tek `table` (köşe) — bias / setup / SL / TP / RR kompakt; okunur tipografi.
7. **Legend (opsiyonel):** table içinde kısa "ne ne demek" satırı veya net renk-kodu.

### Kısıtlar
- `pine/efloud_signals.pine` (SMC v2 port) **ASLA** ezilmez — bu görev yalnız `pine/u2algo/wave1_signals.pine`.
- Pine v6 syntax; **G-T2 compile PASS = 0 hata 0 marker** (TV MCP `pine_smart_compile` + `pine_get_errors`).
- Sinyal/hesap LOGIC'i byte-eşdeğer davranır; yalnız çizim/görünüm değişir.
- RE10045 riski (memory): inline-heavy bağlamda UDF/ölçek limiti → gerekirse inline tut, gating ekle.

### Süreç (iteratif, TV MCP)
Pine edit → `pine_set_source` → `pine_smart_compile` → `pine_get_errors` (0'a kadar) → `capture_screenshot` → değerlendir → rafine. Temiz bir referans sembol/TF'de (örn. BTCUSDT 1h, yakın setup) screenshot.

## Acceptance
- [ ] Default görünüm temiz + kullanıcı-dostu + **screenshot-hazır** (kutu-duvarı yok, etiketler okunur, renkler net).
- [ ] Layer toggle'ları çalışıyor (zones/labels/signals/bgcolor/table show-hide).
- [ ] `pine_smart_compile` 0 hata 0 marker.
- [ ] Sinyal/SL/TP LOGIC değişmedi (sadece görsel).
- [ ] `pine/efloud_signals.pine` dokunulmadı.
- [ ] 3-5 temiz annotated screenshot → `u2algo-site/assets/premium/` (Task 6 — premium.html için).

## Sonra
Temiz görsel → annotated screenshot'lar → premium.html'e → TV paid/invite-only publish (operatör manuel) → satış.
