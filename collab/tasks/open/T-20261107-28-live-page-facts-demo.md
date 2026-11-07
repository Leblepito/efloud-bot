---
id: T-20261107-28
title: live.html canlı-durum gerçekleri + site demo videosu (karar 5)
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: abacus
parent: T-20261106-04
created: 2026-11-07
touches_live: false
---

## Amaç
Karar 5 (vekâleten, spec 2026-11-07 §1 #5): demo videosu yalnız herkese açık illüstratif sayfalardan
(live.html simülasyon + premium.html), gerçek hesap verisi yok. Kayıt sırasında live.html'de canlıyla
çelişen bilgiler görüldü ve düzeltildi.

## Beklenen çıktı (Definition of Done)
- [x] live.html: 2026-11-07'de silinen `bot./v2./scalp.u2algo.com` adları kaldırıldı; Scalp/Long "Çalışıyor" → "Hazır (beklemede)", Mid "Canlı"; "3 Aktif Bot / 3 Bot Üretimde" → "1 canlı + 2 hazır".
- [x] Test: `scripts/test_seo_meta.js` — hiçbir sayfa silinen alt alan adlarını içeremez (RED→GREEN).
- [x] `scripts/demo/record_site_demo.cjs` (Playwright; --rehearse + kayıt; yalnız hover, tıklama yok).
- [ ] Merge + Railway deploy sonrası video yeniden kaydedilir (yerel çıktı `reports/demo/`, repoya girmez).
