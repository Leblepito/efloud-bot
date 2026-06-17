# u2algo Marketing + SEO Ultraplan — Synthesis Spec

| Field | Value |
|---|---|
| Version | v1 |
| Date | 2026-06-17 |
| Epic | P-002.5 "Manus+Higgsfield Growth Layer" |
| Branch (suggested) | `feat/p0025-growth-layer-spec` (doc-only first PR; per-task branches after) |
| Status | PLAN |
| Owners | @hermes (impl/backend/content ops, VPS) · @claude (review/orchestration/Pine/risk) · @operator (decisions, secrets, DNS, payments, publish sign-off) · @gemini (paid acquisition / Google Ads — CAC-gated, §4.7) |
| Supersedes/concretizes | P-002 M6/M7/M10/M13/M14/M15 · P-003 T-010/T-011/T-016 |
| Departments | 6 (SEO, Content, Social, Web, Compliance, Growth) |
| Tasks | 58 dept tasks + 5 synthesis-added gate/blocker tasks = **63** |
| CRIT/HIGH findings resolved | 21 (3 CRIT + 18 HIGH) |

---

## 1. Executive Summary

u2algo, ücretsiz TradingView SMC indikatörünü tepe-huni varlığı olarak kullanan, EN-first global bir içerik + SEO büyüme hunisi kurar. Akış: content → u2algo.com landing → waitlist → 90-gün canlı kanıt → premium indikatör/erişim. Strateji deliberate bir pivottur: P-002'nin TR-first konumlandırması EN-first ile değiştirilir (TR ikincil hreflang destek katmanı kalır). Bütçe HYBRID: Higgsfield PAID (hero/demo/edu video, 15s segment tavanı gerçeği ile), Manus.im + X FREE-start (manuel-onay yarı-otomasyon, CAC datası çıkana kadar paid yok). Tüm çıktı additive, flag-OFF default, draft-only (sıfır auto-publish), `content_compliance.py` + zorunlu risk disclaimer geçer, ve 90-gün track record'a kadar conservative proof (equity SHAPE + aggregate % only, sıfır dolar) gösterir. Canlı MAINNET trade path'e (bot `configs/config.phase2_1k.yaml`, `dry_run:false`) hiç dokunulmaz. İş 4 faza bölünür — Foundation / QuickWins / ContentMachine / Scale — aralarında CAC gate, 90-gün proof gate ve operatör sign-off'ları ile.

**The honest funnel terminus** (governance CRIT): premium ürün bugün farklılaşmamış. Funnel terminus "free indicator + waitlist for premium tier" olarak konumlanır; `$39` SoftwareApplication schema'sı PREMIUM-PRODUCT-DEFINITION task'ı (PROD-0) kapanana kadar yayınlanmaz. **(OPERATÖR ONAYLADI 2026-06-17: "ücretsiz + waitlist" reframe + proof duruşu = "research-log / build-in-public" — aşağıda §2.1b.)**

---

## 2. Binding Operator Decisions + Domain Architecture + Invariants

### 2.1 Operator Decisions (2026-06-17, BINDING)
| # | Decision | Detail |
|---|---|---|
| D1 | **Audience** | GLOBAL / EN-FIRST. SEO + social primary = English; TR secondary hreflang layer. Overrides P-002 TR-first. |
| D2 | **Budget** | HYBRID. Higgsfield = PAID (hero/demo/edu). Manus.im + X = FREE-start, manual-approval; paid only after CAC data. |
| D3 | **Brand** | `u2algo` single consumer brand; landing = u2algo.com; `efloud` internal only. |
| D4 | **Proof** | CONSERVATIVE. Equity-curve SHAPE + aggregate % (win-rate, R:R) only — NO dollar amounts — until 90-day live track record. All content disclaimer-gated. |
| — | **Legal** | Turkish A.S. exists; revenue model one-time / lifetime. |

### 2.1b Resolved this session (2026-06-17, operator)
| # | Question | Decision | Downstream effect |
|---|---|---|---|
| OQ#1 PROD-0 | What is the `$39` premium tier? | **"Free indicator + waitlist" reframe.** No differentiated premium defined yet (Wave-2 premium strategy was DROPPED). Funnel terminus = free indicator + waitlist; live `$39` checkout repositioned as "founding / early-access", NOT "buy premium product". | PROD-0 acceptance = the reframe (not a new product spec). SEO-3 SoftwareApplication schema stays "waitlist", no `$39` offer markup until a real premium is later defined. CON-4/CON-7 CTAs say "join waitlist". |
| OQ#4 Proof posture | What to show while live proof is negative (−5.3%)? | **"Research-log / build-in-public" reframe.** Show metrics honestly framed as "naive single-config bot, NOT the product"; lock all dollar + net-positive claims behind the 90-day gate; route organic traffic to education + free indicator, NOT into the proof block as a conversion moment. | SEO-5 pillar #5 reframed "research log" (not "verified track record" claim). CON-4/CON-5 show shape+aggregate framed as research, 0 $. GROW-8 milestone unlocks positive/$ claims only. CMP-4 keeps `return_pct` out of the positive-claim whitelist. |

### 2.2 Domain Architecture (BINDING)
| Host | Role | Index policy |
|---|---|---|
| `u2algo.com` | Marketing/SEO hub (apex + www) | Fully indexable |
| `bot.u2algo.com` (app) | PRODUCTION dashboard (migrated from bot.ualgotrade.com) | `noindex` (auth app stays out of index) |
| `bot.u2algo.com` (root landing) | Thin static branded landing | Indexable (branded/product intent) |
| `bot.ualgotrade.com` | STAGING/test env for new bot versions | Fully `noindex` (robots Disallow + X-Robots-Tag) |

### 2.3 Hard Invariants (every task honors; violation = rejected)
1. **Trade path untouchable** — no changes to `engine/safety/`, `engine/lifecycle.py`, order path, breaker/guard. Bot LIVE MAINNET.
2. **Flag-OFF default, additive only, clean revert.**
3. **Draft-only content** — zero auto-publish; human/Hermes approval queue mandatory.
4. **Every content piece** passes `content_compliance.py` + mandatory risk disclaimer.
5. **Secrets VPS .env-only**; repo secret-scan green (gitleaks v8.18.4 already in `ci.yml` lines 109-119 — VERIFIED present); no keys in repo/config/commit/logs.
6. **Conservative proof** until 90-day track record.
7. **Model-to-model handoff to Hermes** = git format-patch + sha256 verification (Telegram transfer banned).

---

## 3. Ground-Truth Corrections (empirically verified this session)

These override conflicting governance claims. Commands run against live repo.

