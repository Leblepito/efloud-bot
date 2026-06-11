# T-017: TradingView Erişim Grant Runbook + Kuyruk Görünümü

**Epic:** P-002
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 0.5 gün
**Bağımlılık:** T-016

## Hedef

Entitlement kuyruğundan TradingView invite-only erişimi manuel verme sürecini runbook'laştırmak (TV'nin resmi otomasyon API'si yok — tam otomasyon W4+).

## Çıktılar

- [ ] `docs/runbooks/tv-access-grant.md`: pending entitlement listesi → TV UI "Manage access" adımları → `status=granted` + `granted_at` güncelleme
- [ ] Kuyruk görünümü: pending entitlement'ları listeleyen basit sorgu/script (Hermes MCP `waitlist_list` kalıbı)
- [ ] SLA notu: satın alma → erişim hedefi ≤ 24h

## Acceptance Kriterleri

- [ ] Runbook'ta revoke (iade durumu) akışı da tanımlı
- [ ] Tam otomasyon W4+ araştırma maddesi olarak işaretli

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-002 W2 — UR-002 bekleniyor |
