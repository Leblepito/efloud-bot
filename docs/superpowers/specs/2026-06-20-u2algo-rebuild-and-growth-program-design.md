# u2algo.com Rebuild + Growth Program — Birleşik Tasarım Spec'i

| Alan | Değer |
|---|---|
| Versiyon | v1 |
| Tarih | 2026-06-20 |
| Üreten | Claude (Opus 4.8) — `superpowers:brainstorming` akışı |
| Status | PLAN (doc-only; kod yok, DNS yok, publish yok) |
| Epic | u2algo.com Next.js rebuild (Track D) + P-002.5 growth layer reconcile (Track C) |
| Branch | `feat/u2algo-rebuild-program-spec` (doc-only ilk commit; per-task branch'ler sonra) |
| Sahiplik | Site rebuild = 🔵 @claude + `frontend-design` · Growth backend = 🟢 @hermes (impl) + 🔵 @claude (review) + 🟣 @gemini (ADS) + 🟠 @operator (karar/secret/DNS/publish) |
| Önceki | `feat/audit-remediation` → PR #232 (`c0ec4e6`, MERGED). Seed: `docs/handoff/2026-06-20-next-session-frontend-marketing-u2algo-rebuild-plan.md` |
| Reconcile eder | P-002.5 ULTRAPLAN (`feat/p0025-growth-layer-spec` → `docs/superpowers/specs/2026-06-17-u2algo-marketing-seo-ultraplan-design.md`) |
| Dev-contract | Karpathy 4 prensip (`CLAUDE.md` → "Geliştirme Sözleşmesi") |

---

## 1. Executive Summary

u2algo.com **sıfırdan Next.js (App Router) + Vercel** üzerinde yeniden inşa edilir; ürün modeli **pure free + waitlist** (paid tier yok, şimdilik), pazar **EN-first global** (TR ileride i18n), positioning **open research / transparency** (kanıtlanmış edge YOK → getiri iddiası YASAK). Bu rebuild, mevcut statik-HTML + `server.js` Railway sitesini değiştirir.

Aynı zamanda mevcut **P-002.5 growth ultraplan** (63 görev / 6 departman, kısmen inşa: `backend/social/` M1/M2/M3/M6 merged) bu yeni substrate'e **reconcile** edilir ve tek sıralı roadmap'e dizilir. Growth **backend**'i (Manus/xurl/compliance/approval-queue) substrate-bağımsızdır ve aynen korunur; ultraplan'ın HTML-retrofit varsayan WEB/SEO/CMP-wire görevleri Next.js'e map edilir.

Tüm çıktı **additive, flag-OFF default, draft-only** (zero auto-publish), compliance-gated, conservative-proof (90-gün track-record'a kadar dolar/net-pozitif iddia yok). Canlı MAINNET trade path'e (`configs/config.phase2_1k.yaml`, `dry_run:false`) **hiç dokunulmaz.**

---

## 2. Bağlayıcı Kararlar (operatör, 2026-06-20)

| # | Karar | Detay |
|---|---|---|
| 2.1 Ürün | **Pure free + waitlist** | Indicator(lar) TradingView'de ücretsiz; site = funnel + waitlist + research-log. Paid tier YOK (şimdilik). En düşük compliance riski. `$39`/premium CTA DÜŞER. |
| 2.2 Stack | **Sıfırdan Next.js (App Router) + Vercel** | `server.js` emekli; Supabase korunur. Vercel = Next'in doğal host'u (preview deploy, SSG/ISR, CWV). |
| 2.3 Pazar/dil | **EN-primary global** | Pine/crypto kitlesi EN-ağırlıklı; en yüksek SEO hacmi. GDPR + "no financial advice" disclaimer eklenir. TR sonra (i18n seam). |
| 2.4 Scope | **Lean MVP önce** | Track D çekirdeği önce ship; growth otomasyonu sonraki fazlar (gate'li). |
| 2.5 Positioning | **Open research / transparency** | Radikal dürüstlük; research-log gerçek yolculuğu gösterir (Wave-2 falsification dahil). Güven/eğitim satar, getiri DEĞİL. (#221 honesty fix'iyle uyumlu) |
| 2.6 Entegrasyon | **Birleşik program spec** | Bu doküman: site rebuild'i tasarlar + P-002.5'i reconcile eder + tek roadmap üretir. Tek source-of-truth. |
| 2.7 Growth dahil | **Growth otomasyonu plana dahildir** | Lean MVP'den sonra, P-002.5 reconcile edilmiş haliyle, mevcut CAC/90-gün gate'leriyle. |

> Bu kararlar P-002.5 §2.1 operatör kararlarıyla **uyumludur** (D1 EN-first ✅, D2 Higgsfield-PAID/Manus-FREE ✅, D4 conservative-proof ✅, PROD-0 free+waitlist ✅).

---

## 3. PART 1 — u2algo.com Next.js Site Rebuild (yeni tasarım)

### 3.A Mimari & repo yerleşimi
- **Yeni Next.js App Router app**, `u2algo-site/` içinde yeniden inşa edilir (isim korunur → SITE-SOT netleşir).
- Eski `server.js` + `*.html` → `u2algo-site/legacy/` snapshot'ına alınır (cutover'a kadar referans), cutover sonrası silinir.
- **Korunan/taşınan:** `brand/`, `brand-kit/` (logo SVG, BRAND.md, css), `assets/`, Supabase entegrasyon mantığı, sitemap/robots içeriği, privacy/terms içeriği.
- **Host:** Vercel (apex + www, www→apex 301). Mevcut Railway site cutover'a kadar **canlı kalır** (200 OK garantisi).

### 3.B Sayfa ağacı (MVP, EN)
```
/                    Landing (open-research value-prop)
/indicators          AYRI sayfa — SEO pillar #6 "free TV SMC indicator" BOFU girişi (indexable)
/research            Research-log index (MDX, SSG)
/research/[slug]     Tekil post (MDX, SSG)
/legal/privacy       KVKK→GDPR
/legal/terms         Terms
/legal/disclaimer    "No financial advice" (YENİ, EN compliance)
```
- **Landing bölümleri** (mevcut TR site'ın EN portu, marka sesi korunur): Hero (research positioning, getiri iddiası YOK) · What we do / don't · The indicator (free) — OB/FVG/Breaker/EQH-EQL görsel vitrin · How an idea goes live · Proof, not promise (Wave-2 NO-GO dahil) · Latest from the log (son 3 post teaser) · Waitlist CTA.
- **Canlı-chart bölümü → Faz-2'ye ertelenir** (embed riski/kompleksite; MVP'de statik screenshot/teaser).
- **premium.html / $39 CTA → DÜŞER** (§2.1; PROD-0 free+waitlist reframe).

### 3.C Veri akışı (waitlist) — Vercel farkı
- Next route handler `/api/waitlist` → **Supabase REST (server-side service-role key)**.
- ⚠️ **JSONL local fallback Vercel'de ÇALIŞMAZ** (serverless ephemeral FS, cold-start'ta sıfırlanır). 3-tier fallback retire edilir.
- **Hata davranışı (dürüstlük):** Supabase başarısızsa **sahte 200 dönme** (lead sessizce kaybolur + kullanıcıya yalan başarı). Bunun yerine kullanıcıya açık "tekrar dene" hatası döndür. MVP: Supabase primary + honest-retry. **Durable fallback (Upstash Redis / Vercel KV) = opsiyonel ileride sertleştirme** (reviewer önerisi) — Simplicity-First gereği MVP'ye girmez; Supabase HA + düşük olasılıkla tam-anda-down senaryosu için over-engineering.
- Supabase tablosu/datası **aynı kalır** (lead sürekliliği korunur). Consent gate (KVKK/GDPR) korunur.
- **Session/auth:** Marketing site **sessionless** (auth yok, public + waitlist). `bot.u2algo.com` dashboard ayrı auth app'tir (kapsam dışı, §7) — **paylaşılan session/JWT YOK**; waitlist akışı cross-origin cookie gerektirmez. (Reviewer'ın cross-origin cookie endişesi bu nedenle uygulanamaz.)

### 3.D SEO baseline (Next.js native)
- Metadata API (per-route title/desc/OG), `generateMetadata`, JSON-LD (Organization / SoftwareApplication-as-**waitlist** / FAQ / Breadcrumb), `sitemap.ts` (route + MDX'ten dinamik), `robots.ts`, canonical per-route, `next/image` opt, SSG → CWV güçlü.
- **EN x-default şimdi; /tr i18n seam hazır**, içerik sonra. Lighthouse SEO ≥95 hedef.

### 3.E Compliance baseline
- Her sayfada footer **disclaimer component** (canonical disclaimer text, drift yok); ayrı `/legal/disclaimer` (no financial advice), `/legal/privacy` (KVKK→GDPR), `/legal/terms`.
- Analytics **flag-OFF default**, consent-gated. Site kopyasında **getiri/PF/dolar iddiası YOK** (research framing).

### 3.F Research-log içerik modeli (transparency merkezi)
- **MDX dosyaları repo'da** (`content/research/*.mdx`), frontmatter (title/date/summary/tags), Next MDX → SSG.
- Seed (1-2 dürüst post): *"Why we dropped the Wave-2 premium strategy"* (falsification hikayesi), *"What our indicator actually detects (OB/FVG/Breaker/EQH-EQL)"*.

---

## 4. PART 2 — P-002.5 Ultraplan Reconcile

### 4.1 Kararlarımızla ÇÖZÜLEN blocker'lar
| Blocker | Durum |
|---|---|
| **PROD-0** (premium tanımı) | ✅ RESOLVED — free+waitlist (§2.1; ultraplan §2.1b işaretli) |
| **SITE-SOT** (deploy source-of-truth) | ✅ RESOLVED — yeni Next.js app (`u2algo-site/`) Vercel'de = tek SoT. ⚠️ cutover öncesi mevcut Railway kaynağı doğrulanır (Faz-0). |
| **MANUS-CAP** (`<head>` çakışması) | ✅ Yapısal RESOLVED — Next metadata API tüm `<head>`'i biz sahipleniyoruz, Manus dokunamaz. Auto-publish onayı yine operatör-gated. |
| **LS-FLIP** (LemonSqueezy webhook) | ⏸️ ERTELENDİ — paid tier yok (§2.1); LS/purchase görevleri parked. |

### 4.2 Substrate değiştiği için DEĞİŞEN görevler (mantık aynı, hedef Next.js)
| Ultraplan görevi | Reconcile |
|---|---|
| WEB-2 (Railway'de ayağa kaldır) | → **Vercel'de Next.js** + DNS + TLS |
| SEO-3 (5 HTML'e JSON-LD/canonical retrofit + AUDIT) | → Next **metadata API + JSON-LD component**'leri (audit gereksiz, fresh build) |
| SEO-6 ("5 CANLI HTML'e diff: premium→#waitlist") | → site-içi linking Next route yapısı; eski-HTML-fix **moot** (sayfalar emekli) |
| CMP-1/CMP-5 (canlı HTML disclaimer drift reconcile + wire) | → **layout disclaimer component** + `/legal/disclaimer` route (drift yok, baştan canonical) |
| WEB-5/WEB-6 (analytics + funnel events) | → Next analytics component (consent-gated) + route-handler event'leri |
| WEB-7 (domain-drift smoke: `railway.app` leak) | → `vercel.app`/`ualgotrade.com` leak smoke'a uyarla |
| WEB-3a/3b (LS webhook + email auth) | → LS-webhook **parked**; waitlist-confirmation email auth (SPF/DKIM) gerekirse korunur |

### 4.3 AYNEN kalan (substrate-bağımsız)
Growth **backend**'in tamamı: SD-3 Manus client (✅ #229), SD-8 approval queue, **CMP-3 content_compliance** (✅ merged #224 — `scripts/content_compliance.py`, BANNED_EN + `$39` price-whitelist + unlabeled_simulation; **NOT: `backend/social/` altında DEĞİL, `scripts/` altında**; testler `backend/tests/test_content_compliance{,_en}.py`), CMP-2 policy matrix, CON-1..10 (Higgsfield, gated), SD-4/5/6 (X/TG/YT draft), **KPI-ROUTINE + GROW-1..9**, ADS-0..5. Bunlar draft/metrik üretir; sadece UTM/link'leri yeni Next route'lara bakar.

---

## 5. PART 3 — Birleşik Fazlı Roadmap

Gate'ler HARD: bir fazın görevleri önceki gate geçmeden başlamaz.

| Faz | İçerik | Gate |
|---|---|---|
| **0 — Site MVP** *(YENİ)* | Next.js site (IA + SEO baseline + compliance + waitlist + 1-2 research-log seed + legal). Vercel'de. Railway'den cutover (<5dk, rollback). SITE-SOT doğrulaması burada. | Site canlı + waitlist sürekliliği + Lighthouse SEO ≥95 + görsel onay |
| **1 — Foundation** *(P-002.5, çoğu hazır)* | PROD-0 ✅, **CMP-3 ✅ merged (#224)**, SEO-1 keyword map, SD-1 handles, CMP-1/2, GROW-1. MANUS-CAP operatör onayı. | GATE 1: CMP-3 verified (zaten merged) + site (Faz-0) canlı |
| **2 — QuickWins** | analytics+UTM (Next), funnel events, SD-3/4/5/8 draft, **KPI-ROUTINE→GROW-5 CAC gate**, CON-4/5/6/7 brief (Higgsfield free-credit seed) | **GATE 2 (CAC):** ≥14g + ≥300 organik session + non-zero waitlist conversion |
| **3 — ContentMachine** | SEO-4/5/6 pillar'lar, CON-8/9 (3 video), SD-6, CMP-7/8, GROW-6/8/9, WEB-10 | **GATE 3 (90-gün proof):** dolar-PnL iddialarını açar |
| **4 — Scale** | CON-10, SD-10, GROW-7 A/B, CMP-9, **ADS-4/5 (Google Ads — CAC+bölge+operatör-spend gated)** | Operatör bütçe sign-off |

**Domain mimarisi:** `u2algo.com` (marketing apex, indexable) · `bot.u2algo.com` (dashboard, noindex — ayrı ops cutover, marketing'e gated DEĞİL) · `bot.ualgotrade.com` (→ staging, noindex).

---

## 6. Guardrail'ler (her görevi bağlar)
1. **Karpathy contract** (`CLAUDE.md`): Think-Before-Coding / Simplicity-First / Surgical-Changes / Goal-Driven. Mainnet risk'e dokunan → risk-ops + operatör sign-off.
2. **Trade-path dokunulmaz** — `engine/safety/`, `engine/lifecycle.py`, order path, breaker/guard değişmez. Bot LIVE MAINNET.
3. **Flag-OFF default, additive only, clean revert.**
4. **Draft-only content** — zero auto-publish; insan/Hermes approval queue zorunlu.
5. **Her içerik** `content_compliance.py` + zorunlu risk disclaimer geçer.
6. **Dürüstlük:** kanıtlanmış edge YOK → "kârlı/garantili" iddia YASAK. Research-log/transparency framing. Conservative-proof 90-güne kadar (dolar/net-pozitif yok).
7. **Secrets VPS .env-only** (+ Vercel env for site); repo secret-scan green (gitleaks CI).
8. **Hermes'e handoff** = git format-patch + sha256; Telegram transfer yasak.
9. **Atomic PR + review:** feature-branch + PR + efloud-code-reviewer/risk-ops, flat-iken merge.

---

## 7. Kapsam Dışı (YAGNI — kasıtlı ertelenen)
- Paid tier / Stripe / LemonSqueezy purchase akışı (§2.1 — entitlements seam P-003'te hazır, karar gelince).
- TR locale içeriği (i18n seam kurulur, içerik Faz-3+).
- Canlı-chart embed (Faz-2).
- Growth otomasyonu EXECUTION (specli ama Faz-0 site MVP + CAC gate arkasında).
- Higgsfield/Manus paid spend (operatör bütçe-gated; free-credit seed hariç).
- Bot dashboard migration (`bot.u2algo.com`) — bağımsız ops, marketing'e gated DEĞİL; risk-ops sign-off + flat-book penceresi gerektirir.
- PART-2 institutional blueprint (C++/FPGA/co-lo) — kuzey-yıldızı, uygulanmaz (handoff Track A pragmatizm filtresi).

---

## 8. Açık ön-koşullar / operatör girdileri (Faz-0/1 başlamadan)
1. **SITE-SOT doğrulama:** mevcut Railway u2algo-site deploy'u bu repo'daki `u2algo-site/`'tan mı besleniyor, yoksa vendored kopya mı? (Cutover güvenliği — Faz-0).
2. **Domain DNS:** `u2algo.com` DNS sahipliği/erişimi (Vercel'e yönlendirme için).
3. **Vercel hesabı/projesi:** kurulum + env (Supabase keys).
4. **MANUS-CAP:** Manus auto-publish yapıyor mu? (Faz-1 SD-3 için; `<head>` çakışması Next ile yapısal çözüldü).
5. **Handles:** `@u2algo` X/Telegram/YouTube claimable mı? (SEO-3 sameAs).
6. **Higgsfield bütçe:** Kling-only free-credit ilk batch onayı; aylık cap (Faz-2).
7. **A.S. legal:** isim/MERSIS/adres + Supabase region (CMP-1/CMP-6 GDPR/KVKK).

---

## 9. İlgili Referanslar
- Seed: `docs/handoff/2026-06-20-next-session-frontend-marketing-u2algo-rebuild-plan.md`
- P-002.5 ULTRAPLAN: `feat/p0025-growth-layer-spec` → `docs/superpowers/specs/2026-06-17-u2algo-marketing-seo-ultraplan-design.md`
- Growth backend: `backend/social/` (manus_client, xurl_client, tv_manifest, content_queue, queue_storage, approval_callback, tier2_renderers, doctrine, feeds, hypotheses, reports, research_runs, archive) — M1/M2/M3/M6 (#228-#231)
- Compliance gate: `scripts/content_compliance.py` (CMP-3, ✅ #224) + `backend/tests/test_content_compliance{,_en}.py` — **`scripts/` altında, `backend/social/` değil**
- Mevcut site: `u2algo-site/` (statik HTML + server.js, Railway `considerate-intuition`)
- Honesty fix: #221 (premium/quickstart gerçek-davranış hizalama)
- Memory: `p002_marketing_growth`, `wave2_dropped_falsification`, `frontend_dashboard_redesign_initiative`, `algorithm_setup_audit_2026_06_20`, `reference_karpathy_skills_plugin`

---

*Spec sonu. Doc-only PLAN. Implementasyon per-task, faz gate'leri arkasında, additive + flag-OFF + draft-only, trade path dokunulmaz.*
