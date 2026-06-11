# P-002: Commercial MVP — u2algo Satış Altyapısı (Legal + Kanıt + Monetizasyon + Müşteri Deneyimi)

**Başlangıç:** 2026-06-11
**Sahip:** @hermes (implementor, infra), @claude (architect/reviewer), @gemini (ek reviewer adayı — review dosyası açılınca numaralanır)
**Branch:** `claude/trading-bot-mvp-plan-l83v5s` (plan), implementasyon dalga başına ayrı feature-branch
**Versiyon:** 1.0 (DRAFT — UltraReview UR-002 bekliyor)
**Dayanak:** `docs/audit/2026-06-11-commercial-mvp-gap-analysis.md`

---

## 1. Hedef

u2algo ürün hattını (TradingView indicator ücretsiz / strategy premium) **satılabilir**
hale getiren kurumsal MVP katmanlarını kademeli eklemek: legal pack → public kanıt
katmanı → ödeme/entitlement rayı → müşteri deneyimi. Canlı trade sistemine sıfır temas.

## 2. Kapsam

### 2a. Dahil

- **W0 Legal & Compliance:** u2algo-site'a ToS / Privacy / Risk Disclosure / Refund
  sayfaları + waitlist KVKK/GDPR consent alanı.
- **W1 Güven & Kanıt:** trade journal'dan oransal/aggregate public proof snapshot,
  aylık statement (CSV+MD), uptime alanı, public CHANGELOG.
- **W2 Monetizasyon:** Lemon Squeezy checkout + HMAC doğrulamalı purchase webhook,
  Supabase `entitlements` tablosu, TradingView kuyruk-destekli manuel erişim grant
  runbook'u.
- **W3 Müşteri Deneyimi:** opt-in (default-OFF) gecikmeli/aggregate Telegram kanal
  bildirimi, müşteri quickstart dokümantasyonu, destek kanalı + FAQ.

### 2b. Hariç (Kapsam Daraltma)

- Multi-tenant SaaS, müşteri API key vault, kullanıcı başına bot instance (roadmap
  2026-05-05 kararıyla uyumlu).
- TradingView erişiminde tam otomasyon (resmi API yok) → W4+ araştırma maddesi.
- Gerçek zamanlı sinyal satışı ("sinyal servisi" regülasyon çerçevesi) → bildirimler
  gecikmeli/aggregate, default-OFF.
- Dashboard çoklu kullanıcı/rol + 2FA → P2; dashboard operatör aracı olarak kalır.
- Canlı `config.yaml` / compose / VPS değişikliği → bu epic'te YOK.

## 3. Teknik Tasarım

### 3a. Mimari

```
                    ┌─ W0: u2algo-site/legal/*.html ─ index.html footer ─ sitemap.xml
                    │
trade_journal.jsonl ┼─ W1: scripts/routines/proof_export.py ──► state/proof_snapshot.json
                    │       (oransal/aggregate; mutlak bakiye YOK)        │
                    │                                                     ▼
                    │                                        u2algo-site (statik servis)
                    │
ops/daily_report/   ┼─ W1: monthly.py (aggregate.compute_summary reuse) ─► CSV+MD
                    │       backend/api.py /api/reports/monthly (auth'lu)
                    │
Lemon Squeezy ──────┼─ W2: u2algo-site/server.js POST /api/purchase-webhook (HMAC)
                    │       └► Supabase entitlements ─► onay e-postası
                    │       └► docs/runbooks/tv-access-grant.md (manuel TV grant)
                    │
SafeOrchestrator ───┴─ W3: engine/notifications/telegram_notifier.py
   (DOKUNULMAZ)            (NullNotificationManager duck-type; default-OFF flag)
```

### 3b. Veri Akışı

- **Proof:** `state/trade_journal.jsonl` → `proof_export.py` (cron, `scripts/routines/`
  runner kalıbı) → `state/proof_snapshot.json` → site'a yayın (statik upload/Supabase) →
  ziyaretçi. Bot API'si public'e AÇILMAZ.