| Claim | Verdict | Evidence |
|---|---|---|
| `content_compliance.py` is TR-only (EN banned phrases leak) | **TRUE** | `find_violations('Guaranteed profit, risk-free returns, double your money')` → `[]`. No `BANNED_EN_PHRASES`. |
| `$39` product price false-rejected | **TRUE** | `find_violations('Founding member - $39 lifetime')` → `['absolute_money']`. |
| `has_disclaimer(...,'both')` impossible for EN-first assets | **TRUE** | EN-only text → `'both'`=False, `'en'`=True. `has_disclaimer` already supports `lang='en'/'both'`. |
| Live disclaimer drifts from `COMPLIANCE_TR` constant | **TRUE** | `has_disclaimer('Yatirim tavsiyesi degildir','tr')` → False (live uses short form). |
| `premium_proof.json` is negative | **TRUE** | `return_pct:-5.3, win_rate_pct:24.1, 83 trades / 9 days`. |
| GROW-4 `AlertRouter.from_env()` resolves to trade-alert channel | **TRUE** | `_alert.py:21-22` reads only `EFLOUD_TELEGRAM_TOKEN/CHAT_ID`. |
| `runner.run_one` builds live Binance client | **TRUE** | `_base.py:20-26` `make_future_client` reads `BINANCE_API_KEY/SECRET`. |
| CSO: T-023 gitleaks secret-scan MISSING in CI | **FALSE** | `ci.yml:109-119` `gitleaks v8.18.4` job present + required. Do NOT re-implement. |
| Eng: index.html has 2 canonicals (duplicate-canonical bug) | **FALSE** | All 5 pages have exactly 1 `rel="canonical"`. The "2nd" is a CSS comment. No bug. |

---

## 4. Department Map

Owners legend: 🔵 @claude · 🟢 @hermes · 🟠 @operator.

### 4.0 PROD — Premium Product Definition (NEW, synthesis-added, gates the funnel)

Mission: define WHAT the `$39` premium tier IS before any CTA/schema markets it. Resolves governance CRIT-1.

| id | title | owner | deps | phase | reconciles | acceptance |
|---|---|---|---|---|---|---|
| PROD-0 | Premium product definition + differentiation charter | 🟠+🔵 | — | Foundation | NEW | `docs/marketing/PREMIUM_PRODUCT_DEF.md` states exactly how `$39` indicator differs from free `wave1_signals.pine` (alerts/multi-TF/confluence/invite-only) OR the funnel terminus is reworded to "free indicator + waitlist for future premium". Until merged: every CTA + SoftwareApplication schema (SEO-3) says "waitlist for premium", not "buy now". |

### 4.1 SEO & Keyword Architecture

Mission: own organic search across u2algo.com + bot.u2algo.com; make the free TV indicator the EN-first SEO funnel entry; supersede P-002 M10.

