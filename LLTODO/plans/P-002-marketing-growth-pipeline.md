# Efloud-Bot Marketing + Growth — UltraPlan (Reconstructed)

> **Versiyon:** v2 (UltraPlan rekonstrüksiyonu) — @claude, 2026-06-11
> **Kaynaklar:** Hermes v1 draft (`.v1-hermes-draft.md`, aynı dizin) + 5-ajanlık repo durum tespiti
> (2026-06-11, backend/frontend/database/test/açık-iş haritaları) + repo ground-truth (origin/master `150a6b1`)
> **Epic:** P-002 · **Branch:** `feat/marketing-growth-pipeline` (şemsiye; her PR kendi branch'inde)
> **Statü:** PLAN — Hermes + operatör onayı bekliyor. Hiçbir PR başlamadı.

---

## Hedef

Efloud-bot için marketing/growth pipeline'ını **trade-path'e dokunmadan**, ölçüm-önce ve
onay-kapılı kurmak: organik içerik → waitlist → 90-gün canlı proof → premium strateji erişimi.
Kanallar: X/Twitter, YouTube Shorts, Higgsfield video, Manus otomasyon, u2algo-site SEO.

## Kapsam

**Kapsam içi:** mevcut content-jobs altyapısının aktivasyonu + genişletilmesi (M5-M8),
u2algo-site SEO/waitlist (M9-M10), public read-only snapshot (M11), growth kanalları (M13-M15),
altyapı araç kurulumları (M1-M4).
**Kapsam dışı:** trade mantığı, `engine/safety/` ve order path, prod config flip'leri,
SMC strateji değişiklikleri, paid-ads harcaması (90-gün proof + operatör onayı öncesi).

---

## 0. Ground-Truth Findings

- **G1 — Master referansı bayat:** Hermes prompt'u "master 39c2738" diyor; gerçek origin/master `150a6b1`
  (#177-#179 merge'leri sonrası). Prod hâlâ `feat/pr1-identity-tokens @ ca92ce7` — master'a reconcile
  runbook'u var, operatör-gated.
- **G2 — "Next.js 15" claim'i DOĞRU:** frontend = Next.js 15.1.0 + React 19 + TS 5.7, `output: 'export'`
  (tamamen statik, FastAPI servis ediyor). 19 component, çağrılan tüm endpoint'ler backend'de mevcut.
- **G3 — Dashboard SEO'ya KAPALI (bilinçli):** `frontend/app/layout.tsx:9` → `robots: { index:false, follow:false }`.
  Sitemap/blog/OG yok. Bot dashboard'u pazarlama yüzeyi DEĞİL; pazarlama yüzeyi ayrı repo'daki
  **u2algo-site** (Railway'de canlı, Next.js 15 marketing sayfası).
- **G4 — İçerik pipeline'ı KISMEN HAZIR:** PR #173 (master'da) content-jobs altyapısını getirdi:
  `engine/content_jobs.py` (flag-gated `_enabled()`, default OFF), `scripts/content_compliance.py`,
  `backend/social/` (7 modül: feeds, doctrine, archive, hypotheses, reports, research_runs).
  Hermes v1 bunu görmüyor — **sıfırdan kurma varsayımı yanlış**, iş "aktive et + genişlet".
- **G5 — Waitlist altyapısı kısmen canlı:** u2algo-site `server.js` 3-katmanlı kayıt
  (Supabase REST → direct PG → local JSONL). Canlıda Supabase REST bağlı ama tablo yok (PGRST205)
  → kayıtlar JSONL fallback'te. Open Question #5'in fiili cevabı "Supabase + kendi formumuz".
- **G6 — API/MCP/CLI envanteri:** Bot API: FastAPI 23 route (cookie auth) + `/ws` WebSocket.
  MCP: Higgsfield ✅, GitHub ✅, supabase_postgres ✅ (lokal, 7 tool), TradingView ⚠️ (port 9222 launch
  reçetesi var; **UI/chart-eval tool'ları KIRIK** → otomatik screenshot YOK, compile/save çalışıyor).
  CLI: gh ✅, railway ✅. xurl ❌, YouTube API ❌.
- **G7 — Bot CANLI MAINNET:** prod config `configs/config.phase2_1k.yaml` `dry_run:false`. Marketing
  işleri trade path'ine dokunamaz — content-jobs zaten scripts-only/additive tasarlandı, bu invariant korunmalı.
- **G8 — Pine/TV varlıkları hazır:** `pine/efloud_signals.pine` (SMC v2 port, korunuyor — ASLA ezilmez)
  + `pine/u2algo/wave1_signals.pine` (P-001 T-001 DONE, compile 0 hata). TV içerik üretiminin hammaddesi var.
- **G9 — DB-less prod = proof-archive engeli:** Bot prod'da DATABASE_URL yok, `EFLOUD_AUTO_MIGRATE=0`,
  11 migration hiç koşmadı. Trade history yalnız file-journal'da. "90 günlük kanıt arşivi" ve "public
  snapshot" workstream'leri DB enablement'a (Track A / Faz 4) bağımlı.
- **G10 — Güvenlik yüzeyi:** Gemini API key URL query'sinde (`?key=`), API'de rate-limit yok,
  `/history`-`/equity` pagination'sız, cookie-secure auth. Secrets-VPS-only kuralı yerleşik ve çalışıyor.

## 1. Gap Analysis (Hermes v1'e karşı)

| # | Gap | Etki |
|---|---|---|
| GAP1 | v1, PR #173 content-jobs scaffolding'ini görmüyor (G4) | WS-B'nin ~yarısı zaten merged; PR sayısı/efor şişkin. WS-B "kur" değil "aktive et + emitter ekle" |
| GAP2 | v1, u2algo-site'ı görmüyor (G5) | "Landing page taslağı" işi zaten canlı; kalan iş Supabase tablosu + SEO + domain |
| GAP3 | "Dashboard public snapshot" varsayımı | Dashboard noindex + auth'lu (G3). Public snapshot = yeni read-only endpoint + ayrı statik sayfa; gerçek PnL gösterimi operatör kararı (OQ#6) |
| GAP4 | DB bağımlılığı atlanmış (G9) | Proof-archive/equity-history PR'ları Track A Faz 4'e (DB enablement) zincirli |
| GAP5 | TV screenshot otomasyonu varsayımı | TV MCP chart-eval kırık (G6) → Playwright lane'i veya manuel export; Manus Lane B spec'i bunu zaten öngörüyordu |
| GAP6 | X/Twitter maliyet/limit analizi yok | xurl kurulu değil; X API tier ücreti + rate limit bütçelenmeli (yeni OQ) |
| GAP7 | Security fazı v1 gövdesinde yok | Bu dokümanda §4 olarak eklendi |
| GAP8 | Repo'daki açık işlerle çakışma | PR #170 (dashboard redesign, DRAFT) ve C2 result-emitter ile sıralama koordine edilmeli — C2, PR-M5 olarak bu plana alındı |
| GAP9 | v1'in orta bölümü Telegram'da kayboldu | Safety Invariants + WS-A/WS-B detayı eksik; bu doküman §2 ile boşluğu kapatır (VPS'teki orijinal referans olarak kalır) |

## 2. Görevler — Per-PR Implementation Plan (PR M1..M15)

> Kurallar: her PR atomic + flag-OFF default + TDD + tam suite yeşil + risk-ops review.
> "trade'i bozar mı?" testi: hiçbir PR `engine/safety/`, `lifecycle`, breaker, guard, order path'ine dokunmaz.
> Rollback: tümü additive → revert temiz.

### Faz A — Altyapı

| PR | İçerik | Dosyalar | Acceptance |
|---|---|---|---|
| **M1** | xurl CLI kurulum + auth runbook (doc-only) | `docs/runbooks/xurl-setup.md` | Runbook ile VPS'te xurl auth tamam; secrets .env-only |
| **M2** | TV chart-export lane: Playwright screenshot script + manuel fallback runbook | `scripts/tv_chart_export.py`, `docs/runbooks/tv-chart-export.md` | Lokal smoke: 1 sembol PNG üretir; bot süreçlerine dokunmaz |
| **M3** | Manus REST client (fail-safe, flag OFF) + task template şemaları | `backend/social/manus_client.py`, `tests/` hermetic unit | Key yokken no-op; template validate testleri yeşil |
| **M4** | YouTube upload iskeleti (scripts-only, draft mode) | `scripts/youtube_upload.py`, runbook | Draft-mode upload dry-run testi; key .env-only |

### Faz B — İçerik Pipeline

| PR | İçerik | Dosyalar | Acceptance |
|---|---|---|---|
| **M5** | C2 result-emitter: engine→content-jobs event şeması (bilinen açık iş) | `engine/content_jobs.py` (+şema), testler | Flag OFF'ta sıfır davranış değişikliği; event şema testleri |
| **M6** | İçerik template'leri (X thread, Short script, haftalık snapshot) + onay kuyruğu (draft-only) | `backend/social/templates/`, compliance hook | Her çıktı `content_compliance.py`'den geçer; disclaimer zorunlu |
| **M7** | Higgsfield video pipeline script (MCP, draft asset) | `scripts/higgsfield_video.py` | 1 örnek Short asset'i üretir; publish YOK |
| **M8** | Telegram duyuru kanalı binding (alerter additive) | `ops/alerter/` ek route | Mevcut alert akışı regresyonsuz; duyuru ayrı kanal |

### Faz C — Web

| PR | İçerik | Repo | Acceptance |
|---|---|---|---|
| **M9** | Supabase waitlist tablosu (migration) + REST doğrulama | u2algo-site (+supabase MCP) | PGRST205 kapanır; JSONL fallback'teki kayıtlar import |
| **M10** | SEO: meta/sitemap/OG/blog iskeleti | u2algo-site | Lighthouse SEO ≥90; bot dashboard noindex KALIR |
| ~~**M11**~~ | ~~Public read-only snapshot: `/api/public/snapshot`~~ **SUPERSEDED-BY P-003 T-012/T-014 (2026-06-11):** statik `proof_export.py` yaklaşımı kazandı — bot API public'e AÇILMAZ, DB bağımlılığı çözüldü (OQ#12 kapandı) | — | Bkz. `P-003-commercial-mvp.md` §3b |
| **M12** | Domain kararı (OQ#1) sonrası DNS/Railway bağlama | infra | **Operatör-gated** |

### Faz D — Growth

| PR | İçerik | Acceptance |
|---|---|---|
| **M13** | X build-in-public akışı: draft→Hermes onayı→manuel post; ilk 10 içerik | Sıfır otomatik publish; her post disclaimer'lı |
| **M14** | YouTube Shorts serisi (ilk 3 eğitim videosu, OQ#8 kararına göre) | Draft→onay→manuel publish |
| **M15** | KPI takibi: followers/waitlist/engagement (basit cron + JSON/sheet) | Haftalık otomatik rapor Telegram'a |

**Sıralama/bağımlılık (2026-06-11 dedup revizyonu):** M1-M4 paralel, **P-003 T-023 (CI secret-scan)
yeşil SONRASI** (G5 gate'i) → M5-M8 (M5, M3'e bağımsız; M6, M3'e bağımlı) → M9 hemen (T-011'in
ön-şartı), M10 **T-010 (legal sayfalar) SONRASI** (aynı site, tek sahip Hermes, serileştir) →
~~M11~~ SUPERSEDED → M12-M15 operatör kararları sonrası (M12 domain değişiminde LS webhook
URL'i yeniden kaydedilir — P-003 GÖREV B notu). M8 ↔ P-003 T-018: ayrı bot token/kanal.

## 3. Marketing & SEO Strategy

- **Positioning (v1'den korundu):** "SMC tabanlı, risk-disiplinli, şeffaf algoritmik trading araştırması."
- **Hedef kitle:** (1) TR algoritmik trade meraklısı retail, (2) EN SMC/ICT topluluğu, (3) TradingView
  indikatör kullanıcıları (Wave-1 funnel'ı: ücretsiz indikatör → site → waitlist).
- **Keyword temaları:** TR: "algoritmik trading", "SMC strateji", "risk yönetimi botu"; EN: "smart money
  concepts bot", "order block indicator", "algorithmic risk management". Blog (M10) bu temalarla açılır.
- **Funnel:** içerik (X/Shorts/TV indikatör) → u2algo-site → waitlist → 90-gün canlı proof → premium
  strateji erişimi (P-001 R-002 gelir modeli: indikatör ücretsiz, strateji premium).
- **CAC gate (R-001 bulgusu):** paid ads ÖNCESİ organik dönüşüm ölçümü; CAC hesaplanamıyorsa ads yok.
- **MRR projeksiyonu:** ancak waitlist→ücretli dönüşüm verisi geldikten sonra (90. gün) modellenir —
  v1'deki erken projeksiyon yerine ölçüm-önce yaklaşımı.
- **Content calendar:** haftada 3-5 post (OQ#4); sütunlar v1'deki 4 başlık (build-in-public, risk,
  algoritma, snapshot). Her içerik `scripts/content_compliance.py` + Hermes onayından geçer.

## 4. Security Audit

| # | Bulgu | Aksiyon | PR |
|---|---|---|---|
| S1 | Gemini API key URL query'sinde (`engine/agents/gemini_client.py`) | Header'a taşı; httpx error path redaction testi | Track A |
| S2 | Public snapshot endpoint'i (M11) auth'suz | Rate-limit + cache + sadece türetilmiş metrikler (ham pozisyon verisi ASLA) | M11 |
| S3 | Dashboard cookie auth + public yüzey aynı origin riski | Public sayfa u2algo-site'ta (ayrı origin); bot dashboard noindex+auth kalır | M10/M11 |
| S4 | dry-run/live karışıklığı → içerik sızıntısı | İçerik pipeline'ı TESTNET/LIVE etiketini metadata'dan süzer; canlı PnL yayını operatör onaylı | M6 |
| S5 | Yeni secret'lar (Manus, YouTube, X) | VPS .env-only; repo'ya gitleaks/secret-scan CI adımı | M1-M4 |
| S6 | API rate-limit yok | Public yüzey açılmadan önce FastAPI rate-limit middleware | M11 öncesi |
| S7 | Telegram aktarımıyla dosya transferi | Plan/patch transferinde bütünlük kaybı yaşandı (GAP9) → transferler git branch push'a taşınmalı (Hermes read-only key'ine PR-only write scope'lu deploy key değerlendirilebilir — operatör kararı) | süreç |

## 5. Gate — UltraReview Compliance Checklist (G1-G8)

- [ ] **G1 Trade-path dokunulmazlığı:** Diff'te `engine/safety/`, `lifecycle.py`, order path değişikliği YOK
- [ ] **G2 Flag-OFF default:** Tüm yeni özellikler default kapalı; prod config'e dokunulmadı
- [ ] **G3 Draft-only içerik:** Hiçbir otomatik publish yolu yok; onay kuyruğu zorunlu
- [ ] **G4 Risk disclaimer:** Her içerik template'inde zorunlu disclaimer + compliance script geçişi
- [ ] **G5 Secrets:** Repo'da sıfır secret; yeni key'ler VPS .env-only; secret-scan yeşil
- [ ] **G6 Testler:** Tam suite (423+) + yeni PR testleri yeşil; CI py3.11 geçti
- [ ] **G7 Operatör sign-off:** Domain (M12), gerçek-PnL gösterimi (M11), paid ads (M15 sonrası) operatör onaylı
- [ ] **G8 LLTODO süreç uyumu:** append-only STATE, atomic commit, lint 8/8, review zinciri (R-00X → UR-002)

## 6. Open Questions

Hermes v1'in 8 sorusu (operatöre — domain, X handle, dil, takvim, waitlist aracı, PnL gösterimi,
ads bütçesi, ilk video konusu) **aynen açık**. Yeni eklenenler:

9. X API tier'ı ve aylık maliyeti — hangi pakete bütçe var? (GAP6)
10. Public snapshot'ta PnL formatı: yüzde-bazlı mı, $ mi, sadece equity-curve şekli mi? (S2/OQ#6 türevi)
11. Hermes'e PR-only write scope'lu ikinci deploy key verilecek mi, patch-transfer süreci mi kalacak? (S7)
12. M11 public endpoint'i Track-A DB enablement'ı beklesin mi, file-journal'dan mı servis etsin? (G9)