- **Satış:** site checkout linki → Lemon Squeezy (merchant-of-record, KDV/VAT LS'de) →
  webhook (imza doğrula) → `entitlements` insert → onay e-postası → operatör TV UI'dan
  invite-only erişim verir → entitlement `granted` işaretlenir.
- **Bildirim (W3):** kapanmış/teyitli olaylar → gecikmeli aggregate özet → u2algo
  Telegram kanalı. Trade karar yolundan tek yönlü okuma; geri besleme YOK.

### 3c. Bağımlılıklar

- W2 ⇐ W0 (legal pack olmadan satış açılamaz).
- W2 ⇐ P-001 T-003 (satılacak premium strategy script'in backtest/validasyonu).
- W3 ⇐ W2 (ödeyen müşteri kohortu).
- W1 bağımsız, hemen başlayabilir (Lead Trader yoluna da hizmet eder).
- Hermes altyapı ön-işleri: `docs/handoff/2026-06-11-hermes-commercial-mvp-tasks.md`.

## 4. Görsel Standartlar

### 4a. Renk Paleti (u2algo-site mevcut dark theme değişkenleri korunur)

| Eleman | Renk | Kaynak |
|---|---|---|
| Legal sayfalar | site `--surface` / `--muted` | `index.html` mevcut CSS değişkenleri |
| Proof metrikleri | site accent | Brand kit (`u2algo-site/brand-kit/`) |
| Uyarı/disclaimer | `--warn` | Mevcut disclaimer bloğu stili |

### 4b. Çizgi Stilleri

| Eleman | Kalınlık | Stil |
|---|---|---|
| Equity eğrisi (% normalize) | 2px | solid |
| Drawdown bandı | 1px | dashed |

## 5. Kalite Gate'leri

### 5a. Teknik Gate'ler

- [ ] G-P2-1: Proof snapshot'ta mutlak bakiye/pozisyon büyüklüğü alanı YOK (test ile zorlanır).
- [ ] G-P2-2: Purchase webhook imza doğrulaması — geçersiz imza 401, test kapsamında.
- [ ] G-P2-3: `notifications:` flag default-OFF; flag kapalıyken davranış birebir mevcut
      (NullNotificationManager) — regression test.
- [ ] G-P2-4: server.js 3'lü fallback zinciri (Supabase REST → PG → JSONL) consent
      alanıyla bozulmadan çalışır — mevcut test kalıbıyla.
- [ ] G-P2-5: `git diff` canlı dosyalara (config.yaml, compose, .env) temas etmez.

### 5b. İş Gate'leri (CAC/Gelir)

- [ ] G-P2-B1: Legal metinlerde getiri vaadi/yatırım tavsiyesi dili yok (guardrail
      checklist'ten geçirilir).
- [ ] G-P2-B2: Fiyatlandırma + refund policy yayından önce operatör onayı.
- [ ] G-P2-B3: İlk satış açılışı öncesi P-001 T-003 backtest gate'i (min 100 trade,
      OOS %30) PASS.
- [ ] G-P2-B4: Proof sayfası yayını öncesi operatör onayı (hangi metriklerin kamuya
      açılacağı).

## 6. Görevler

| ID | Dalga | Açıklama | Tahmini Süre | Bağımlılık |
|---|---|---|---|---|
| T-010 | W0 | u2algo-site legal sayfaları (terms/privacy/risk-disclosure/refund) + footer + sitemap | 1 gün | — |
| T-011 | W0 | Waitlist consent checkbox + server.js payload alanı (+test) | 0.5 gün | — |
| T-012 | W1 | `scripts/routines/proof_export.py` + snapshot şema + privacy testi | 1-2 gün | — |
| T-013 | W1 | `ops/daily_report/monthly.py` + `/api/reports/monthly` (auth'lu) + test | 1-2 gün | — |
| T-014 | W1 | Uptime alanı (alerter heartbeat'ten) + public CHANGELOG.md + site updates bölümü | 1 gün | T-012 |
| T-015 | W2 | Supabase `entitlements` migration + RLS (Hermes ön-işi ile) | 0.5 gün | T-010 |
| T-016 | W2 | Lemon Squeezy webhook endpoint (HMAC) + onay e-postası + test | 1-2 gün | T-015 |
| T-017 | W2 | `docs/runbooks/tv-access-grant.md` + entitlement kuyruk görünümü | 0.5 gün | T-016 |
| T-018 | W3 | `engine/notifications/telegram_notifier.py` (default-OFF) + regression test | 1-2 gün | T-016 |
| T-019 | W3 | `docs/customer/quickstart-tradingview.md` + site FAQ/destek bölümü | 1 gün | T-017 |

## 7. Riskler

| Risk | Olasılık | Etki | Mitigasyon |
|---|---|---|---|
| Proof snapshot'tan hassas veri sızması | Düşük | Yüksek | Whitelist şema + G-P2-1 testi + yayın öncesi operatör onayı |
| Webhook sahteciliği (sahte entitlement) | Orta | Yüksek | HMAC imza zorunlu (G-P2-2), secret yalnız Railway env |
| "Sinyal servisi" regülasyon çerçevesine girme | Orta | Yüksek | W3 bildirimleri gecikmeli/aggregate + default-OFF + legal review |
| TV manuel grant darboğazı (ölçek) | Düşük | Orta | MVP'de kabul; kuyruk + runbook; otomasyon W4+ |
| Canlı sisteme yanlışlıkla temas | Düşük | Kritik | Tüm işler additive/flag'li; G-P2-5 diff gate; risk-ops review zorunlu |
| P-001 T-003 gecikirse W2 boşta kalır | Orta | Orta | W2 altyapısı üründen bağımsız hazırlanır; satış açılışı gate'e bağlı |

## 8. Revizyon Geçmişi

| Tarih | Revizyon | Yazar |
|---|---|---|
| 2026-06-11 | İlk sürüm (DRAFT, UR-002 bekliyor) | @claude |
