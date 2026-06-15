# Ultrareview — Dashboard & Growth-Surface Redesign Plan (2026-06-08)

Companion to `.hermes/plans/2026-06-08_efloud-dashboard-redesign.md`. This document preserves the
**verification evidence** behind the corrections folded into the canonical plan. Every ground-truth
finding was checked file-by-file against the repo.

## Verdict
Plan is sound and buildable — architecture and the 4a/4b + Phase-5 publish-gate safety boundary
are correct. Verification surfaced **3 material corrections (C1–C3)** and **3 gaps (D1–D3)**, all
patched into the canonical plan. None invalidates the plan.

## Ground-truth verification table

| # | Claim | Verdict | Evidence |
|---|------|---------|----------|
| G1 | Marketing = static `index.html`+`server.js`; `web/` stub | ✅ CONFIRMED | `u2algo-site/web/package.json` build=`node ../scripts/smoke.js`; `nixpacks.toml` build=`npm run smoke`, start=`node server.js`; `railway.json` start=`node server.js`. CLAUDE.md "Next.js 15" line is **inaccurate**. |
| G2 | `landing-reference/*.tsx` are complete Next.js components | ✅ CONFIRMED | 15 components import `next/link`+`lucide-react`. |
| G3 | Hero hard-codes fabricated metrics | ✅ CONFIRMED (overstated) | `HeroSection.tsx:360` "Start Free Demo", `:405` "50,000+ Signals Generated", `:407` "2,500+ Active Traders", `:408` "73.2% Avg Win Rate". Not all four are *literal* banned-list hits — see C1. |
| G4 | Lane A emits 3 events, all wired | ⚠️ CORRECTED → 2 events | `content_job.created` (`engine/notifications/__init__.py:77`), `content_job.position_opened` (`:109`, execution payload at `:113`). `position_closed` (`:117`) emits **nothing**. Wired in `backend/bot_runner.py:27,258`. Gate `EFLOUD_CONTENT_EMITTER_ENABLED` (`content_jobs.py:33`). Default path `/app/data/content_jobs/` (`:30`), env `EFLOUD_CONTENT_JOBS_PATH`. Consumer = **greenfield** (no reader exists). |
| G5 | Lane B = Manus spec, pull-cron, idempotent, draft-only, Drive→local | ✅ CONFIRMED | `docs/superpowers/specs/2026-06-04-lane-b-screenshot-design.md`. Budget §7 = **$5/day = 300 events** (binding). Algorithm is **§4 ("Akış")**; §10 is "PR-ready next steps". §6 = 8 failure modes. §3.2 = analysis JSON (`structure/smc_zones/invalidation/risk_note/confidence`). |
| G6 | `telegram_client.py` send-only | ✅ CONFIRMED | Only `send_message` (`:21`); no `reply_markup`/`callback_query`/`getUpdates`/`inline_keyboard`. Phase 5 greenfield. |
| G7 | Shared tokens exist | ✅ CONFIRMED | `design-tokens.ts` exports `colors`(:14)/`spacing`(:88)/`radius`(:103)/`typography`(:115)/`effects`(:139)/`tw`(:149). |
| G8 | API contract fully typed | ✅ CONFIRMED (+2) | `frontend/lib/api.ts`: `Status/OpenPosition/OpenOrder/Trade` **+ `EquityPoint`(:66), `ConfigSnapshot`(:72)**. |

## Material corrections

### C1 — Compliance gate targets the real banned list (P1)
- Banned list: `docs/marketing/GO_TO_MARKET_2026-05-28.md:16-22`, **Turkish promise-phrases**:
  "Kesin kazanç", "Garantili getiri", "Her gün kâr", "Pasif gelir makinesi", "Sinyal al kazan",
  "Fonumuza para yatır".
- **"Yatırım tavsiyesi değildir" / "Not investment advice" is ALLOWED** (prescribed disclaimer,
  `:33,:86`) — the plan mislabeled it as banned.
