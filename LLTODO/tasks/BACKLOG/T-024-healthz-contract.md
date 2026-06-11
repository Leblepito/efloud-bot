# T-024: Healthz Kontrat Dokümanı + Uptime Metriği

**Epic:** P-003
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 0.5 gün
**Bağımlılık:** —

## Hedef

`/healthz`'nin mevcut (tasarım gereği doğru) semantiğini harici monitörler için kontrata bağlamak: **HTTP 200 + `status:"suspended"` = breaker HALT, servis ayakta** (autoheal restart-loop'unu önler — `backend/healthz.py:4-9` docstring'i). Harici monitör yalnız HTTP koduna bakarsa trading durmuşken "operational" gösterir — T-021'in probe kontratı buradan beslenir.

## Çıktılar

- [ ] `docs/runbooks/healthz-contract.md` — durum matrisi: 200/ok, 200/suspended, 503/transient; her birinin monitör yorumu
- [ ] Uptime metriği yüzeyi — **UR-003 düzeltmesi:** heartbeat tek-timestamp'tir ve alerter'ın
      canlılığını ölçer (bot down + alerter up → heartbeat taze) → uptime % İÇİN KULLANILMAZ.
      Tasarım: healthz-türevi sampling (T-014 ile ortak pinlenir); `status:"suspended"` ayrı
      kategori olarak raporlanır ("servis up / trading suspended")
- [ ] Kod değişikliği YOK veya minimum (yalnız metrik yüzeyi; healthz semantiği DEĞİŞMEZ)

## Acceptance Kriterleri

- [ ] T-021 probe konfigürasyonu bu kontrat dokümanına referans verir
- [ ] healthz davranış değişikliği yok (mevcut autoheal/alerter regresyonsuz)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W-R — T-014/T-021 besleyici |
