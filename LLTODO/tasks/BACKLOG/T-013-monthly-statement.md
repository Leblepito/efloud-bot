# T-013: Aylık Statement (monthly.py + /api/reports/monthly)

**Epic:** P-002
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 1-2 gün
**Bağımlılık:** — (UR-002 onayı sonrası başlar)

## Hedef

Mevcut daily-report altyapısını yeniden kullanarak aylık performans statement'ı (CSV + markdown) üretmek.

## Çıktılar

- [ ] `ops/daily_report/monthly.py` — `aggregate.compute_summary()` yeniden kullanımı, 30 günlük pencere
- [ ] CSV + markdown çıktı (`reports/` altına)
- [ ] `backend/api.py` auth'lu `/api/reports/monthly` endpoint'i (mevcut router + `require_auth` kalıbı)
- [ ] pytest: aggregate doğruluğu + endpoint smoke

## Acceptance Kriterleri

- [ ] `aggregate.compute_summary()` değiştirilmez, yalnız çağrılır
- [ ] Endpoint auth'suz 401 döner
- [ ] Mevcut daily report davranışı değişmez

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-002 W1 — UR-002 bekleniyor |
