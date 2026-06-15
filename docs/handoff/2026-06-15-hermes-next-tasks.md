# 🟧 Hermes — Sıradaki Görevler: P-003 W2 Implementasyon (2026-06-15 akşam)

> Hazırlayan: Claude (Architect/Backend-orchestrator). Bitince Claude review edecek.
> Kurallar: canlı mainnet bot → feature-branch + PR, atomic, secrets sadece VPS/Railway
> env (repo'ya ASLA), destructive-op yok.
> **Transfer ÇALIŞIYOR:** VPS read-only key → `git format-patch origin/master --stdout > /tmp/<ad>.patch`
> + sha256. Claude patch'i `scp efloud-bot:/tmp/<ad>.patch` ile KENDİSİ çekiyor → sha256 doğrula →
> `git am` (authorship korunur) → review → push+PR+merge. Telegram'a içerik yapıştırma YOK.

---

## 0. Durum (master `7c19873`)

GÖREV A/B/D/E/F (infra ön-işleri) **TAMAM → #202 merged**. A entitlements SQL'leri zaten master'da
(`entitlements.sql` + `002_waitlist_consent.sql` + `waitlist_leads.sql`, `e229544`). Sıra **W2
implementasyonunda**. Operatör kararları (B.1-B.4) + F drill + E UptimeRobot OPERATÖRDE — onlar senin
beklemen gereken işler değil, paralel ilerliyorlar.

**Karar hatırlatma:** premium ürün = INDICATOR (strateji R&D'de); gelir modeli ERTELENDİ → entitlements
şeması forward-compatible (`expires_at NULL`, zaten SQL'de). T-018 müşteri Telegram = SHIPPED (#201).

---

## GÖREV 1 (ÖNCELİK) — T-015: entitlements migration apply + RLS doğrulama

SQL master'da ama Supabase'e UYGULANDI mı + RLS doğru mu — onu kesinleştir.
1. `supabase_postgres` MCP ile `entitlements` tablosunu canlıda oluştur/migrate et (idempotent — `IF NOT EXISTS`).
2. **RLS doğrula:** yalnız service-role yazabilir; anon/authenticated SELECT bile alamamalı (müşteri
   entitlement'ı kendisi okuyamaz — backend kontrol eder). RLS policy testini yaz.
3. `waitlist_leads`'e `002_waitlist_consent` (consent + consent_at) uygulandı mı teyit et.
4. Çıktı: migration apply raporu + `list_tables`/`table_columns` MCP çıktısı + RLS policy doğrulaması.

**Acceptance:** entitlements + consent kolonları canlıda; RLS service-role-only kanıtlı. → Claude review.

---

## GÖREV 2 — T-011: server.js waitlist consent alanı (W0, ungated)

`002_waitlist_consent.sql` hazır; `u2algo-site/server.js`'e consent alanını bağla.
1. Waitlist POST payload'ına `consent` (boolean) + `consent_at` (server-side timestamp) ekle.
2. **G-P3-4 KORUNUR:** 3'lü fallback zinciri (Supabase REST → PG → JSONL) consent alanıyla BOZULMADAN
   çalışmalı — mevcut test kalıbıyla regression testi.
3. Consent UI checkbox'ı (frontend) AYRI Claude oturumunda — sen yalnız server.js + payload + migration
   tarafını yap, seam'i PR notunda belirt.

**Acceptance:** server.js consent alanı + fallback regression testi yeşil. → Claude review.

---

## GÖREV 3 (PREP — INERT) — T-016: purchase-webhook HMAC iskeleti

⚠️ **GATE:** B.1-B.4 (LS AUP/TR payout/tüzel kişilik/domain) OPERATÖR kararı BEKLİYOR. Lemon Squeezy
fizibilitesi teyit edilmeden CANLI webhook AÇILMAZ (plan §3c). Ama **provider-agnostik HMAC iskeleti**
şimdi hazırlanabilir (inert, flag-gated):
1. `u2algo-site/server.js` `POST /api/purchase-webhook` — HMAC-SHA256 imza doğrulama
   (`LEMONSQUEEZY_WEBHOOK_SECRET`, env-only). **G-P3-2: geçersiz imza → 401, test kapsamında.**
2. Geçerli imza → `entitlements` insert (status `pending`/`granted`) — ama `ENTITLEMENTS_ENABLED=false`
   iken endpoint 503/feature-off döner (default-OFF, .env.example'da var).
3. Refund/cancel/expired event iskeletleri (forward-compatible — gelir modeli ertelendi, abonelikse gerekir).

**Acceptance:** webhook endpoint + HMAC 401 testi + default-OFF gate. **CANLI AKTİVASYON B teyidi +
operatör sign-off arkasında — bu PR inert.** → Claude review.

---

## GÖREV 4 (varsa zaman) — T-017: tv-access-grant runbook

`docs/runbooks/tv-access-grant.md` — operatörün TV UI'dan invite-only erişim verme akışı + entitlement
kuyruk görünümü (`status=pending` → grant → `granted`). Saf doküman, gated değil.

---

## Öncelik & Bitince

**Sıra:** GÖREV 1 (T-015) → 2 (T-011) → 3 (T-016 prep) → 4 (T-017). Her biri ayrı branch + PR + test.
B.1-B.4 OPERATÖRDE — T-016'yı CANLI açma. Her teslimat: format-patch + sha256, Claude scp+am+review eder.
Claude'a "review" sinyali ver.
