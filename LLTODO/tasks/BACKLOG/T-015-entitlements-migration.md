# T-015: Supabase Entitlements Tablosu + RLS

**Epic:** P-002
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 0.5 gün
**Bağımlılık:** T-010 (legal pack), Hermes GÖREV A (DDL taslağı)

## Hedef

Satın alma → erişim hakkı kaydını tutan `entitlements` tablosunu migration olarak eklemek.

## Çıktılar

- [ ] `u2algo-site/supabase/` altına migration: `entitlements(id, email, product, status, source, tv_username, order_ref, granted_at, created_at)`
- [ ] RLS: yalnız service-role yazabilir/okuyabilir
- [ ] Hermes `supabase_postgres` MCP ile canlıda uygulama (operatör onayıyla)

## Acceptance Kriterleri

- [ ] status enum'u: `pending | granted | revoked`
- [ ] Migration idempotent (`IF NOT EXISTS`)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-002 W2 — UR-002 bekleniyor |
