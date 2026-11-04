---
id: T-20261105-01
title: "Soru: veri çekme sıklığı — 15m REST yerine websocket gerekli mi? (ölç, öner; kod yok)"
from: claude-code
to: abacus
status: in-review
claimed_by: abacus
reviewer: claude-code
parent: T-20261104-09
created: 2026-11-05
touches_live: false
---

## Amaç
Operatör: "Her sembol için 15 dakikada bir veri çekiyorsak bu büyük bir hata olabilir; websocket ile
bakılmalı." Abacus bunu bağımsız olarak değerlendirir: mevcut davranış ne, neyi kaçırıyor, websocket
neyi değiştirir, ve bu değişiklik **NET edge**'e katkı yapar mı yoksa yalnız gecikmeyi/uyarıları mı
iyileştirir. Sonuç ölçüm + öneridir; motor/config kodu yazılmaz.

## Girdi — claude-code'un doğruladığı gerçekler (master `1e9ad91`)
- Döngü 30 sn'de bir döner (`configs/config.phase2_1k.yaml:288 check_interval_sec: 30`), **ama** tarama
  yalnız yeni bir entry mumu kapanınca yapılır: `backend/bot_runner.py:540-553` (2026-06-26, `d7e04f0`).
  Sonra sembol başına 4 REST çağrısı (`:561-566`: HTF, MTF, entry, 1d; `kline_limit: 750`).
- `exchange/__init__.py:101-117` oluşmakta olan mumu atar → motor yalnız **kapanmış** barları görür
  (repaint koruması, C1). `current_price` = son kapanmış 15m mumun kapanışı.
- Bölgeye "dokundu" kararı `is_price_in_zone(current_price, zone)` (`engine/smc_v2/zones.py:81-83`,
  `engine/safe_orchestrator.py:2133`) → **fitil değil, kapanış**. Teyit zaten zone-içi engulfing
  **kapanışı** (`engine/smc_v2/confirmation.py`).
- Pozisyon koruması (SL/TP) borsa tarafında emir olarak durur; reconcile ayrıca çalışır — veri
  sıklığından bağımsız.
- Ölçüm (60 gün, 10 sembol, 3.044 chart-OB fitil dokunuşu): dokunuşların %35'inde o mum bölge içinde
  kapanıyor; %85'inde 48 mum içinde bölge içinde bir kapanış geliyor. Yani 15m örnekleme bölgeyi çoğunlukla
  **geciktiriyor**, ~%15'ini tamamen kaçırıyor.
- T-09 (#277): teyitsiz, bölge kenarından anlık/limit giriş (websocket'in mümkün kılacağı tür) bu veride
  NET olarak daha iyi değil (−0.04 … −0.75 R/işlem); motorun bugünkü akışı da NET −0.30 R.

## Beklenen çıktı (Definition of Done)
- [x] `collab/outputs/abacus/2026-11-05-data-fetch-cadence.md` (Türkçe, kendi cümlelerin):
  1. Bağımsız doğrulama: yukarıdaki dosya:satır iddiaları doğru mu? (farklıysa kanıtla)
  2. Websocket (kline / markPrice / bookTicker) ne kazandırır: bölge tespiti gecikmesi, kaçan %15,
     erken uyarı (#275), API weight; ne riske atar: repaint, kapanmamış barla karar, yeniden bağlanma,
     iki veri yolu tutarsızlığı.
  3. Net öneri: (a) değiştirme, (b) yalnız uyarı/izleme için websocket, (c) giriş mantığı için websocket
     — her biri için ölçüm planı (hangi metrik, hangi araç, karar eşiği).
- [x] Sonucu PR ile aç, PR'a `inbox:claude-code` etiketi + tek satır yorum koy → claude-code bir sonraki
      döngüsünde okur, gerekirse karşı ölçüm yapar ve cevabı aynı PR'a yazar.
- [x] `collab/log/abacus.md` girişi (`- VPS: N/A`).

## Kısıtlar
- Motor, exchange, config kodu değişmez. Canlı sisteme yazma yok. Websocket prototipi gerekiyorsa
  yalnız laptop'ta, repo dışında, salt-okuma (public stream) ve sonuçlarıyla birlikte raporlanır.

## Log
- 2026-11-05 claude-code: task açıldı (operatör isteği; gerçekler master `1e9ad91`'de doğrulandı).
- 2026-11-05 abacus: claim + rapor. İddiaların hepsi doğrulandı (ek bulgu: giriş market/taker). Öneri: (b) WS uyarı+event_scan hemen; (c) touch_entry yalnız shadow + ölçüm eşiği.

## Review
