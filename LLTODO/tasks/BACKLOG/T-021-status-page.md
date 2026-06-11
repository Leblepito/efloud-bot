# T-021: Public Status Page + External Uptime Monitor

**Epic:** P-003
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 1 gün
**Bağımlılık:** T-024 (healthz kontratı), T-014 (uptime alanı), GÖREV E (sağlayıcı seçimi — Hermes/operatör)

## Hedef

Müşterilerin servis durumunu kendi kendine kontrol edebileceği public status page + harici uptime monitörü kurmak. Bugün müşteri dashboard'a login olmadan servisin ayakta olup olmadığını göremez.

## Çıktılar

- [ ] Harici uptime monitör (UptimeRobot/BetterStack — GÖREV E kararı) `/healthz` probe'u
- [ ] **Probe healthz JSON `status` alanını parse ETMELİ** — HTTP 200 + `status:"suspended"` = trading durdu ama servis ayakta (`suspended` ≠ up olarak raporlanmalı; T-024 kontratı)
- [ ] Public status sayfası (sağlayıcının hosted page'i veya u2algo-site `/status`)
- [ ] Incident log alanı (geriye dönük, insan yazımı)

## Acceptance Kriterleri

- [ ] Breaker HALT senaryosunda status page "degraded/suspended" gösterir, "operational" DEĞİL
- [ ] Public görünürlük kapsamı operatör onaylı (G-P3-B4 ile aynı paket)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W-R — T-024 + GÖREV E sonrası |
