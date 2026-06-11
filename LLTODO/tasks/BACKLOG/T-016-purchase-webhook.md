# T-016: Lemon Squeezy Purchase Webhook (HMAC) + Onay E-postası

**Epic:** P-002
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 1-2 gün
**Bağımlılık:** T-015, Hermes GÖREV B (Railway env)

## Hedef

Lemon Squeezy satın alma webhook'unu imza doğrulamalı şekilde alıp entitlement kaydı + onay e-postası üretmek.

## Çıktılar

- [ ] `u2algo-site/server.js` → `POST /api/purchase-webhook` (X-Signature HMAC-SHA256 doğrulaması, secret env'den)
- [ ] Geçerli event → `entitlements` insert (`status=pending`) + onay e-postası (TV username toplama linki)
- [ ] index.html pricing bölümüne checkout linki (operatör onayı sonrası — G-P2-B2)
- [ ] Test: geçersiz imza 401, duplicate order_ref idempotent

## Acceptance Kriterleri

- [ ] G-P2-2: imza doğrulama testi yeşil
- [ ] Secret repo'ya girmez (yalnız Railway env)
- [ ] Satış açılışı P-001 T-003 backtest gate'ine bağlı (G-P2-B3)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-002 W2 — UR-002 bekleniyor |
