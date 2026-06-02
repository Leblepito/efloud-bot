# Supabase/Postgres MCP + u2algo Waitlist Bağlantısı

Tarih: 2026-05-31
Güncelleme: 2026-05-31
Durum: Supabase Management API bağlantısı çalışıyor; repo migration'ları ve waitlist şeması `u2algo-efloud` içinde uygulanmış; Hermes MCP bağlantısı sağlıklı.

## Proje

- Supabase project: `u2algo-efloud`
- Project ref: `trytjrtqdpmeekgxhhdb`
- Local secret dosyası: `.env.supabase` (gitignored)
- Token/secret değerleri bu dokümana yazılmadı.

## Uygulanan bağlantılar

### 1. Supabase Management API helper

Repo içinde helper script'ler hazır:

- `scripts/supabase_mgmt.py`
  - `.env.supabase` içinden `SUPABASE_ACCESS_TOKEN` ve `SUPABASE_PROJECT_REF` okur.
  - `User-Agent: curl/8.0` header'ı kullanır; Supabase Management API `/database/query` endpoint'inde Cloudflare 1010 engelini önler.
  - Komutlar:
    - `python3 scripts/supabase_mgmt.py tables`
    - `python3 scripts/supabase_mgmt.py sql "select 1;"`
    - `python3 scripts/supabase_mgmt.py sqlfile path/to/file.sql`

- `scripts/supabase_apply.py`
  - `backend/migrations/*.sql` dosyalarını stem sırasıyla uygular.
  - `schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ)` kaydı tutar.
  - `u2algo-site/supabase/waitlist_leads.sql` dosyasını ayrıca uygular.
  - Komutlar:
    - `python3 scripts/supabase_apply.py --dry-run`
    - `python3 scripts/supabase_apply.py`

### 2. Hermes MCP server

Hermes local MCP server mevcut ve test başarılı:

- MCP server name: `supabase_postgres`
- Transport: stdio üzerinden local bash wrapper
- Test komutu:
  - `hermes mcp test supabase_postgres`
- Son doğrulama sonucu:
  - Connected: başarılı
  - Tools discovered: 7

Keşfedilen tool'lar:

- `health` — DB connectivity check
- `list_tables` — schema içindeki tabloları listeler
- `table_columns` — tablo kolonlarını gösterir
- `ensure_waitlist_leads` — `public.waitlist_leads` tablosunu create/repair eder
- `waitlist_count` — waitlist lead sayısı
- `waitlist_list` — son lead'leri email local-part redaction ile listeler
- `waitlist_insert` — açık kullanıcı talebiyle lead insert/upsert

Not: Bu MCP tool'ları yeni Hermes session/restart sonrası agent tool listesine `mcp_supabase_postgres_*` prefiksiyle düşer. Mevcut session içinde görünmüyorsa Hermes'i yeniden başlatmak yeterli.

## Supabase tablo durumu

Son doğrulama komutları:

```bash
python3 scripts/supabase_apply.py --dry-run
python3 scripts/supabase_mgmt.py tables
python3 scripts/supabase_mgmt.py sql "select version, applied_at from schema_migrations order by version;"
```

Migration durumu:

- Applied:
  - `001_init`
  - `002_trace_id`
  - `003_bar_ts`
  - `004_enable_rls`
  - `005_trade_audits`
  - `006_enable_trade_audits_rls`
  - `007_smc_v2_telemetry`
  - `008_tp2_nullable`
  - `009_trade_warehouse_extension`
- Pending: yok

Public tablolar:

- `audit_log`
- `equity_history`
- `schema_migrations`
- `trade_audits`
- `trades`
- `waitlist_leads`

Row count son durum:

| Table | Rows |
|---|---:|
| `audit_log` | 0 |
| `equity_history` | 0 |
| `schema_migrations` | 9 |
| `trade_audits` | 0 |
| `trades` | 0 |
| `waitlist_leads` | 1 |

RLS durumu:

- `audit_log`: enabled
- `equity_history`: enabled
- `schema_migrations`: enabled
- `trade_audits`: enabled
- `trades`: enabled
- `waitlist_leads`: enabled

## Beklenen boş tablolar

`trades`, `trade_audits`, `equity_history`, `audit_log` şu an boş. Bu normal olabilir:

- Bot production DB olarak bu Supabase projesine bağlandıktan sonra canlı trade/equity/audit kayıtları bu tablolara yazılır.
- Şu an sadece şema ve migration kayıtları doldurulmuş durumda.
- Dummy trade/audit seed'i uygulanmadı; production analytics'i kirletmemek için gerçek trading tablolarına test verisi yazılmadı.

## Güvenlik notları

- Paylaşılan Supabase personal access token repo'ya yazılmadı.
- `.env.supabase` `.gitignore` içinde.
- Secret değerleri terminal çıktısında ve dokümanda gösterilmedi.
- İş bitince Supabase Access Token rotate edilmesi önerilir.

## Operasyon notları

- Management API token ops/admin credential'dır; runtime app secret olarak kullanılmamalı.
- Runtime için ayrı `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` veya anon key/service role ayrımı yapılmalı.
- Compose/env değişimi production'da `docker compose up -d` ile recreate gerektirir; `docker restart` yeterli değildir.
- Canlı deploy/config/mainnet işleri Utku operatör alanıdır.
