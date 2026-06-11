# T-013: Aylık Statement (monthly.py + /api/reports/monthly)

**Epic:** P-003
**Claimed by:** @claude (2026-06-11)
**Tahmini süre:** 1-2 gün
**Bağımlılık:** — (UR-003 onayı sonrası başlar)

## Hedef

Mevcut daily-report altyapısını yeniden kullanarak aylık performans statement'ı (CSV + markdown) üretmek.

## Çıktılar

- [x] `ops/daily_report/monthly.py` — `aggregate.compute_summary()` yeniden kullanımı, 30 günlük pencere (clamp 1..92)
- [x] CSV + markdown çıktı (`reports/monthly/statement_YYYY-MM.{md,csv}`)
- [x] `backend/api.py` auth'lu `/api/reports/monthly` endpoint'i (mevcut router + `require_auth` kalıbı)
- [x] pytest: aggregate doğruluğu + endpoint smoke (15 test)

## Acceptance Kriterleri

- [x] `aggregate.compute_summary()` değiştirilmez, yalnız çağrılır (diff'te aggregate.py yok)
- [x] Endpoint auth'suz 401 döner (test)
- [x] Mevcut daily report davranışı değişmez (report/render dokunulmadı; komşu testler yeşil)

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
| 2026-06-11 | DONE ✅ | PR #191: monthly.py (journal-first adapter, UR-003 pini: DB-less equity "n/a" + equity_note, operatör-only İÇ endpoint) + /api/reports/monthly + 15 test. Review: api-integration APPROVE + efloud-code-reviewer APPROVE_WITH_NITS (nit'ler düzeltildi: parsed-ts sort + 3 test boşluğu). @claude |
