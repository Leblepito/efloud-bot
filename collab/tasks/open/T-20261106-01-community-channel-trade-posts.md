---
id: T-20261106-01
title: Topluluk Telegram kanalına bot işlem paylaşımlarını canlıda aç (EFLOUD_CUSTOMER_TG_TRADES)
from: claude-code
to: hermes
status: open
claimed_by: null
reviewer: claude-code
parent: null
created: 2026-11-06
touches_live: true
---

## Amaç
Bot'un gerçek işlemleri (açılış, TP1, kapanış) topluluk Telegram kanalına müşteri-güvenli formatta düşsün. Kod `feat/community-trade-notify` PR'ında, varsayılan KAPALI; canlıda açmak env + container recreate ister. Bu kanal pazarlama ve sosyal medya (Instagram/X) içeriğinin kaynağı olacak.

## Girdi
- PR: `feat/community-trade-notify` (engine/notifications/telegram_notifier.py `post_trade_*`, backend/bot_runner.py dispatch)
- Doc: `docs/telegram/community-channel.md`
- Env (VPS'teki prod env dosyası, docker compose'un okuduğu): `EFLOUD_CUSTOMER_TG_TOKEN`, `EFLOUD_CUSTOMER_TG_CHANNEL_ID`, `EFLOUD_CUSTOMER_TG_TRADES=1`
- Topluluk kanalı: operatörün daha önce açtığı kanal; bot'u (@BotFather botu) kanala **admin** olarak eklemek gerekir.

## Beklenen çıktı (Definition of Done)
- [ ] Operatör/hukuki onay: gerçek zamanlı entry/SL/TP paylaşımı P-003 §2b 'sinyal servisi' sınırı — kanal herkese açıksa onay olmadan `EFLOUD_CUSTOMER_TG_TRADES=1` yapılmaz.
- [ ] PR merge edildikten sonra VPS kodu master'a çekildi (operatör onayıyla).
- [ ] Üç env değişkeni prod env dosyasında (`.env.production`, `docker-compose.prod.yml` `efloud-bot` servisinin `env_file`'ı) set (değerler repo'ya/log'a yazılmaz). `EFLOUD_CUSTOMER_TG_PARSE_MODE` ayarlanmaz (Markdown kalır).
- [ ] Bot container'ı **flat (açık pozisyon yokken)** pencerede recreate edildi: `docker compose -f docker-compose.prod.yml up -d --force-recreate --no-deps efloud-bot`; `EFLOUD_AUTOSTART=0` olduğu için bot manuel start edildi; `/healthz` 200.
- [ ] Açılış logunda `Customer Telegram per-trade posts: ENABLED` satırı var (`digest disabled (flag off)` normal).
- [ ] İlk gerçek işlem açılışında topluluk kanalında mesaj göründü (ekran görüntüsü `collab/outputs/hermes/` altına, kişisel veri yok).
- [ ] Ops kanalı (EFLOUD_TELEGRAM_*) davranışı değişmedi.
- [ ] `collab/log/hermes.md`'ye tek satır kayıt.

## Kısıtlar
- `touches_live: true` → operatör onayı olmadan recreate/restart YOK. Açık pozisyon varken restart YOK.
- Token/chat id değerlerini hiçbir dosyaya, PR'a, log'a yazma.
- Trading config (`configs/config.phase2_1k.yaml`) değişmez.
- Sorun olursa geri alma: `EFLOUD_CUSTOMER_TG_TRADES=0` + recreate.

## Log
- 2026-11-06 claude-code: kod hazır (default OFF, testler yeşil), canlı açma Hermes + operatöre devredildi.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
