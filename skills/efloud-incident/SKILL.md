---
name: efloud-incident
description: Efloud-bot durma, HALT ve ardışık kayıp olaylarını güvenle incele.
---

# Efloud olay müdahalesi

## Adımlar
1. Bot durmuşsa container durumu, `/healthz` JSON status/failures, breaker `data.state`/reason ve güvenli log olay sayımlarını salt okunur incele. `200/suspended` sağlıklı trading demek değildir. Durumu ve zamanı kaydet.
2. `/app/state_1k/positions.json` içindeki açık kayıtları ve borsadaki pozisyon/SL/TP emirlerini bağımsız kontrol et. Eksik veri veya uyuşmazlığı açıkça bildir. Korumasız pozisyon ya da HALT halinde kullanıcıya hemen haber ver; emir/pozisyonlara kendiliğinden müdahale etme.
3. HALT ise `docs/runbooks/breaker-reset.md` uyarınca nedeni ve devam edip etmediğini araştır. Haftalık zarar/ardışık kayıp güvenlik durağıdır; restart ile bypass etmeye çalışma. Reset kararı ayrı insan onayıdır; önce açık pozisyon kontrolünü tekrarla ve görev dosyasına yaz.
4. Ardışık kayıp/stop için son yedi günü `efloud-journal-analysis` ile incele; journal tahmini PnL'yi borsa net sonucu sanma. Kök neden bir kod hatası ise bulguyu `Claude'a devir` notuyla yaz, bot kodunu değiştirme.
5. Deploy, restart, config değişikliği veya reset öncesi güncel pozisyon kontrolü ve Telegram üzerinden açık üretim onayı zorunludur. Açık pozisyon varken görev açıkça izin vermiyorsa dur ve ayrıca kullanıcı onayı iste. `emergency_balance_threshold=0` değerini değiştirme.

## Doğrulama
Her görevde secret'sız komutlar, kısaltılmış kanıt, commit hash, healthz cevabı ve bağımsız doğrulanamayan noktalar yer alsın. Aynı komut iki kez başarısızsa üçüncü denemeyi yapma; blocked ve nedenini kaydet. Ayrıntı: `docs/runbooks/on-call-playbook.md`, `breaker-reset.md`, `crash-loop-recovery.md`.
