# backend/migrations — numaralandırma ve uygulama kuralları

Bu dizin **tek doğru migration kaynağıdır**. Kök `migrations/` dizini 2026-11-03'te
kaldırıldı (ölü kopyaydı: hiçbir runner onu okumuyordu).

## Nasıl uygulanır

```bash
docker exec efloud-bot python3 -m backend.migrate up      # VPS
python -m backend.migrate up                              # lokal (DATABASE_URL gerekir)
python -m backend.migrate status
```

Uygulama mantığı (`backend/migrate.py`):

- Sıra: **dosya adına göre alfabetik** (`sorted(glob("*.sql"))`).
- `version` = dosya adının uzantısız hâli (ör. `009_content_drafts`).
- Uygulananlar `schema_migrations(version TEXT PK, applied_at TIMESTAMPTZ)` tablosuna yazılır.
- İçerik hash'i **tutulmaz** → yalnız `version` önemlidir.

## Kurallar

1. **Numara = sıra.** Yeni migration bir sonraki boş numarayı alır (şu an `016_`).
2. **Uygulanmış bir dosyayı YENİDEN NUMARALANDIRMA veya ADLANDIRMA.** `version`
   kaydı ada bağlı; yeniden adlandırmak aynı migration'ı ikinci kez uygulatır
   (canlı DB riski).
3. **Uygulanmış dosyanın SQL'ini değiştirme.** Yeniden çalıştırılmaz, yani değişiklik
   hiçbir yere gitmez — yeni bir migration yaz. (Yalnız yorum düzeltmesi kabul edilir;
   hash tutulmadığı için teknik olarak güvenlidir, ama gereksizdir.)
4. **Idempotent yaz:** `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` /
   `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Yeni tablolar için RLS politikası ekle
   (bkz. `004_enable_rls.sql`, `006_enable_trade_audits_rls.sql`).
5. Süpabase Management API ile uygulama gerekiyorsa `scripts/supabase_apply.py`
   aynı semantiği (`version` = stem, alfabetik) izler.

## Bilinen tuzak: iki adet `009_*`

Aynı numarayı iki dosya taşıyor:

| Dosya | İçerik | Neden aynı numara |
|---|---|---|
| `009_content_drafts.sql` | Content Approval Queue (P-002 M6) | kendi serisinde 009 |
| `009_trade_warehouse_extension.sql` | `trades` tablosuna telemetry/excursion kolonları (Phase 3.2) | paralel geliştirilen başka bir iş kolu |

Alfabetik sırada `009_content_drafts` önce uygulanır. İkisi de `IF NOT EXISTS`
kullandığı ve farklı tablolara dokundukları için sıra farkı bugüne kadar sorun
üretmedi — ama bu **isimlendirme hatası canlıda düzeltilmemelidir** (kural 2).
Yeni dosyalarda aynı desene düşmemek için: bir migration yazmadan önce
`ls backend/migrations/` ile en yüksek numarayı teyit et.
