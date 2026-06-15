# T-018: Müşteri Telegram Kanal Bildirimi (default-OFF)

**Epic:** P-003
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 1-2 gün
**Bağımlılık:** T-016 (müşteri kohortu), efloud-risk-ops-reviewer onayı

## Hedef

u2algo Telegram kanalına gecikmeli/aggregate bildirim gönderen, `NullNotificationManager` ile aynı duck-type arayüzlü opt-in notifier eklemek. Trade karar yoluna SIFIR temas.

## UR-003 Düzeltmesi (2026-06-11) — Composition kararı ZORUNLU

⚠️ Gap-analizi G4'teki "engine/notifications/ içinde tek implementasyon null_manager.py" iddiası
**YANLIŞ**: `engine/notifications/__init__.py`'de gerçek `NotificationManager` var ve canlıda
`main.py` → SafeOrchestrator `notification_mgr` seam'ine bağlı (channels=['terminal','log'] +
content_emitter; ~8 çağrı noktası). telegram_notifier'ı bu seam'e DOĞRUDAN takmak operatör
bildirimlerini YERİNDEN EDER. Tasarım: mevcut NotificationManager'a 'telegram' **channel** olarak
eklenmeli (sınıf zaten bu genişleme için tasarlanmış) veya composite/fan-out sarmalayıcı.
G-P3-3 regression testi "flag ON iken operatör terminal/log bildirimleri KAYBOLMAZ" senaryosunu
da kapsamalı. Ek nicelik: "gecikmeli" = olay kapanışından ≥1 saat VEYA yalnız günlük özet
(implementasyonda biri pinlenir, regülasyon guard'ı test edilebilir olur).

## Tasarım Kararı (2026-06-15 @claude)

UR-003 notundaki iki seçenekten ("≥1 saat gecikme" VEYA "günlük özet") **günlük aggregate
özet** PİNLENDİ — en güvenli regülasyon guard'ı: müşteri kanalına yalnız KAPANMIŞ trade'lerin
toplulaştırılmış günlük özeti (sayı/kazanma-oranı/toplam getiri) gider; per-trade entry/SL/TP/symbol
ASLA. Bu nedenle notifier trading-loop'tan tamamen DECOUPLED — NotificationManager seam'ine
DOKUNULMADI (operatör terminal/log bildirimleri yapısal olarak değişmez → G-P3-3 trivially sağlanır).
Müşteri kanalı operatör alerter'ından AYRI kimlik kullanır (`EFLOUD_CUSTOMER_TG_*` ≠ `EFLOUD_TELEGRAM_*`).

## Çıktılar

- [x] `engine/notifications/telegram_notifier.py` — `CustomerChannelNotifier` + `build_daily_digest`
- [x] `config.yaml` `notifications:` bloğu — **default OFF** (canlı config DEĞİŞMEDİ; yalnız şema + örnek)
- [x] Bildirim içeriği: kapanmış olayların gecikmeli **aggregate** özeti — gerçek zamanlı sinyal YOK; per-trade alan sızıntısı testle engellendi
- [x] Regression test: flag kapalıyken hiçbir dış çağrı yok + NotificationManager telegram-free (G-P3-3)

## Acceptance Kriterleri

- [x] Tek yönlü; geri besleme yolu yok (trading-loop'tan decoupled, ayrı günlük digest)
- [x] Flag OFF (veya creds eksik) iken hiçbir dış çağrı yapılmaz — double-gate testli (12 test)
- [ ] risk-safety-auditor / efloud-risk-ops-reviewer review'ı zorunlu — PR'da bekliyor
- [ ] Canlı aktivasyon T-016 (müşteri kohortu) + operatör/legal sign-off arkasında (BACKLOG'da kalır)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W3 — UR-003 bekleniyor |
| 2026-06-15 | IMPLEMENTED (BACKLOG'da) | `feat/t018-customer-telegram-notifier` — kod+config+12 test yeşil. IN_PROGRESS'e taşınmadı (R2: @claude'da T-020 aktif; tek-task/agent). Canlı aktivasyon T-016 + risk-ops + operatör sign-off arkasında — bu yüzden DONE değil. |
