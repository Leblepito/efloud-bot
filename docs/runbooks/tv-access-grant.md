# Runbook: TradingView Erişim Grant + Entitlement Kuyruğu (T-017 / P-003 W2)

> **Amaç:** Lemon Squeezy webhook → entitlement tablosuna `status='pending'` yazıldıktan sonra,
> TradingView'e manuel erişim verme sürecini runbook'laştırmak. **Tam otomasyon W4+ R&D backlog** —
> TV'nin resmi public API'si olmadığından "Manage access" UI adımı manuel kalır.
> **SLA:** pending → granted ≤ 24 saat.

---

## 1. Kuyruğu Görüntüle (Günde birkaç kez)

### Yöntem A — Script (önerilir)
```bash
# VPS'te veya lokalde (env ayarlandıysa):
cd /opt/efloud-bot
python3 scripts/list_pending_entitlements.py

# Filtreli:
python3 scripts/list_pending_entitlements.py --status pending
python3 scripts/list_pending_entitlements.py --status granted --limit 100
python3 scripts/list_pending_entitlements.py --status all
```

### Yöntem B — Supabase dashboard
1. https://app.supabase.com → project seç → **Table Editor** → `entitlements`
2. `status = pending` filtresi
3. Sütunlar: `email, product, order_ref, source, created_at, expires_at`

### Yöntem C — SQL Editor
```sql
select email, product, status, source, order_ref, granted_at, expires_at, created_at
from public.entitlements
where status = 'pending'
order by created_at asc;
```

---

## 2. TradingView Erişim Ver (Manuel)

**Ön koşul:** T-016 webhook aktif (`LS_WEBHOOK_ENABLED=true` + secret set). Aktif değilse kuyruk BOŞ olur.

### Adım 1 — Ürün tipine göre doğru TV yönetim paneline git
- **wave1-premium** (TradingView indicator) → [TradingView Pine Editor](https://www.tradingview.com/chart/?solution=pine) → script'in "Publish" ayarları
- **wave1-pro** (strateji) → aynı yer, strateji sekmesi

### Adım 2 — "Invite-only" / "Manage access" ayarla
1. TradingView → Pine script listesinde u2algo ürününü bul
2. **"..."** menüsü → **"Manage access list"** (veya "Invite-only")
3. Müşteri e-postasını ekle (VEYA TV username — alan varsa)
4. **Save** — müşteri TV'ye girip görebilir

### Adım 3 — Entitlement DB güncelle (status → granted)
```sql
-- Supabase SQL Editor'da veya script ile:
update public.entitlements
set status = 'granted',
    granted_at = now(),
    tv_username = $1  -- opsiyonel: müşterinin TV kullanıcı adı
where order_ref = $2;  -- LS order ID

-- Doğrula:
select * from public.entitlements where order_ref = $2;
```

### Adım 4 — Müşteriye onay e-postası
- **B.4 (Resend) onaylandıysa:** Resend API ile otomatik template gönder
  - Şimdilik bu entegrasyon T-016 finalize edilecek (LS_WEBHOOK_ENABLED aktif olduktan sonra)
- **B.4 bekliyorsa:** Manuel e-posta (operatör):
  - Subject: "u2algo erişimin hazır"
  - Body: TV'ye giriş linki + ürün adı + destek maili

---

## 3. Revoke (İade / Dispute) Durumu

T-016 webhook `order_refunded` event'ini otomatik handle eder → `status='revoked'`. **Operatör hâlâ TV erişimini kaldırmalı:**

### Adım 1 — Revoke kuyruğunu gör
```bash
python3 scripts/list_pending_entitlements.py --status revoked
```

### Adım 2 — TV "Manage access" → e-postayı kaldır
- Aynı "Manage access list" ekranı
- Müşteriyi bul → **"Remove access"**

### Adım 3 — DB'de `granted_at` temizle (opsiyonel, audit için)
```sql
update public.entitlements
set granted_at = null,
    updated_at = now()
where order_ref = $1 and status = 'revoked';
```

### Adım 4 — Müşteriye bilgilendirme (opsiyonel)
- İade onayı zaten LS tarafından gönderildi
- u2algo tarafında "erişiminiz kaldırıldı" bilgilendirmesi gerekmez (kötü UX); sessiz revoke

---

## 4. SLA ve Monitoring

| Metrik | Hedef | Kaynak |
|---|---|---|
| Pending → Granted | ≤ 24h | Operatör runbook takip |
| Refund → Revoke | ≤ 1h | Otomatik (T-016) + TV manual ≤ 1h |
| Duplicate `order_ref` | 0 (idempotent) | T-016 ON CONFLICT DO NOTHING |

**Haftalık kontrol:** Pazartesi sabahı tüm "pending" entitlement'ları gözden geçir. 24h'yi aşanları araştır (LS webhook çalışmıyor olabilir).

---

## 5. Bilinen Sınırlar

- **Tam otomasyon W4+:** TV'nin resmi public API'si yok. W4+ R&D backlog'unda "TradingView unofficial API" veya "TV partner program" araştırması var.
- **Email gönderimi:** Resend entegrasyonu T-016 finalize aşamasında. Şimdilik manuel e-posta kabul.
- **SLA ölçümü:** Şu an operatör takip ediyor. Otomasyon: haftalık cron → `pending > 24h` raporu (W4+ R&D).
- **TV username opsiyonel:** Entitlement tablosunda `tv_username` nullable. Müşteri sadece e-posta ile TV'ye eklenirse boş kalır.

---

## 6. Hata Durumları

| Hata | Muhtemel neden | Çözüm |
|---|---|---|
| Kuyruk sürekli boş | T-016 webhook aktif değil (`LS_WEBHOOK_ENABLED=false`) veya LS event gelmiyor | T-016 logları kontrol, LS panel test webhook gönder |
| `order_ref` duplicate | Aynı sipariş 2 kez webhook tetikledi | `ON CONFLICT DO NOTHING` idempotent — logla, sorun yok |
| Müşteri TV'de göremiyor | Email typo veya "Manage access" eklenmemiş | TV ürün ayarlarını kontrol, e-posta doğrula |
| Refund event gelmiyor | LS panel webhook URL yanlış veya devre dışı | LS dashboard → Webhooks → URL doğrula, test event gönder |
| 24h SLA aşımı | Operatör unreachable veya runbook ihmal | Haftalık pazartesi raporu + Telegram alert (P-003 W4+) |

---

## 7. İlgili Dokümanlar

- T-015 (entitlements DDL): `u2algo-site/supabase/entitlements.sql`
- T-016 (webhook handler): `u2algo-site/server.js` (INERT default)
- T-017 task kartı: `LLTODO/tasks/BACKLOG/T-017-tv-access-runbook.md`
- P-003 plan: `LLTODO/plans/P-003-commercial-mvp.md` §T-017
- Operatör onay gerektiren durumlar: B.1 (LS ürün taslağı), B.4 (domain/email)
- Kuyruk script: `scripts/list_pending_entitlements.py`

---

## 8. Kabul Kriterleri (T-017 → DONE)

- [x] `docs/runbooks/tv-access-grant.md` (7+ bölüm, revoke akışı dahil)
- [x] `scripts/list_pending_entitlements.py` (argparse + status filter + JSON çıktı)
- [x] SLA notu (≤ 24h)
- [x] Hata durumları tablosu
- [x] Tam otomasyon W4+ R&D backlog notu
