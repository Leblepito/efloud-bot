# T-018: Müşteri Telegram Kanal Bildirimi (default-OFF)

**Epic:** P-003
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 1-2 gün
**Bağımlılık:** T-016 (müşteri kohortu), efloud-risk-ops-reviewer onayı

## Hedef

u2algo Telegram kanalına gecikmeli/aggregate bildirim gönderen, `NullNotificationManager` ile aynı duck-type arayüzlü opt-in notifier eklemek. Trade karar yoluna SIFIR temas.

## Çıktılar

- [ ] `engine/notifications/telegram_notifier.py` (NullNotificationManager arayüzü)
- [ ] `config.yaml` `notifications:` bloğu — **default OFF** (canlı config bu PR'da DEĞİŞMEZ; yalnız şema + örnek)
- [ ] Bildirim içeriği: kapanmış/teyitli olayların gecikmeli özeti — gerçek zamanlı sinyal YOK ("sinyal servisi" regülasyon çerçevesi riski)
- [ ] Regression test: flag kapalıyken davranış birebir mevcut (G-P3-3)

## Acceptance Kriterleri

- [ ] SafeOrchestrator'dan tek yönlü okuma; geri besleme yolu yok
- [ ] Flag OFF iken hiçbir dış çağrı yapılmaz
- [ ] risk-safety-auditor / efloud-risk-ops-reviewer review'ı zorunlu

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W3 — UR-003 bekleniyor |
