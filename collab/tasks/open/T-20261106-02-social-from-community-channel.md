---
id: T-20261106-02
title: Topluluk kanalındaki işlemlerden Instagram + X paylaşım akışı (onaylı, varsayılan kapalı)
from: claude-code
to: abacus
status: open
claimed_by: null
reviewer: claude-code
parent: T-20261106-01
created: 2026-11-06
touches_live: false
---

## Amaç
Operatör, Telegram topluluk kanalına düşen işlemleri (bot işlemleri + u2algo Price Action indicator sinyalleri) Instagram ve X'te paylaşmak istiyor. Repoda hazır bir sosyal hat var (Lane A→G: journal → caption → chart PNG/MP4 → platform bundle → onaylı publish). Bu görev o hattı bu kaynağa bağlayıp tek komutla "taslak üret → operatör onayı → paylaş" akışını çalışır hale getirmek.

## Girdi
- `skills/social-publishing/SKILL.md` (hat dokümanı), `scripts/daily_social_run.py`, `scripts/lane_g_social.py`, `scripts/lane_g_publish.py`, `scripts/chart_render.py`
- Kaynak seçenekleri (birini seç, gerekçeyi yaz):
  1. Bot journal (Lane A JSONL, `engine/content_jobs.py`) — en güvenilir; bot işlemleriyle birebir.
  2. Telegram topluluk kanalı mesajları (bot hesabıyla `getUpdates`/kanal geçmişi) — indicator sinyallerini de kapsar.
- Mesaj formatları: `docs/telegram/community-channel.md` (bot) ve `docs/telegram/tradingview-to-telegram.md` (indicator).

## Beklenen çıktı (Definition of Done)
- [ ] `docs/social/telegram-to-social.md`: seçilen kaynak, akış şeması, operatör komutları (dry-run, onay, live).
- [ ] Gerekirse küçük bir adaptör (ör. `scripts/social_from_telegram.py`) + testler; mevcut Lane B–G arayüzleri değişmez.
- [ ] Dry-run çıktısı: 3 örnek işlem için IG (1080x1350) ve X görseli + caption, `collab/outputs/abacus/` altında (her dosya < 150 KB).
- [ ] Caption'larda uyum kuralları korunur (`content_compliance.find_violations`), "yatırım tavsiyesi değildir" ifadesi var, kesin getiri vaadi yok.
- [ ] PR açıldı, `inbox:claude-code` etiketiyle review istendi.

## Kısıtlar
- Canlı paylaşım YOK: `--live`, `--auto-approve` ve `X_API_ENABLED`/`INSTAGRAM_ENABLED` yalnız operatör açar.
- API anahtarları repo'ya girmez; repo PUBLIC.
- TradingView script açıklamasına veya grafiğine Telegram/sosyal link konmaz (TradingView House Rules).

## Log
- 2026-11-06 claude-code: görev açıldı.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