| id | title | owner | deps | phase | reconciles | acceptance (compressed) |
|---|---|---|---|---|---|---|
| SEO-1 | EN-first keyword-cluster map + Manus RACI | 🔵 | — | Foundation | M10 | `SEO_KEYWORD_MAP.md` ≥9 clusters, ≥40 keywords, TR cluster ≥6, RACI zero-ambiguous, EN-first PIVOT note. **Canonical Manus-SEO doc** (SD-7/WEB-9/GROW-3 reference, not duplicate). |
| SEO-2 | Domain + indexability architecture spec | 🔵 | SEO-1 | Foundation | M12 | `SEO_DOMAIN_ARCHITECTURE.md` per-host table; auth app stays noindex post-migration; staging noindex; self-canonicals. |
| SEO-3 | Technical-SEO retrofit (JSON-LD + hreflang + canonical AUDIT) | 🟢 | SEO-1, SEO-2, **SD-1**, **PROD-0**, **CMP-3** | QuickWins | M10 | Org/SoftwareApplication/FAQ/Breadcrumb JSON-LD; Rich Results 0 err; **AUDIT canonicals (all 5 already have 1 — confirm, don't blindly add)**; sameAs uses FINAL handles (dep SD-1); `$39` only if PROD-0 defines premium else "waitlist"; Lighthouse SEO ≥95. |
| SEO-4 | EN/TR locale split + sitemap/robots upgrade | 🟢 | SEO-2, SEO-3, SEO-5, **EN-MASTER** | ContentMachine | M10 | EN x-default served; TR `/tr` hreflang bidirectional; sitemap validates + hreflang alternates; no 404 stubs. |
| SEO-5 | 8 pillar briefs + supporting-page map | 🔵 | SEO-1 | ContentMachine | M10 | `SEO_PILLAR_BRIEFS.md` 8 pillars + ≥10 supporting; pillar #5 conservative-proof-gated; pillar #6 = free-TV-indicator entry. |
| SEO-6 | Internal-linking map + CWV + tech checklist + **live cross-page CTA fixes** | 🔵 | SEO-3, SEO-5 | ContentMachine | M10 | Hub-spoke graph no orphan; **diff to 5 LIVE pages: premium.html→#waitlist, quickstart→home/waitlist** (DevEx HIGH); measured CWV recorded. |
| SEO-7 | Rank-tracking sheet (GSC/Bing merged into WEB-10) | 🟠 | SEO-2, SEO-4 | QuickWins | M15 | Rank sheet ≥30 keywords + baseline. **GSC/Bing verification deduped → WEB-10 owns it.** |
| SEO-8 | graphify dept/task indexing + gstack SEO-review gate | 🔵 | SEO-1, SEO-5 | Foundation | NEW | SEO dept + tasks queryable in graphify-out/; `SEO_REVIEW_GATE.md` 7-item gstack check; gate cited in SEO-3/SEO-4. |

KPIs: organic impressions (branded/long-tail baseline first — NOT +50% head-term, governance HIGH); indexed dashboard pages = 0; avg position branded keywords; Rich-result 0-err; CWV pass; organic→waitlist attribution.
Risks: EN pivot drops TR impressions (mitigate: bidirectional hreflang, one sitemap); staging duplicate-content (mitigate: SEO-2 noindex); Manus auto-meta conflict (mitigate: SEO-1 RACI, hand-built canonical sole source).

### 4.2 Content & Creative (Higgsfield PAID)

Mission: draft-only compliance-gated video+copy line; EN-first; conservative proof; never auto-publish. Reconcile M6/M7.

| id | title | owner | deps | phase | reconciles | acceptance (compressed) |
|---|---|---|---|---|---|---|
| CON-1 | Creative brand+compliance spec (incl. BRAND-token reconcile) | 🔵 | — | Foundation | M7 | `CREATIVE_SPEC.md`: **resolved bg token (Design HIGH: BRAND.md #050510 vs live #000000 — pick one), BOTH gradients (logo #0EA5E9→#6366F1→#7C3AED + accent #00f0ff→#0080ff→#a855f7) with non-overlap roles**, disclaimer card, EN-first rule, shipped-feature allowlist (OB/FVG/EQH-EQL/Breaker), forbid "CHoCH/BOS drawn" (#221), u² wordmark + pronunciation. |
| CON-2 | Higgsfield MCP runbook (**15s-segment reality**) | 🔵 | CON-1 | Foundation | M7 | `higgsfield-production.md`: balance preflight + **per-batch get_cost ABORT threshold (budget HIGH)**; **each video = N×≤15s segments + named external stitch (ffmpeg/CapCut)**; default model **Kling 3.0 ~6cr**, Seedance/Veo hero-only; 1 dry-run media_id logged; no publish tool. |
| CON-3 | Per-channel format + delivery matrix | 🔵 | CON-1 | Foundation | M7 | 5 surfaces res/aspect/duration/caption/disclaimer-safe-area; reframe targets feed CON-2. |
| CON-4 | Hero brief 30s (= 2-3 segments) | 🔵 | CON-1,2,3 | QuickWins | M7 | Beat sheet+VO+CTA+per-beat prompts; **`has_disclaimer(...,'en')==True`** (corrected from 'both'); 0 $; 0 win-rate %. |
| CON-5 | Demo brief 45-60s (screen-record, $0 Higgsfield) | 🔵 | CON-1,2,3 | QuickWins | M7 | Shipped-feature labels (no CHoCH/BOS); dashboard segment excludes $; **films against u2algo.com until migration lands** (governance HIGH). |
| CON-6 | Edu brief "What is an Order Block?" 60-90s | 🔵 | CON-1,2,3 | QuickWins | M7 | Episode skeleton; education-only (no trade call); compliance 0-violation. |
| CON-7 | EN copy templates (landing hero + pillar intros + captions) | 🔵 | CON-1 | QuickWins | M6 | EN hero preserves live voice devices (do/don't panel, "proof not promise"); price token only if PROD-0; compliance 0. |
| CON-8 | Video-script compliance harness (extend, don't rebuild) | 🟢 | CON-1, CON-4, **CMP-3** | ContentMachine | M6 | Imports `find_violations/has_disclaimer` from content_compliance; **rename queue label "compliance PASS"→"script-text PASS"** (CSO HIGH); tests green. |
| CON-9 | Render+queue 3 first videos via Higgsfield | 🔵 | CON-2,4,5,6,8 | ContentMachine | M7 | 3 masters + reframes, media_ids + credits logged; **approval-queue entry requires human visual-QC attestation** (no on-screen $/CHoCH/fabricated overlay) — CON-8 text gate alone insufficient; zero publish. |
| CON-10 | Content calendar + cadence | 🔵 | CON-6,7,9 | Scale | M7 | Weekly grid + loop + edu backlog ≥4; **snapshot template cites exact proof file+schema** (see §8 proof-artifact map); no $. |

KPIs: TOFU reach; CTR to u2algo.com; waitlist conv per 1k views; hook retention; throughput vs cadence; compliance pass-rate 100%; Higgsfield credit efficiency.
Risks: fabricated chart overlay (#221-class) → real TV captures only + human visual-QC; draft leak → no publish tool + approval queue; PAID credit overrun → Kling default + get_cost abort; voice drift → CON-7 reconcile live voice.

### 4.3 Social & Distribution

Mission: 1 pillar → N derivatives; EN-first; Manus FREE-start manual-approval; never touch operator alerter. Reconcile M3/M6/M8/M13/M14/T-018.

| id | title | owner | deps | phase | reconciles | acceptance (compressed) |
|---|---|---|---|---|---|---|
| SD-1 | Channel-handle consolidation + brand audit | 🔵 | — | Foundation | NEW | `channel-registry.md` canonical handles; draft site link-string diff; **handle rename operator-gated**; no copy claims unclaimed handle. **(SEO-3 depends on this.)** |
| SD-2 | Repurposing matrix 1→N EN-first | 🔵 | SD-1 | Foundation | M6 | 4 pillars × derivative list; **audit+scrub launch-assets `efloud` leak (6×) before mapping as TR-derivative** (CSO/recon MED); pivot note. |
| SD-3 | Manus REST client + IG/FB templates (fail-safe flag-OFF) | 🟢 | SD-2, **MANUS-CAP** | QuickWins | M3 | Key-absent no-op test; templates reject banned-phrase/$ via content_compliance; no publish path; `backend/social/templates/`. |
| SD-4 | X build-in-public draft→approve→manual | 🟢 | SD-3 | QuickWins | M13 | 10 EN draft threads; aggregate-only (no per-trade entry/SL/TP); **manual-post only on X free tier** (no xurl write-automation, budget MED). |
| SD-5 | Telegram community + snapshot (separate customer token) | 🟢 | SD-2 | QuickWins | T-018 | `telegram_digest.py` aggregate-only; double-gated default-OFF; **uses `EFLOUD_CUSTOMER_TG_*` NOT operator alerter**; regression asserts ops/alerter untouched. |
| SD-6 | YouTube 2/wk structure + Shorts | 🟢 | SD-3, SD-2 | ContentMachine | M14 | **YT longs = screen-record, $0 Higgsfield** (budget MED); templates w/ disclaimer+UTM; draft-mode only. |
| SD-7 | Manus-SEO scope (Social slice) | 🔵 | SD-1 | Foundation | M10 | **References canonical SEO-1 RACI**; covers only social-profile SEO/link-in-bio; no full-matrix duplicate. |
| SD-8 | Manual-approval queue (no auto-publish) | 🟢 | SD-3 | QuickWins | M6 | `social_queue.py` list/show/approve/reject; **approve action HARD-calls `find_violations()==[]` AND `has_disclaimer(<lang>)` (reject not warn)** (governance CRIT/HIGH); no auto-transition to posted. |
| SD-9 | Distribution KPI tracker (**merged into single KPI routine**) | 🟢 | KPI-ROUTINE | ContentMachine | M15 | **Collapsed → one weekly KPI routine** (see KPI-ROUTINE); X metrics MANUAL-ENTRY on free tier (budget MED); read-only Supabase; no $. |
| SD-10 | Content-calendar engine | 🟢 | SD-8, SD-2 | Scale | M6 | `social_calendar.py` emits week of DRAFT slots to SD-8 queue; EN/TR split; none auto-posted. |

KPIs: waitlist by utm_source; conv per channel; follower growth; cadence adherence; repurposing leverage ≥6; compliance pass 100%; approval latency.
Risks: signal-service leak (aggregate-only tests); auto-publish slip (SD-8 single sink); secret leak (gitleaks + no-op design); customer-TG reuses ops token (separate namespace + regression).

### 4.4 Web & Technical Infrastructure

Mission: domain/hosting/TLS/measurement. Migrate prod dashboard to bot.u2algo.com, repoint old host to staging, stand up u2algo.com. Trade path untouched. **OWNS the single analytics+UTM+event layer** (DevEx/recon HIGH — dedups GROW-2/3).

| id | title | owner | deps | phase | reconciles | acceptance (compressed) |
|---|---|---|---|---|---|---|
| WEB-1 | Domain migration runbook (doc-only, operator-gated) | 🔵 | — | **EXTRACTED** | M12 | `2026-domain-migration.md` numbered cutover+rollback (<5min); risk-ops review. **Off marketing critical path** (governance HIGH). |
| WEB-2 | Stand up u2algo.com on Railway + DNS + TLS | 🟢 | **SITE-SOT** | Foundation | M12 | apex+www TLS; www→apex 301; `SITE_URL=https://u2algo.com`; no railway.app leak. **Only true marketing prerequisite.** |
| WEB-3a | Webhook URL + waitlist origin rebind | 🟢 | WEB-2, **LS-FLIP** | QuickWins | T-016 | LS webhook→u2algo.com/api/purchase-webhook; valid-sig accept + bad-sig 401; **requires operator `LS_WEBHOOK_ENABLED=true` flip sequenced first** (verified 503-by-default). |
| WEB-3b | Email domain auth SPF/DKIM/DMARC + live send | 🟢 | WEB-2 | QuickWins | T-016 | SPF+DKIM+DMARC for u2algo.com; **live test send to Gmail/Outlook (not just mail-tester)**; gates T-016 email go-live. |
| WEB-4 | Repoint bot.ualgotrade.com → STAGING + human redirect | 🟠 | WEB-1 | **EXTRACTED** | NEW | Staging config NOT phase2_1k (`dry_run:true` asserted); noindex; STAGING marker; **301/interstitial for humans who bookmarked old host** (DevEx MED). |
| WEB-5 | Analytics Plausible+GA4 consent-gated (flag-OFF) | 🟢 | WEB-2 | QuickWins | M9 | Both snippets behind `ANALYTICS_ENABLED` default-OFF; GA4 post-consent only (T-011 KVKK); IDs env-driven; privacy.html discloses. **Sole analytics owner.** |
| WEB-6 | Funnel events incl. **checkout/purchase** | 🟢 | WEB-5 | QuickWins | M15 | visit/cta_click/waitlist_submit/proof_view + **checkout_click/purchase_complete (join server.js:247 LS webhook)** (DevEx/recon HIGH — T-015/T-016 orphan fix); `analytics.js` no-ops flag-OFF; `funnel-events.md`. |
| WEB-7 | Dashboard noindex guard + domain-drift smoke | 🔵 | WEB-2, WEB-3a | QuickWins | M10 | Smoke fails on stale `ualgotrade.com`/`railway.app` in HTML/sitemap; `bot.u2algo.com` X-Robots-Tag noindex; layout.tsx noindex assertion. |
| WEB-8 | Rebind STATUS_PAGE_URL + uptime monitor | 🟢 | WEB-3a, WEB-4 | QuickWins | T-021 | Probes prod+staging healthz; distinguishes 200 vs 503-breaker (no false page); `.env.example` updated. |
| WEB-9 | Manus-SEO boundary (Web slice: canonical conflict) | 🔵 | WEB-2 | QuickWins | M10 | **References SEO-1 canonical doc**; resolves canonical-conflict (single source); only Web-specific DNS/canonical slice. |
| WEB-10 | GSC + Bing verification both properties (**SEO-7 merged in**) | 🟠 | WEB-9, WEB-7 | ContentMachine | M10 | u2algo.com verified + sitemap 0-err; bot.u2algo.com branded property, dashboard excluded-by-noindex; DNS TXT recorded. |
| WEB-3c | Harden /api/waitlist (CORS+rate-limit+honeypot) | 🟢 | WEB-2 | QuickWins | NEW | Restrict `access-control-allow-origin` to known apex for /api/waitlist; per-IP rate-limit; honeypot; server-side referer bound (CSO MED — protects CAC attribution integrity). |

KPIs: cutover <5min downtime, 0 trade incidents; all hosts valid TLS + correct noindex + 0 stale-domain leaks; funnel measurable; Lighthouse SEO ≥90; LS+waitlist+email green on new domain; uptime 200 vs 503 distinguished.
Risks: cutover downtime (TLS-before-DNS, <5min revert); LS webhook silent break (3a test + operator LS test-purchase); GA4 pre-consent (post-consent load + flag-OFF); Manus canonical conflict (WEB-9 single source); staging on mainnet config (WEB-4 asserts NOT phase2_1k).

### 4.5 Compliance & Legal

Mission: guardrails that GATE every dept. Bilingual disclaimer library, Meta/YT/X policy matrix, EXTEND content_compliance.py. Reconcile P-003 W0.

| id | title | owner | deps | phase | reconciles | acceptance (compressed) |
|---|---|---|---|---|---|---|
| CMP-1 | Bilingual disclaimer library + **live-string reconcile** | 🔵 | — | Foundation | T-010 | `disclaimer-library.md` 6 blocks × EN/TR × long/short/social; EN byte-match COMPLIANCE_EN; **reconcile live HTML short-form drift to constant OR widen has_disclaimer variant set** (CSO HIGH, verified live fails today). |
| CMP-2 | Promo-policy matrix Meta+YT+X | 🔵 | CMP-1 | Foundation | NEW | ≥12 banned + ≥8 approved EN+TR mapped to violation tags. |
| CMP-3 | Extend content_compliance.py: **BANNED_EN + price-whitelist + testnet-label** (TDD) | 🟢 | CMP-1, CMP-2 | **Foundation (pulled up)** | M6 | Add `BANNED_EN_PHRASES` (full CMP-2 matrix); **PRICE_WHITELIST so `$39 lifetime` passes while $-PnL fails**; `unlabeled_simulation` tag; **optional `lang` param on `find_violations` ONLY — do NOT touch `has_disclaimer` (already supports en/both)**; backward-compat regression. **HARD blocker for every EN-copy task.** |
| CMP-4 | Conservative-proof rule + code enforcement + **return_pct decision** | 🟢 | CMP-3 | QuickWins | T-012 | Whitelist (win-rate%/R:R/PF/max-DD%); **decide signed `return_pct` status — live premium_proof.json publishes -5.3% which trips gate + is outside whitelist (VERIFY)**; `proof_mode` flag; **bind to GROW-8 `proof_milestone.json` single-source-of-truth** (CSO MED). |
| CMP-5 | Wire disclaimer library into live pages + risk-disclosure.html | 🟢 | CMP-1 | QuickWins | T-010 | premium/quickstart NFA+Risk+Proof≠Product; new `risk-disclosure.html` linked; PR body states canonical source (SITE-SOT). |
| CMP-6 | KVKK/GDPR consent + **full sub-processor map** | 🔵 | CMP-1 | Foundation | T-011 | Consent copy EN+TR; **enumerate ALL new processors (Manus, Higgsfield, GA4-US, Plausible, Resend) data-residency + cross-border** (CSO MED — not just Supabase). |
| CMP-7 | Compliance gate hook into draft queue | 🟢 | CMP-3, CMP-4 | ContentMachine | M6 | Gate rejects violation/missing-disclaimer pre-queue; `check_draft.py` CLI; **mandatory on manual path (SD-8/CON-9), not advisory** (governance HIGH). |
| CMP-8 | Channel publish checklist + generated-media gate | 🔵 | CMP-2, CMP-3 | ContentMachine | M13 | 4 channels + Higgsfield/Manus media; [BACKTEST]-label rule; **human visual-QC for burned-in pixels** (text gate can't see pixels); Manus copy through compliance before live. |
| CMP-9 | Quarterly audit + proof_mode flip + breach-response | 🔵 | CMP-3,4,5,8 | Scale | T-023 | `audit-log.md`; 90-day proof_mode flip operator-gated; **add `breach-response.md` incident runbook** (CSO LOW); secret-scan spot-check (gitleaks already in CI). |

KPIs: 100% drafts pass gate pre-queue; 0 banned-claim published; 100% live pages render disclaimer; 0 $/per-trade pre-90-day; 0 unmapped banned patterns; quarterly audit on schedule.
Risks: EN enforcement gap (CMP-3 front); policy drift (CMP-9 quarterly); proof overreach (CMP-4 proof_mode); vendored-copy stale (CMP-5 canonical-source); disclaimer drift (CMP-1 byte-pin + reconcile).

### 4.6 Growth, Analytics & KPI

Mission: measurement + decision gates. Instrument funnel, weekly KPI report, enforce CAC gate + A/B significance + 90-day proof gate. Reconcile M15 + P-003 W1.

| id | title | owner | deps | phase | reconciles | acceptance (compressed) |
|---|---|---|---|---|---|---|
| GROW-1 | Funnel KPI dictionary + measurement-before-spend + **purchase path** | 🔵 | — | Foundation | M15 | ≥10 metrics formula/source/cadence; per-channel + EN/TR; CAC-gate thresholds (≥14d, ≥300 sessions); **parallel direct-to-premium path + purchase-CAC** (DevEx HIGH); break-even rule (credit spend recoverable at $39×customers). |
| GROW-2 | UTM scheme + waitlist source capture (server.js:280 fix) | 🟢 | GROW-1, **WEB-6** | Foundation | T-011 | Real `source` persisted (replaces hardcoded `'u2algo-site'`); consent gate intact; 3-fallback 200; additive nullable column. **Consumes WEB-6 event layer** (not re-implement). |
| GROW-3 | ~~Analytics standup~~ → **consume WEB-5** | 🟢 | **WEB-5** | QuickWins | M10 | **Collapsed: consume WEB-5 Plausible/GA4** (DevEx/recon HIGH dedup). Only `analytics-vs-manus-seo.md` slice → references SEO-1. |
| GROW-4 → KPI-ROUTINE | **Single weekly KPI routine** (standalone, no Binance, customer token) | 🟢 | GROW-2, WEB-6 | QuickWins | M15 | **`scripts/growth/kpi_report.py` standalone runner — NO `make_future_client`, asserts no ccxt.binance + no BINANCE_* read** (recon HIGH); **uses `EFLOUD_CUSTOMER_TG_*` NOT AlertRouter.from_env()** (verified trade-channel contradiction); `state/kpi_weekly.json` no $ pre-milestone; flag-OFF no-op. **Absorbs SD-9 + WEB-11.** |
| GROW-5 | CAC gate enforcement + state file | 🔵 | KPI-ROUTINE | QuickWins | M15 | `cac_gate.json` `gate_open` true only when ≥14d AND ≥300 sessions AND non-zero conversion; runbook; every paid task cites green gate. **No Binance client.** |
| GROW-6 | KPI dashboard schema + operator read-out | 🟢 | KPI-ROUTINE, GROW-5 | ContentMachine | M15 | Schema + noindex static `ops/kpi.html` OR sheet; $ columns null pre-milestone; not in sitemap. |
| GROW-7 | A/B framework + significance gate (+ **proof-block experiment**) | 🔵 | GROW-2, GROW-6 | Scale | NEW | `ab-framework.md` 3 pre-registered + **4th: proof-block presentation** (DevEx MED); z-test helper `insufficient_sample` below n; one experiment at a time. |
| GROW-8 | 90-day proof milestone + unlock gate (**corrected unlock**) | 🔵 | GROW-1 | ContentMachine | M15 | `proof_milestone_gate.py` reads `proof_snapshot.json`; `milestone_reached=false` today; **unlock = dollar-PnL CLAIMS, NOT "premium product" (premium already live — DevEx/recon HIGH correction)**; binds CMP-4 proof_mode. |
| GROW-9 | Keyword-attribution join | 🔵 | KPI-ROUTINE, SEO-handoff | ContentMachine | M15 | `utm_campaign=cluster-slug`; per-cluster conv table EN/TR; rides GROW-2 UTM. |

KPIs: North-Star visit→waitlist % (≥3% organic benchmark); waitlist→customer % (post-milestone); CAC computable before paid; per-channel + EN/TR split; CTR; retention/churn; time-to-90-day; A/B lift; CAC-gate status; report delivery health.
Risks: vanity metrics (North-Star = conversion); attribution blindness (GROW-2 UTM); premature paid spend (GROW-5 machine gate); proof overreach (GROW-8 milestone); A/B false positive (pre-registered n + z-test); trade-path touch (standalone runner, no Binance — recon HIGH); Manus overlap (GROW-3 collapse + GROW-9 single join key).

### 4.7 ADS — Paid Acquisition / Google Ads (NEW, owner 🟣 @gemini, CAC-GATED)

Mission: stand up paid-acquisition READINESS now (policy feasibility, account, conversion tracking, campaign blueprint, policy-compliant ad copy); **ZERO live spend until GATE 2 CAC opens AND a CPA target tied to `$39` LTV is set.** Concretizes the "paid ads" deferral in P-002 M15 + GROW-5. Delegated to @gemini (separate AI session; same git-push + sha256 handoff discipline as Hermes; @claude reviews).

| id | title | owner | deps | phase | reconciles | acceptance (compressed) |
|---|---|---|---|---|---|---|
| ADS-0 | **Google Ads policy feasibility** (crypto/financial-products) | 🟣 | — | Foundation | NEW | `docs/marketing/google-ads-feasibility.md`: can a SMC indicator / trading-bot be advertised on Google Ads per region (EU/US/TR/global)? Google restricts crypto, "trading signals", get-rich/complex-speculative-financial + may require advertiser certification. **GO / NO-GO / RESTRICTED verdict per region BEFORE any campaign build.** If NO-GO, pivot budget to the channels that allow it (YouTube organic, X, TG). |
| ADS-1 | Account structure + conversion tracking | 🟣 | WEB-6 | QuickWins | M15 | GA4 conversion import; conversion actions = `waitlist_submit` + `purchase_complete` (WEB-6 events, single source); no spend; doc-only. |
| ADS-2 | Search-campaign blueprint + keyword/negatives | 🟣 | SEO-1, ADS-0 | QuickWins | M15 | branded + commercial clusters → ad groups; match types; negative-kw list; **flags SMC/ICT head-term saturation + CPC reality** (governance HIGH). |
| ADS-3 | Policy-compliant RSA ad copy (EN-first) | 🟣 | CMP-2, CMP-3, ADS-0 | QuickWins | M6 | RSA headlines/descriptions pass `content_compliance` rules (no profit-guarantee, conservative-proof, disclaimer on landing) AND Google financial-products policy; routed through the SAME compliance gate as all copy. |
| ADS-4 | Budget/bid + **CAC-gate interlock** | 🟣 | GROW-5, ADS-1 | Scale | M15 | CPA target ≤ f(`$39` LTV); **ads go live ONLY after `cac_gate.json gate_open=true`**; daily cap; kill-switch; operator spend sign-off. |
| ADS-5 | Landing alignment + paid UTM | 🟣 | ADS-2, SEO-5 | Scale | M15 | ad → pillar-page message-match; `utm_medium=paid` tagged (feeds GROW-2/GROW-9); conversion path verified pre-launch. |

KPIs: policy-GO regions; conversion tracking accuracy; quality score; CPC vs forecast; paid CAC vs $39 LTV; paid vs organic conversion delta. Risks: **Google crypto/financial policy NO-GO (ADS-0 first — may kill the channel)**; CPC unaffordable in saturated niche (ADS-2 flags, branded-only fallback); spend before CAC proven (ADS-4 hard interlock); ad copy policy-strike (ADS-3 dual-gate).

---

## 5. SEO Appendix

### 5.1 Keyword Cluster → Page → Domain → Intent → Funnel
| Cluster | Domain | Intent | Funnel | Example head keywords | Target page |
|---|---|---|---|---|---|
| Smart Money Concepts education | u2algo.com | informational | TOFU | smart money concepts, smc trading explained, smc strategy | Pillar #1 /en/smart-money-concepts |
| SMC/ICT bot & automation | u2algo.com | commercial | MOFU | smc trading bot, ict algo trading bot, smc strategy automation | Pillar #2 /en/smc-trading-bot |
| Order Block / FVG indicators | u2algo.com→premium | commercial | BOFU | order block indicator tradingview, fvg indicator, best order block indicator | Pillar #3 /en/order-block-indicator |
| ICT concepts | u2algo.com | informational | TOFU | ict trading, ict order blocks, ict vs smc, liquidity sweep ict | Pillar #4 /en/ict-algo-trading |
| Transparent track record | u2algo.com | commercial | MOFU | verified trading bot results, honest crypto trading bot, build in public | Pillar #5 /en/track-record (%/shape only) |
| Free TV SMC indicator | u2algo.com | commercial/branded | BOFU/entry | tradingview smc indicator, free smc indicator, u2algo indicator | Pillar #6 /en/tradingview-smc-indicator |
| u2algo brand + dashboard | both | branded | BOFU | u2algo, u2algo bot, u2algo dashboard, u2algo login, u2algo review | Pillar #7 bot.u2algo.com landing + home |
| SMC risk management | u2algo.com | informational | MOFU | smc risk management, drawdown control trading bot, r:r based crypto strategy | Pillar #8 /en/smc-strategy-automation |
| Long-tail spokes | u2algo.com | informational | — | fair value gap vs order block, best timeframe for smc, breaker block explained | Supporting (10-15) |
| TR secondary (/tr hreflang) | u2algo.com | informational | — | smart money concepts nedir, order block gostergesi, tradingview smc indikator | /tr mirrors of pillars 1/3/6 |

**Near-term reality (governance HIGH):** SMC/ICT head terms are saturated (LuxAlgo-class authority). First 90 days target ONLY branded + long-tail + TradingView-internal discovery (the published free indicator's TV script page is the one channel with a built-in audience). Head-term pillars 1-4 = 6-12 month compounding bet. SEO-1 KPI corrected to branded/long-tail baseline.

### 5.2 Manus.im SEO vs Hand-built (canonical RACI — SEO-1 owns; SD-7/WEB-9/GROW-3 reference)
| Concern | Manus.im owns | Hand-built (us) | Overlap → coordinate |
|---|---|---|---|
| DNS/registrar config | ✅ | | |
| XML sitemap submission to GSC/Bing | ✅ submits | ✅ we own canonical `sitemap.xml` | Manus submits OUR file |
| Baseline meta/title generation | suggests | ✅ all `<head>` final | **MANUS-CAP: confirm Manus does NOT auto-write `<head>` (blocking)** |
| Keyword-suggestion feed | ✅ | | |
| JSON-LD schema | | ✅ all (Org/SoftwareApp/FAQ/Breadcrumb) | |
| hreflang EN/TR | | ✅ | |
| Pillar/supporting IA + internal-linking | | ✅ | |
| Editorial briefs/copy | generic (rejected) | ✅ all (compliance-gated) | Manus copy → content_compliance before publish |
| Social-profile SEO / link-in-bio | ✅ | | SD-7 slice |

---

## 6. 4-Phase Roadmap

Gates are HARD: a phase's tasks do not start until the prior gate passes.

### Phase 1 — Foundation (specs, blockers, gates defined)
Dependency order:
1. **SITE-SOT** (NEW blocker) — resolve u2algo-site deploy source-of-truth (repo vs vendored Railway copy). **Blocks every site PR** (recon HIGH).
2. **MANUS-CAP** (NEW blocker, 🟠) — operator confirms in writing: Manus cannot auto-publish + whether it writes `<head>`. Blocks SD-3, SEO-3 merge.
3. **LS-FLIP** (NEW, 🟠) — operator `LS_WEBHOOK_ENABLED=true` + LS test-purchase. Blocks WEB-3a.
4. PROD-0 (premium definition) → SEO-1 → SEO-2, SEO-8 · SD-1 → SD-2, SD-7 · CON-1 → CON-2, CON-3 · CMP-1 → CMP-2 → **CMP-3 (pulled up)** → CMP-4 · CMP-6 · GROW-1 → GROW-2 · WEB-2 (after SITE-SOT).
5. WEB-1 (migration runbook, EXTRACTED — runs parallel, off critical path).

**GATE 1 → QuickWins:** SITE-SOT resolved · MANUS-CAP confirmed · CMP-3 merged + verified (EN banned + price-whitelist) · PROD-0 decided · u2algo.com (WEB-2) live with TLS.

### Phase 2 — QuickWins (thin spine that proves the funnel)
Order: WEB-5 → WEB-6 → GROW-2 (consume) · WEB-3a (after LS-FLIP), WEB-3b, WEB-3c · WEB-7, WEB-8 · SEO-3 (after SD-1+PROD-0+CMP-3), SEO-7 · CON-4, CON-5, CON-6, CON-7 · SD-3 (after MANUS-CAP), SD-4, SD-5, SD-8 · CMP-5 · **KPI-ROUTINE → GROW-5 (CAC gate)** · WEB-9.

**GATE 2 → ContentMachine (CAC GATE):** `cac_gate.json gate_open=true` requires ≥14 days AND ≥300 organic sessions AND a measured non-zero visit→waitlist conversion. **All ContentMachine/Scale tasks BLOCKED until this first reports non-zero conversion** (CEO HIGH — boil the lake, don't build it upfront). First Higgsfield batch runs on free 887 Plus credits (Kling-only) to seed.

### Phase 3 — ContentMachine (scale content once funnel proven)
SEO-4, SEO-5, SEO-6 · CON-8, CON-9 (3 videos) · SD-6, SD-9(→KPI-ROUTINE) · CMP-7, CMP-8 · GROW-6, GROW-8, GROW-9 · WEB-10.

**GATE 3 → Scale (90-DAY PROOF GATE):** `proof_milestone.json milestone_reached=true` (≥90 consecutive days closed-trade history + ≥N trades, operator-set). Unlocks dollar-PnL CLAIMS (not the product). Bound to CMP-4 proof_mode. Operator sign-off recorded in gate file. **Higgsfield top-up/Ultra upgrade gated on same CAC signal.**

### Phase 4 — Scale (repeatable engine + paid only after CAC justifies)
CON-10 · SD-10 · GROW-7 (A/B incl. proof-block) · CMP-9 (quarterly) · **ADS-4/ADS-5 (Gemini — Google Ads go-live, ONLY after CAC gate green + CPA ≤ $39-LTV + ADS-0 region GO + operator spend sign-off)**.
*(ADS prep — ADS-0 feasibility / ADS-1 tracking / ADS-2 blueprint / ADS-3 copy — runs in parallel during Foundation/QuickWins; only ADS-4/5 SPEND is Scale-gated.)*

**Bot-dashboard migration (WEB-1/WEB-4/WEB-8)** — standalone ops change, NOT gated by marketing phases. Requires: efloud-risk-ops-reviewer sign-off + quiet/flat-book trading window + LS test-purchase verification. Runs whenever operator schedules.

---

## 7. Governance & Verify Resolution

| # | Finding (sev) | Lens | Resolution |
|---|---|---|---|
| 1 | Premium product undefined; only proof is LOSING (CRIT) | CEO/DevEx | **PROD-0** defines or reframes to "free+waitlist"; SEO-3/CON-4 CTA gated on it. Proof-readiness gate (GROW-8) before any proof_view traffic. |
| 2 | EN compliance hole — gate is TR-only (CRIT) | CSO/Verify | **CMP-3 pulled to Foundation**, HARD blocker for all EN-copy tasks; `BANNED_EN_PHRASES` full CMP-2 matrix + per-phrase regression. Empirically verified leak. |
| 3 | Negative proof = sales liability funneled INTO (CRIT) | DevEx | GROW-8 proof-readiness gate; CMP-4 decides return_pct; SEO-5 pillar #5 + CON-4/5 blocked until metrics pass credibility bar. |
| 4 | Scope bloat — measurement machine before traffic (HIGH) | CEO | GATE 2 CAC gate blocks all ContentMachine/Scale until non-zero conversion. Thin QuickWins spine first. Build 2 pillars not 8 initially. |
| 5 | SEO timeline KPIs unrealistic (HIGH) | CEO | SEO-1 KPI → branded/long-tail baseline; head-term = 6-12mo bet; TV indicator page = primary near-term channel. |
| 6 | LIVE dashboard migration on marketing critical path (HIGH) | CEO/recon | WEB-1/4/8 EXTRACTED; only WEB-2 (u2algo.com) is marketing prereq; CON-5 films u2algo.com until migration. |
| 7 | Cold-start / first-100-users missing (HIGH) | CEO | Add to SD-2/SD-1: TradingView script-library engagement + EN SMC community participation = realistic first-100 path; TV indicator page tied to waitlist. |
| 8 | GROW-4 spams operator trade-alert channel (HIGH) | Eng/recon | KPI-ROUTINE uses `EFLOUD_CUSTOMER_TG_*` not `AlertRouter.from_env()`; regression asserts never resolves to `EFLOUD_TELEGRAM_CHAT_ID`. Verified `_alert.py:21-22`. |
| 9 | KPI routine couples to live Binance client (HIGH) | Eng/recon | KPI-ROUTINE standalone runner, no `make_future_client`; test asserts no ccxt.binance + no BINANCE_* read. Verified `_base.py:20-26`. |
| 10 | Analytics triple-planned (WEB-5/GROW-3, WEB-6/GROW-2, SD-9) (HIGH) | DevEx/recon | WEB owns analytics+UTM+event layer; GROW-3 collapses to consume WEB-5; SD-9→KPI-ROUTINE; explicit dep edges. |
| 11 | 4× duplicate Manus-SEO docs (HIGH) | recon | SEO-1 RACI canonical; SD-7/WEB-9/GROW-3 reference + dept-slice only. |
| 12 | GSC submission planned 2× (SEO-7/WEB-10) (HIGH) | recon | WEB-10 owns GSC/Bing verification; SEO-7 keeps only rank-tracking sheet. |
| 13 | 3× weekly KPI routine (HIGH) | recon | One KPI-ROUTINE; SD-9/WEB-11 absorbed. |
| 14 | Orphan: T-015/T-016 $39 purchase funnel (HIGH) | DevEx/recon | WEB-6 adds checkout/purchase events; GROW-1 direct-to-premium path; GROW-8 unlock corrected. |
| 15 | Orphan: T-023 secret-scan "missing" (HIGH, CSO) | Verify | **FALSE — gitleaks IS in ci.yml:109-119**. No re-implementation. Residual: scan is working-tree-only (documented). |
| 16 | u2algo-site source-of-truth unresolved (HIGH) | recon/Eng | SITE-SOT Foundation blocker before any site PR. |
| 17 | $39 price false-rejected by gate (HIGH) | CSO/Verify | CMP-3 PRICE_WHITELIST; regression `$39 lifetime` passes, `$250 trade`/`balance $1000` fail. |
| 18 | has_disclaimer 'both' impossible for EN assets (HIGH) | CSO/Verify | CON-4→`'en'`; CMP-3 leaves has_disclaimer untouched (already supports en/both). |
| 19 | Live disclaimer drift from constant (HIGH) | CSO/Verify | CMP-1 reconcile step (embed constant OR widen variant set) + render-parity test. |
| 20 | Manus auto-publish/auto-meta unresolved (HIGH) | CSO/Verify | MANUS-CAP Foundation blocker; CMP-8 hard rule Manus copy→compliance+manual approval. |
| 21 | Generated-media pixels uncheck-able by text gate (HIGH) | CSO/Verify | CON-9/CMP-8 mandatory human visual-QC attestation; CON-8 label "script-text PASS". |

Deferred (with reason): A/B framework (GROW-7), 8 full pillars, content calendars (CON-10/SD-10) → Scale phase, gated on CAC. Higgsfield Ultra upgrade → gated on CAC signal. Bot migration → standalone ops window.

---

## 8. Reconciliation (new dept tasks → existing P-002 / P-003)

| Existing card | Status | Absorbed by |
|---|---|---|
| M3 (Manus connectors) | concretized | SD-3 |
| M6 (templates/approval) | concretized | CON-7, SD-8, CMP-7 |
| M7 (Higgsfield pipeline) | concretized | CON-1..CON-10 |
| M8 (Telegram binding) | concretized | SD-5 |
| M9 (web/measurement) | concretized + extended | WEB-5 (analytics = missing half) |
| M10 (SEO) | **superseded** | SEO-1..SEO-8, WEB-9/10 |
| M12 (DNS/Railway cutover) | concretized | WEB-1, WEB-2, WEB-4 |
| M13 (X draft→approve) | concretized | SD-4 |
| M14 (YouTube) | concretized | SD-6 |
| M15 (KPI) | concretized | KPI-ROUTINE, GROW-5/6/8/9 |
| T-010 (legal pages) | concretized | CMP-1, CMP-5 |
| T-011 (KVKK consent) | concretized | CMP-6, GROW-2 |
| T-012/T-014 (proof export) | referenced | GROW-8, CMP-4, SEO-5 pillar #5 |
| T-015/T-016 (entitlements/LS webhook) | orphan→absorbed | WEB-3a/3b, WEB-6, GROW-1 |
| T-018 (telegram notifier) | concretized | SD-5 |
| T-021 (uptime) | concretized | WEB-8 |
| T-023 (secret-scan CI) | **already done** (verified) | — (no new task; CMP-9 spot-check) |
| T-024 (healthz contract) | referenced | WEB-8 |
| M2 (TV chart-export lane) | orphan→prereq | named dep of CON-5/CON-9 (operator/Web to own) |
| M5 (C2 result-emitter) | orphan→prereq | named upstream dep of SD-4 |

**Genuinely NEW (no existing card):** PROD-0, SEO-8, WEB-4, WEB-3c, GROW-7, SD-1, CMP-2, and the 3 blockers (SITE-SOT, MANUS-CAP, LS-FLIP).

---

## 9. graphify + gstack Management Layer

### 9.1 graphify
- The dept/task graph is emitted to `graphify-out/` by SEO-8 (extend to all 6 depts).
- Query dependency questions instead of grepping: `graphify query "what blocks SEO-4"` · `graphify query "which tasks depend on CMP-3"` · `graphify query "all tasks touching u2algo-site"`.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture context.
- Every task node carries: id, owner, deps, phase, reconciles_with, invariants-touched. Edges = dependency + reconciliation.

### 9.2 gstack role-reviews per phase gate
| Phase gate | gstack role-review | What it checks |
|---|---|---|
| Foundation → QuickWins | **CSO/Compliance lens** | CMP-3 EN coverage, price-whitelist, disclaimer reconcile, MANUS-CAP confirmed |
| Foundation → QuickWins | **Eng/Feasibility lens** | SITE-SOT resolved, no Binance coupling in KPI routine, serialization owner for site PRs |
| QuickWins → ContentMachine (CAC) | **CEO/Strategy lens** | CAC gate non-zero conversion, scope not bloated ahead of data |
| QuickWins → ContentMachine | **SEO review gate (SEO-8)** | JSON-LD valid, hreflang valid, canonical present, no $-claim, dashboard noindex, Lighthouse ≥95 |
| ContentMachine → Scale (90-day) | **CSO + Growth lens** | proof_milestone bound to compliance proof_mode, conservative-proof intact |
| Any site PR | **Design/Brand lens** | brand-token consistency, no efloud leak, cross-surface coherence |
| Any trade-adjacent | **efloud-risk-ops-reviewer** | trade path untouched (mandatory on WEB-1/4 migration) |

Single-owner serialization: @hermes serializes all `u2algo-site` PRs (one merge queue, file-ownership map for the 5 HTML pages) to prevent conflicting additive diffs.

---

## 10. Open Questions for Operator

1. ~~**PROD-0:** Define the `$39` premium tier's differentiation, OR confirm funnel terminus = "free + waitlist".~~ ✅ **RESOLVED 2026-06-17 → "free + waitlist" reframe** (see §2.1b). SEO-3/CON-4 unblocked with the reframe.
2. **SITE-SOT:** Is `u2algo-site/` in this repo the Railway deploy source-of-truth, or a vendored copy? (Blocks all site PRs.)
3. **MANUS-CAP:** Does Manus.im auto-publish content or auto-write page `<head>`? Free-tier quotas for IG/FB automation + SEO export + DNS? (Blocks SD-3, SEO-3, GROW-9.)
4. ~~**Proof posture:** What does the proof block show while track record is NEGATIVE (-5.3% today)?~~ ✅ **RESOLVED 2026-06-17 → "research-log / build-in-public" reframe** (see §2.1b). Honest framing, dollar/positive claims gated to 90-day, traffic routed to education+indicator not proof block.
5. **Handles:** Rename `@Leblepito` YouTube to u2algo? Is `@u2algo` claimable on X/Telegram/YouTube? (Operator-gated; SEO-3 sameAs depends.)
6. **Higgsfield budget:** Workspace is PLUS / 887 credits. Confirm Kling-only first batch on free credits; cap monthly credits; gate Ultra upgrade on CAC.
7. **Telegram customer token:** Provision `EFLOUD_CUSTOMER_TG_*` (separate from operator alerter); when to flip `notifications.telegram.enabled` ON.
8. **CAC thresholds:** ≥14 days + ≥300 organic sessions right for low-volume SMC niche?
9. **90-day milestone:** Minimum closed-trade count (30? 50?) for non-noise metrics given conservative indicator-only entry frequency.
10. **A.S. legal details:** Name, MERSIS, address for jurisdiction/controller fields (CMP-1/CMP-6). Data-retention window + Supabase region for KVKK.
11. **LS-FLIP:** When to flip `LS_WEBHOOK_ENABLED=true` + run LS test-purchase (gates WEB-3a).
12. **Bot migration window:** When is the flat-book / quiet trading window for the bot.u2algo.com cutover (standalone ops change)?

---

*End of spec. Doc-only PLAN. No code, no DNS, no publish action taken. All implementation is per-task, behind the phase gates above, additive + flag-OFF + draft-only, trade path untouched.*
