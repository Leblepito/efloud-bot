# 🟧 Hermes — Commercial MVP (P-002) Açık Görevler (2026-06-11)

> Hazırlayan: Claude (Architect/Review). Bitince Claude review edecek.
> Kurallar: canlı mainnet → feature-branch + PR, atomic, secrets sadece VPS/Railway,
> destructive-op yok. Bu dosyadaki görevler P-002 planının **infra ön-işleri** —
> implementasyon görevleri (T-010..T-019) UR-002 UltraReview onayından SONRA başlar.

Bağlam: P-002 "Commercial MVP" epic'i açıldı (`LLTODO/plans/P-002-commercial-mvp.md`,
durum REVIEW_OPEN). Ticari çapa: u2algo ürün hattı (TradingView indicator ücretsiz /
strategy premium). Boşluk analizi: `docs/audit/2026-06-11-commercial-mvp-gap-analysis.md`.

---

## GÖREV A — Supabase şema ön-hazırlığı (entitlements + waitlist consent)

**Durum:** P-002 W2 (T-015) ve W0 (T-011) için Supabase tarafı hazırlık gerekiyor.
Hermes'te `supabase_postgres` MCP araçları kurulu (health, list_tables,
ensure_waitlist_leads, waitlist_*).

**Yapılacak:**
1. `waitlist_leads` tablosu hâlâ hazır değilse (canlıda health check `PGRST205`
   dönüyordu) önce `ensure_waitlist_leads` ile tabloyu oluştur — JSONL fallback'teki
   kayıtları migrate etmeyi değerlendir.
2. `entitlements` tablosu için DDL taslağı hazırla (henüz UYGULAMA, taslak):
   `id, email, product, status (pending|granted|revoked), source (lemonsqueezy|manual),
   tv_username, order_ref, granted_at, created_at` + RLS (service-role-only yazma).
3. `waitlist_leads`'e `consent boolean` + `consent_at timestamptz` kolonları için
   migration taslağı (mevcut kayıtlar `consent=null` kalır, geriye dönük varsayım yok).

**Acceptance:** waitlist tablosu canlıda çalışıyor (PGRST205 yok) + iki migration
taslağı `u2algo-site/supabase/` altında PR olarak. → Claude review.

---

## GÖREV B — Railway env hazırlığı (ödeme webhook)

**Durum:** W2 (T-016) Lemon Squeezy webhook'u `LEMONSQUEEZY_WEBHOOK_SECRET` isteyecek.

**Yapılacak:**
1. Lemon Squeezy hesabı/ürün taslağı operatörle birlikte aç (fiyat YAYINLANMAZ —
   G-P2-B2 gate'i operatör onayı ister).
2. Railway `u2algo-site` servisine `LEMONSQUEEZY_WEBHOOK_SECRET` placeholder env'ini
   ekle (değer yalnız Railway'de; repo'ya girmez).
3. Webhook URL planı: `https://u2algo-site-production.up.railway.app/api/purchase-webhook`
   — endpoint kodu T-016'da gelecek, şimdi sadece LS panel tarafını not et.

**Acceptance:** env hazır + LS ürün taslağı linki operatöre iletildi.

---

## GÖREV C — P-001 T-002/T-003 devamı (W2'nin satış konusu)

**Durum:** P-002 W2'nin satışa açılma gate'i (G-P2-B3) P-001 T-003 backtest
validasyonuna bağlı. T-001 DONE; T-002 (MTF confluence + SL/TP) backlog'da seni bekliyor.

**Yapılacak:** Önceki handoff'taki (2026-06-10 GÖREV 1) akışla T-002'yi claim et ve
implementasyona devam et. P-002 bu hattı HIZLANDIRIR, değiştirmez.

**Acceptance:** T-002 claim + ilk implement commit. → FAZ 4 UR-001.

---

## GÖREV D — Çakışma notu: prod/master reconciliation (2026-06-10 GÖREV 4)

**Durum:** Önceki handoff'taki GÖREV 4 (prod `feat/pr1-identity-tokens` ↔ master
hizalaması) hâlâ açık. P-002 implementasyonu master'dan branch alacağı için bu
reconciliation P-002 FAZ 3'ten ÖNCE bitmeli — yoksa u2algo-site değişiklikleri
(W0/W2) prod'daki `bebcc8c` token-sync ile çakışabilir.

**Yapılacak:** GÖREV 4'ü P-002 FAZ 3 başlamadan kapat veya ayrı tutma gerekçesini
belgele.

**Acceptance:** prod↔master topolojisi net + karar belgeli.

---

### Bitince

Her görev: branch + PR (master) + test. Claude'a "review" sinyali ver.
P-002 implementasyonu (T-010..T-019) UR-002 onayı olmadan BAŞLAMAZ.
