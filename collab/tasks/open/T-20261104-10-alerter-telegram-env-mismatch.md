---
id: T-20261104-10
title: "İstek: prod alerter Telegram'a hiç mesaj göndermiyor — env adı uyuşmazlığı"
from: claude-code
to: operator
status: open
claimed_by: null
reviewer: null
parent: T-20261104-08
created: 2026-11-04
touches_live: true
---

## Amaç
`efloud-alerter` (breaker / trade açıldı-kapandı / healthz uyarıları) 2026-11-04 14:35 UTC açılışında
"EFLOUD_TELEGRAM_TOKEN or EFLOUD_TELEGRAM_CHAT_ID not set — dry-run mode" yazdı; saatlik istatistikte
`fired=0`. Kod `EFLOUD_TELEGRAM_TOKEN` + `EFLOUD_TELEGRAM_CHAT_ID` okuyor (`ops/alerter/alerter.py`,
`.env.example`), container ortamında ise yalnız `EFLOUD_TELEGRAM_BOT_TOKEN` var ve chat id yok.
Repo'da `EFLOUD_TELEGRAM_BOT_TOKEN` okuyan kod yok. Sonuç: operatöre hiçbir otomatik uyarı ulaşmıyor;
T-20261104-08 (LuxAlgo bölge uyarısı) da bu düzelmeden ulaşmaz.

## Girdi
- `docker logs efloud-alerter` (2026-11-04 14:35–18:35 UTC), `docker exec … env` (yalnız değişken ADLARI okundu).

## Beklenen çıktı (Definition of Done)
- [ ] Operatör `.env.production`'a `EFLOUD_TELEGRAM_TOKEN` (mevcut bot token değeri) ve
      `EFLOUD_TELEGRAM_CHAT_ID` ekler; alerter'ı yeniden oluşturur.
- [ ] Doğrulama: `docker logs efloud-alerter` açılışta "dry-run" uyarısı YOK.
- [ ] (T-08 merge + deploy sonrası, istenirse) `EFLOUD_ALERTER_LUX_ALERTS=1`.

## Kısıtlar
- Secret değeri hiçbir dosyaya/sohbete yazılmaz. Canlı değişiklik → operatör.

## Log
- 2026-11-04 claude-code: task açıldı (T-08 çalışması sırasında bulundu).

## Review
