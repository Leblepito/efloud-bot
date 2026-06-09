# Frontend Dashboard-Redesign — Durum Tablosu + Railway Bağlantısı (2026-06-09)

Bu oturum: (1) frontend/growth planının kodlanma durumunu repo ground-truth ile çıkardı,
(2) Railway bağlantısını `.env` üzerinden kurdu, (3) regresyon (pytest) koşup bir latent bug
düzeltti, (4) Phase-1 monorepo foundation'ını izole worktree'de build doğruladı.

## Kaynak dosyalar
- Plan (canonical, ultrareviewed): `.hermes/plans/2026-06-08_efloud-dashboard-redesign.md`
  (branch `claude/frontend-ultraplan-review-BMuiu`, HEAD `12b9d5d`).
- Ultrareview kanıtları: `docs/superpowers/audits/2026-06-08-dashboard-redesign-ultrareview.md`.
- Bu iş **master'a MERGE EDİLMEMİŞ** — sadece `claude/frontend-ultraplan-review-BMuiu` branch'inde.

## Servis mimarisi (re-scope amendment 6e66856 ile netleşti)
| Railway servisi | İçerik | Build | Serve |
|-----------------|--------|-------|-------|
| `efloud-bot` | Trade bot **+ operatör Dashboard** | kök `Dockerfile` (frontend `next build` → `output:'export'`) | FastAPI `StaticFiles(html=True)` `/` |
| `u2algo-site` | **Ticari satış platformu** (indikatör/algo satışı) | `u2algo-site/railway.json` (NIXPACKS) | `node server.js` |

> Phase 3 artık sadece landing+waitlist değil: katalog + ödeme (Stripe) + lisans/entitlement
> (TradingView invite-only indikatör erişimi + bot aboneliği) + hesap/auth = tam storefront.
> PR #6–#10 bunun ilk dilimi. Detaylı tasarım Phase 3 başlayınca yapılacak.

## PR durum tablosu (22 PR)

| Faz | PR | İş | Durum |
|-----|----|----|-------|
| **1 — Design System** | #0 | npm-workspaces monorepo root (C3) | ✅ DONE (69f90d6) |
| | #1 | `@efloud/tokens` paketini çıkar | ✅ DONE (69f90d6) |
| | #2 | Dashboard token'ları benimser | ✅ DONE (12b9d5d) |
| **2 — Dashboard Redesign** | #3 | Layout/IA + nav (tabbed shell) | ⬜ kalan |
| | #4 | Component görsel pass | ⬜ kalan |
| | #5 | Responsive/density | ⬜ kalan |
| **3 — Public Site/SEO (→ satış platformu)** | #6 | Next.js App Router scaffold (`u2algo-site/web`) | ⬜ kalan |
| | #6b | i18n provider port (D1) | ⬜ kalan |
| | #7 | Landing wire + compliance-strip (C1) | ⬜ kalan |
| | #8 | Waitlist API bridge (3-tier, D3) | ⬜ kalan |
| | #10 | SEO: metadata + JSON-LD + sitemap/robots | ⬜ kalan |
| **4a — Offline Draft Pipeline** | #11 | Lane B consumer harness (§4) | ⬜ kalan |
| | #12 | Lane C copywriting | ⬜ kalan |
| | #13 | Multi-TF commentary gen | ⬜ kalan |
| | #14 | Lane D visual/video | ⬜ kalan |
| **5 — Approval Flow (GATE)** | #16 | Telegram reply_markup + callback | ⬜ kalan |
| | #17 | getUpdates poller + approval FSM | ⬜ kalan |
| | #18 | Web Edit UI (future) | ⬜ kalan |
| **4b — Activation & Publish (gated)** | #13b | Trade-triggered fast lane (+1-line result emitter, C2) | ⬜ kalan |
| | #13c | Multi-platform publisher (Lane E) | ⬜ kalan |
| | #15 | Lane F metrics + orchestrator | ⬜ kalan |
| **6 — Mobile App (RN/Expo)** | #19 | Expo scaffold + `packages/shared-types` | ⬜ kalan |
| | #20 | auth + api layer | ⬜ kalan |
| | #21 | core screens | ⬜ kalan |
| | #22 | push notifications | ⬜ kalan |

**Özet: 3/22 kodlandı (tüm Phase 1). Foundation hazır; Phase 2+ açık.**
Lane A emitter (Phase 4'ün temeli) zaten shipped & wired, default-OFF (`engine/content_jobs.py`).

## Phase-1 build doğrulaması (izole worktree, branch HEAD 12b9d5d)
- `npm install` (workspaces, 298 paket) → **exit 0**
- `@efloud/tokens` `tsc --noEmit` → **temiz**
- `frontend` `tsc --noEmit` → **temiz** (PR #2 shared package'a karşı derleniyor)
- `frontend` vitest → **3/3 passed** (KronosCard)
- `frontend` `next build` (output:'export') → **exit 0**: 5 static page, `out/index.html` +
  `out/login/index.html` + `out/404.html` üretildi. **Deploy-ready.**

`next.config.ts`: `output:'export'` + `transpilePackages:['@efloud/tokens']` + `trailingSlash:true`
→ static export, FastAPI serve eder. Deploy modeli sağlam.

## Railway bağlantısı (bu oturumda kuruldu)
- `.env` (gitignored): `RAILWAY_CLIENT_ID=rlwy_oaci_…` eklendi; `RAILWAY_TOKEN=` / `RAILWAY_API_TOKEN=`
  **boş** (operatör dolduracak).
- `.env.example`: Railway bloğu + iki-servis açıklaması (placeholder, gerçek değer yok).
- `scripts/railway_set_token.ps1`: token'ı ekranda göstermeden `.env`'e yazan helper ("button").
- `docs/runbooks/railway-deploy.md`: tam deploy akışı (CLI login → link → up).

## Bu oturumda düzeltilen bug (regresyon sırasında bulundu)
**Lane A content-job emitter UTF-8 bug** (`engine/content_jobs.py:79`): şema dosyası encoding'siz
`read_text()` ile okunuyordu → UTF-8 olmayan locale'de (Windows cp1252, C-locale container)
Türkçe compliance `const` string'leri bozuluyor → **her emit şema validation'da fail → Lane A
tüm event'leri sessizce düşürür**. Fix: `read_text(encoding="utf-8")` (JSON her zaman UTF-8, RFC 8259).
Ayrıca `tests/test_content_jobs.py`: 4 yerde lokal `date.today()` → UTC (emitter UTC kullanıyor,
date-boundary flake). `jsonschema` venv'e kuruldu (requirements.txt'te vardı, kurulu değildi).
**Sonuç: `pytest tests/` → 406 passed, 6 skipped, 0 failed.**

## Sıradaki somut adım
Plan suggested first slice: `#0 → #1 → #6 → #11`. #0/#1/#2 ✅. Sıradakiler:
- **#11 (Lane B consumer)** — Python, self-contained, spec §4 var, pytest ile test edilir, canlı
  trade'e/publish'e dokunmaz. Temiz "next implementation" adayı (kendi brainstorm/spec dilimi).
- **#6 (Next.js scaffold)** — Phase 3 re-scope nedeniyle **önce detaylı tasarım** istiyor (storefront).
