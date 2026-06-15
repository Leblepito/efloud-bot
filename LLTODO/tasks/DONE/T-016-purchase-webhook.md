# T-016: Lemon Squeezy Purchase Webhook (HMAC) + Onay E-postası

**Epic:** P-003
**Claimed by:** @claude (2026-06-15, INERT DELIVERED; Hermes handoff) (henüz claim edilmedi)
**Tahmini süre:** 1-2 gün
**Bağımlılık:** T-015, Hermes GÖREV B (Railway env)

## Hedef

Lemon Squeezy satın alma webhook'unu imza doğrulamalı şekilde alıp entitlement kaydı + onay e-postası üretmek.

## Çıktılar

- [ ] `u2algo-site/server.js` → `POST /api/purchase-webhook` (X-Signature HMAC-SHA256 doğrulaması, secret env'den)
- [ ] Geçerli event → `entitlements` insert (`status=pending`) + onay e-postası (TV username toplama linki)
- [ ] **Refund/chargeback event'leri (UR-003):** `order_refunded` / dispute → `status=revoked`
      + T-017 revoke kuyruğuna düşer (refund-sonrası-erişim-devam riskine karşı otomatik tetik)
- [ ] **G-P3-B5 kararına göre:** abonelik seçilirse `subscription_cancelled/expired/payment_failed`
      event'leri + `expires_at` işleme (tek-seferlikse bu satır düşer)
- [ ] index.html pricing bölümüne checkout linki (operatör onayı sonrası — G-P3-B2)
- [ ] Test: geçersiz imza 401, duplicate order_ref idempotent, refund→revoked geçişi

## Acceptance Kriterleri

- [ ] G-P3-2: imza doğrulama testi yeşil
- [ ] Secret repo'ya girmez (yalnız Railway env)
- [ ] Satış açılışı P-001 T-003 backtest gate'ine bağlı (G-P3-B3)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W2 — UR-003 bekleniyor |
