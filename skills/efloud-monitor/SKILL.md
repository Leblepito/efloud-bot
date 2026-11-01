---
name: efloud-monitor
description: Efloud-bot sağlık, breaker ve günlüklerini salt okunur izle.
---

# Efloud izleme

## Adımlar
1. SSH ile salt okunur container durumu ve `docker logs efloud-bot --since 1h` incele. Raw loglar sır içerebileceğinden önce yerinde filtreleyip yalnız olay türü, sayım ve güvenli zaman bilgilerini çıkar; ham hata, token ve config değerlerini raporlama.
2. `Traceback`, `HALT`, `SLTooFar` ve v2 emit/aday olaylarını ayrı ayrı say; gerçek log terimlerini `engine/safe_orchestrator.py` ve `tools/v2_doctor.py` içinde doğrula. Sıfır eşleşme yokluk kanıtı değildir: zaman aralığı ve log seviyesi önemli.
3. Container içinden `http://localhost:8080/healthz` sorgula. HTTP kodunu ve JSON `status`/`failures` alanlarını kaydet; `200/suspended` = trading askıda, `200/ok` = sağlıklı, 503 = unhealthy. Startup sırasında ilk 30 saniyede 503 olabilir.
4. `/app/state_1k/breaker.json` StateStore zarfından `data.state`, güvenli `reason` ve `consecutive_losses` alanlarını çıkar. Dosya eksik/bozuksa sonuç bilinmiyor; OPEN varsayma. Bakiye ve secret olabilecek alanları dökme.

## Doğrulama
Sağlık cevabı, breaker durumu, incelenen UTC pencere ve her filtre sayısı görev dosyasında olsun. Eksik erişimi `doğrulanmadı` diye işaretle. Üretim durumunu değiştirme; HALT veya korumasız pozisyon olasılığını kullanıcıya hemen bildir.