- Of the hero strings: `"73.2%"` violates `:8` "Performans vaadi: kesinlikle yok";
  `"guaranteed"` maps to "Garantili getiri". `"Start Free Demo"` / `"Active Traders"` are
  fabricated (remove) but not literal banned phrases.
- Content-pillar #2 SMC vocab (`FVG, OB, liquidity sweep, MSB, CHoCH`) confirmed at
  `GO_TO_MARKET_2026-05-28.md:43`.
- Disclaimer source exists in-engine: `engine/content_jobs.py:28-29` `COMPLIANCE_TR/EN`.
- **Action:** `compliance.test.ts` (#7) + pipeline jobs grep the real TR list + a numeric-% regex
  against **resolved i18n values** (see D1).

### C2 — `position_closed` emits no content_job event (P1)
- Entry path is real: `content_job.position_opened` carries
  `execution{filled,fill_price,quantity,leverage,trace_id}` (`:113`).
- Result path is **absent**: `notifications/__init__.py:117` is a plain notification method.
- **Action:** #13b adds a one-line `content_emitter.emit("content_job.position_closed", ...)` —
  additive, fire-and-forget, honors Lane A isolation. **OQ#2 reopened for the result path.**

### C3 — No monorepo/workspace exists (P1, architectural)
- Repo root has **no `package.json`/workspaces**. `frontend/`→Vercel(fra1), `u2algo-site/`→Railway,
  deployed separately. The plan's "extract once, consume thrice" needs a workspace first.
- **Resolved (operator):** npm workspaces monorepo → new PR #0 establishes root + updates both
  deploy configs before #1.

## Gaps

### D1 — i18n dependency (P1)
4 `landing-reference/*` components import `useI18n` from `@/lib/i18n/context`, which **does not
exist** in `frontend/` or `u2algo-site/`. `RiskDisclaimer` text = `t("risk_disclaimer")`.
**Action:** new PR #6b ports an i18n provider + dictionary before #7; compliance test greps the
**resolved** value, not component source.

### D2 — Second spec
`docs/superpowers/specs/2026-06-04-content-jobs-consumer-design.md` (consumer/dispatcher design)
is a source for #11/#13b alongside the screenshot spec.

### D3 — `server.js` still reads `DATABASE_URL`
`u2algo-site/server.js:11` = `SUPABASE_DATABASE_URL || DATABASE_URL`. CLAUDE.md says removed; code
keeps the fallback. #8 ports 3-tier logic verbatim.

## Technical deep-dive validation
- **SEO (#10):** App Router APIs (`metadata`/`metadataBase`/`title.template`/`app/sitemap.ts`/
  `app/robots.ts`/`app/opengraph-image.tsx`) all correct for Next.js 15. Schema.org choice
  (`SoftwareApplication`, avoid `FinancialProduct`) is regulator-safe. ✅
- **Telegram (Phase 5):** `getUpdates` long-poll (no webhook endpoint exists), `callback_data`
  ≤64B, `answerCallbackQuery` <10s — all real Bot API constraints. "1s auto-archive" critique
  valid; durable-pending+TTL redesign correct. ✅
- **Publisher (#13c):** API table accurate (X v2, IG 2-step container, LinkedIn Posts API,
  YouTube 1600-unit quota). Telegram-first rollout sound. ✅

## Resolved decisions (operator, 2026-06-08)
1. Draft TTL — durable `pending` + optional default-OFF 24–72h → `expired` (never publishes).
2. PnL disclosure — ratio/risk metrics only; absolute $ never shown.
3. Canonical domain — `https://u2algo.com`; 301 from railway host.
4. Token distribution — npm workspaces monorepo (both deploy configs updated).

## Remaining open
- OQ#2 (result path) — covered by C2's 1-line emitter (additive).
- OQ#7 Drive auth — Phase-4b prod blocker; local fallback for dev.
- OQ#8 Mobile auth — confirm backend exposes a token endpoint for bearer/secure-store.

## Recommended first slice
`#0 (monorepo root) → #1 (tokens) → #6 (Next.js scaffold) → #11 (Lane B consumer, §4)`.
