# Supabase/Postgres MCP + u2algo Waitlist Bağlantısı

Tarih: 2026-05-31
Durum: MCP kuruldu; direct Supabase host bağlantısı IPv6-only/ENETUNREACH nedeniyle canlı DB erişimi bloklu.

## Yapılanlar

1. Hermes local MCP server oluşturuldu:
   - `C:/Users/utkuc/AppData/Local/hermes/mcp-servers/supabase_postgres/supabase_postgres_mcp.py`
   - `C:/Users/utkuc/AppData/Local/hermes/mcp-servers/supabase_postgres/run_supabase_postgres_mcp.sh`

2. Hermes config'e MCP eklendi:
   - server name: `supabase_postgres`
   - tools discovered: 7

3. Secret local Hermes env'e eklendi:
   - key: `SUPABASE_DATABASE_URL`
   - değer bu belgeye yazılmadı.

4. MCP smoke:
   - `hermes mcp test supabase_postgres` başarılı.
   - 7 tool listelendi:
     - `health`
     - `list_tables`
     - `table_columns`
     - `ensure_waitlist_leads`
     - `waitlist_count`
     - `waitlist_list`
     - `waitlist_insert`

5. u2algo-site backend güncellendi:
   - `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` varsa Supabase REST ile yazar.
   - `SUPABASE_DATABASE_URL` veya `DATABASE_URL` varsa doğrudan PostgreSQL ile yazar.
   - DB erişilemezse local JSONL fallback ile public form 200 döner.
   - `ensureWaitlistTable()` PostgreSQL bağlantısı varsa `public.waitlist_leads` migration'ını otomatik uygular.

6. Railway variable eklendi:
   - service: `u2algo-site`
   - key: `DATABASE_URL`
   - değer stdin üzerinden verildi, log'a yazılmadı.

## Canlı doğrulama

Railway deployment:
- service: `u2algo-site`
- latest deployment: `09000f5b-c5f1-4b6c-945f-dd93be34698e`
- status: SUCCESS

Endpointler:
- `/healthz` -> 200
- `/api/waitlist/health` -> 200 ama database unhealthy, backend postgres, error ENETUNREACH
- `POST /api/waitlist` -> 200, backend local-jsonl-fallback

## Blokaj

Verilen direct Supabase host DNS'te IPv6-only döndü. Local Windows ve Railway runtime IPv6 route ile Postgres'e erişemedi.

Görülen hata tipi:
- local MCP: host resolve / IPv6 unreachable
- Railway: `ENETUNREACH` IPv6 address port 5432

Bu, uygulama kodu veya MCP discovery problemi değil; Supabase direct database host'un IPv6-only olması veya kullanılabilir IPv4 pooler DSN'in eksik olmasıyla ilgili.

## Çözüm seçenekleri

En iyi çözüm: Supabase Dashboard > Project Settings > Database > Connection string ekranından IPv4 uyumlu pooler connection string alınmalı.

Genelde gerekli bilgi:
- Transaction/session pooler host
- Region-specific pooler hostname
- User formatı (`postgres.<project-ref>` veya dashboard'un verdiği user)
- Port (`6543` veya dashboard'un verdiği port)
- `sslmode=require`

Bu doğru pooler DSN geldikten sonra:
1. Hermes local `.env` içinde `SUPABASE_DATABASE_URL` güncellenir.
2. Railway `u2algo-site` service variable `DATABASE_URL` güncellenir.
3. `hermes mcp test supabase_postgres` + `health` çalıştırılır.
4. `/api/waitlist/health` backend `postgres`, database `ready` olmalı.
5. `POST /api/waitlist` backend `postgres` dönmeli.

## Güvenlik Notları

- Secret değerleri repo'ya yazılmadı.
- Connection string bu belgeye eklenmedi.
- MCP server sadece Hermes local config altında kuruldu.
- Public u2algo-site formu DB kesintisinde 500 döndürmeyecek şekilde fallback korumalı.
- Trading/Binance/Hetzner canlı execution secret'larına dokunulmadı.
