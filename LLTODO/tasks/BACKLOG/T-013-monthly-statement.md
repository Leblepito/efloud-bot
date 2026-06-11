# T-013: Aylık Statement (monthly.py + /api/reports/monthly)

**Epic:** P-003
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 1-2 gün
**Bağımlılık:** — (UR-003 onayı sonrası başlar)

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

## UR-003 Düzeltmesi (2026-06-11)

**Veri kaynağı pinlendi:** `compute_summary` DB-row anahtarları bekler (`pnl_usdt/opened_at/closed_at`),
journal ise `realized_pnl/entry_timestamp/exit_timestamp` taşır → **adapter gerekli**. Prod DB-LESS
olduğundan monthly.py journal'dan okumalı (`backend/api.py read_journal_history` emsali);
equity_start/end alanları DB yokken None döner — statement şablonu bunu açıkça göstermeli.
Ek netleştirme: bu endpoint operatör-only İÇ tüketimdir; müşteri-yüzlü yayın T-012/T-014
üzerinden (operatör onaylı statik) yapılır.

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W1 — UR-003 bekleniyor |
