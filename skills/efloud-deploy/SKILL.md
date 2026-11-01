---
name: efloud-deploy
description: Efloud-bot canlı deploy işlemini onay ve sağlık kontrolleriyle yürüt.
---

# Efloud deploy

## Adımlar
1. Deploy canlı sistemi etkiler. Görev kapsamını, hedef commit'i ve kullanıcıdan Telegram üzerinden açık üretim onayını doğrula. Bu skill tek başına onay değildir.
2. Önce VPS'te `/app/state_1k/positions.json` dosyasını salt okunur incele: StateStore zarfında `data` listesindeki kayıtlar `closed_at` ile açık/kapalı ayrılır; `entries` ve `exits` büyüklükleriyle de tutarlılığı kontrol et. Eksik/bozuk/durum belirsizse sıfır varsayma. Borsa açık pozisyonlarını da bağımsız doğrula. Sonucu görev dosyasına yaz. Açık pozisyon varsa görev açıkça izin vermedikçe dur ve kullanıcıdan ayrıca onay iste.
3. Lokal, GitHub master ve VPS HEAD'i karşılaştır; VPS çalışma ağacı ve hedefin fast-forward olduğunu doğrula. Yerel değişiklikleri ezme. Hedefi ve açık pozisyon kontrolünü kaydet.
4. Yalnız onaydan sonra `ssh root@2.28.139.82 "cd /opt/efloud-bot && git pull -q --ff-only && bash deploy/deploy.sh"` uygula. Başarısızsa ikinci aynı hatadan sonra üçüncü kez deneme, blocked yaz.
5. Deploy sonrası bot suspended kalabilir; üretim başlatma da onay gerektirir. Dashboard oturumunu güvenli istemcide aç: parolayı yalnız sunucu dosyasından veya container ortamından süreç içinde oku; komut satırına, loga veya görev dosyasına koyma. `POST /api/login`, sonra çerezi bellek içinde taşıyarak `POST /api/bot/start` yap. Kimlik bilgilerini URL/argv'ye yazma; TLS doğrulamasını kapatma.
6. Reset otomatik değildir: HALTED ise nedeni incele, açık pozisyonları yeniden kontrol edip kaydet ve kullanıcıdan ayrıca Telegram onayı al. Bot çalışırken onaylı nedenle `POST /api/breaker/reset` çağır; tekrarlayan trip'te yeniden resetleme.

## Doğrulama
- Container içinden `http://localhost:8080/healthz`: HTTP ve JSON `status`/`failures` alanlarını kontrol et. HTTP 200 tek başına yeterli değil: `suspended` trading'in aktif olduğunu göstermez. İlk 30 saniyede 503 olursa bekleyip yeniden dene.
- `/app/state_1k/breaker.json` içindeki `data.state` değerini oku: OPEN olmalı. Borsa pozisyonları ve koruyucu emirleri ayrıca doğrula.
- Hedef ve VPS commit'i, pozisyon özeti, komutlar, güvenli çıktı, healthz ve breaker sonucunu görev dosyasına yaz. Doğrulanamayanı açıkça işaretle. Sır ve kişisel verileri yazdırma.
