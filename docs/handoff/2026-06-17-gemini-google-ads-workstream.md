# Gemini Handoff — u2algo Paid Acquisition / Google Ads (P-002.5 ADS workstream)

| Field | Value |
|---|---|
| Date | 2026-06-17 |
| From | @claude (orchestration/review/risk) |
| To | @gemini (paid acquisition / Google Ads) |
| Epic | P-002.5 "Manus+Higgsfield Growth Layer" → §4.7 ADS |
| Full spec | `docs/superpowers/specs/2026-06-17-u2algo-marketing-seo-ultraplan-design.md` (READ §1, §2, §4.6 Growth, §4.7 ADS, §6 roadmap) |
| Your tasks | **ADS-0 … ADS-5** (6 tasks). ADS-0..3 = prep (Foundation/QuickWins). ADS-4/5 = SPEND (Scale, CAC-gated). |
| Branch convention | `feat/p0025-ads-<task>-<slug>` per task; docs may batch |

---

## 1. Mission (read, then go to spec §4.7)

u2algo paid acquisition = **Google Ads**. Your job is to make the paid channel **ready** (policy feasibility, account, conversion tracking, campaign blueprint, compliant ad copy) and then run it — **but ZERO live spend until the CAC gate opens.** The whole plan's discipline is *measurement before spend*: no paid ads until ≥14 days + ≥300 organic sessions + a measured non-zero visit→waitlist conversion exist (`cac_gate.json gate_open=true`, owned by GROW-5), AND a CPA target tied to the `$39` lifetime LTV is set.

**Two hard realities you must confront FIRST (ADS-0):**
1. **Google Ads heavily restricts crypto + "trading signals" + speculative/complex financial products**, and bans "get-rich-quick". In several regions advertising a crypto trading bot / signal service is **prohibited or requires advertiser certification**. Your ADS-0 deliverable decides GO / NO-GO / RESTRICTED per region BEFORE you build any campaign. If NO-GO, we redirect budget to channels that allow it (YouTube organic, X, Telegram) — do not force a non-compliant campaign.
2. **The product is "free indicator + waitlist" right now** (PROD-0 decision 2026-06-17). There is no differentiated `$39` premium yet, and the only live track record is NEGATIVE (-5.3%). So ads sell the **free indicator + waitlist**, framed as research/build-in-public — NOT a profit promise, NOT a paid product, NO dollar/performance claims. All ad copy passes the same `content_compliance.py` gate as every other channel.

---

## 2. Model-to-Model Transfer Protocol (same as Hermes — Telegram BANNED)

You work in a separate AI session. Deliver work to @claude for review via git, never Telegram (it corrupts patches).

```
Gemini side                              Local (Claude)
───────────                              ──────────────
1. work on isolated branch off origin/master
2. git format-patch --stdout origin/master..HEAD > NNNN.patch
3. sha256sum NNNN.patch  ───────────────► (paste the sha)
4. push branch OR scp NNNN.patch  ──────►
                                          5. verify sha256 (mismatch = abort, resend)
                                          6. isolated worktree + git am --3way
                                          7. @claude review → PASS push+PR→master / FAIL fix-notes back
```

Most ADS tasks are **doc-only** (`docs/marketing/*.md`) — those can go via a pushed branch. Anything touching `u2algo-site` analytics/UTM coordinates with @hermes (WEB-5/WEB-6 own the event layer — you *consume* it, do not re-implement). `git add -A` banned; stage specific files; origin/master = source of truth.

---

## 3. Your Task Queue (spec §4.7)

### ADS-0 — Google Ads policy feasibility  **[prep · Foundation · do FIRST]**
- **File:** `docs/marketing/google-ads-feasibility.md`
- **Do:** Research and document, per region (EU, US, TR, global): can a SMC-indicator / algorithmic-trading-bot brand be advertised on Google Ads? Cover Google's policies on (a) cryptocurrencies & related products, (b) "complex speculative financial products", (c) trading signals / financial advice, (d) get-rich-quick, (e) advertiser **certification / verification** requirements. Cite the actual Google Ads policy pages.
- **Deliver:** A **GO / NO-GO / RESTRICTED-WITH-CERTIFICATION verdict per region**, plus what certification/landing-page/disclaimer requirements unlock GO. If global NO-GO, recommend the budget reallocation (YouTube/X/TG organic boost).
- **Acceptance:** verdict table per region + cited policy sources + certification checklist + fallback recommendation. This GATES ADS-2/3/4/5.

### ADS-1 — Account structure + conversion tracking design  **[prep · QuickWins]**
- **File:** `docs/marketing/google-ads-account-structure.md`
- **Depends:** WEB-6 (funnel events — @hermes). **Consume** its events, don't build new ones.
- **Do:** Design the Google Ads account: campaign/ad-group hierarchy, GA4 link + conversion import, conversion actions = `waitlist_submit` (primary) + `purchase_complete` (secondary, from WEB-6 / server.js:247 LS webhook). Define attribution window, value, and that **no spend happens here** — this is tracking readiness only.
- **Acceptance:** account-structure doc + conversion-action spec mapped to WEB-6 events + GA4 import steps. No campaign goes live.

### ADS-2 — Search-campaign blueprint + keyword/negatives  **[prep · QuickWins]**
- **File:** `docs/marketing/google-ads-campaign-blueprint.md`
- **Depends:** SEO-1 (keyword map — @claude), ADS-0.
- **Do:** Map the commercial + branded keyword clusters (from SEO-1 `SEO_KEYWORD_MAP.md`) to Search campaigns / ad groups. Match types. Negative-keyword list (exclude "free", "crack", job-seekers, irrelevant "u2" matches). **Flag the SMC/ICT head-term saturation + CPC reality** (governance HIGH: LuxAlgo-class competition; expect high CPC on "order block indicator" etc.). Recommend starting **branded + long-tail only** until conversion data justifies head-term bids.
- **Acceptance:** ad-group → keyword → match-type → negatives table; CPC estimate per cluster; branded-first phasing recommendation.

### ADS-3 — Policy-compliant RSA ad copy (EN-first)  **[prep · QuickWins]**
- **File:** `docs/marketing/google-ads-rsa-copy.md`
- **Depends:** CMP-2 (policy matrix), CMP-3 (EN compliance gate — must be merged), ADS-0.
- **Do:** Write Responsive Search Ad assets (15 headlines / 4 descriptions per ad group, EN-first). Every line must pass BOTH (a) `content_compliance.py` rules (no "guaranteed profit / risk-free / double your money", no $ / performance %, conservative-proof) AND (b) Google's financial-products policy. Lead with: free SMC indicator, transparent/research framing, education, waitlist CTA. Disclaimer present on the landing the ad points to.
- **Acceptance:** RSA asset sets per ad group; each line annotated as compliance-checked (run it through `scripts/content_compliance.py find_violations` once CMP-3 lands); Google-policy-safe; zero profit/performance claim.

### ADS-4 — Budget/bid + CAC-gate interlock  **[SPEND · Scale · HARD-GATED]**
- **File:** `docs/marketing/google-ads-launch-runbook.md` + operator account/billing actions
- **Depends:** GROW-5 (`cac_gate.json`), ADS-1.
- **Do:** Define CPA target ≤ a function of `$39` LTV (account for refund/churn). Bid strategy (start Manual CPC or Maximize Conversions with CPA cap). Daily budget cap + a kill-switch rule. **The launch runbook states explicitly: ads go live ONLY when `cac_gate.json gate_open=true` AND operator signs off the spend.**
- **Acceptance:** runbook with CPA math, daily cap, kill-switch, and the CAC-gate + operator-sign-off precondition written as a hard checklist. No spend until checklist passes.

### ADS-5 — Landing alignment + paid UTM  **[SPEND-adjacent · Scale]**
- **File:** `docs/marketing/google-ads-landing-alignment.md`
- **Depends:** ADS-2, SEO-5 (pillar briefs — @claude).
- **Do:** Message-match each ad group to its destination pillar page (no bait-and-switch — Google quality + policy). Tag all paid destination URLs `utm_medium=paid&utm_source=google&utm_campaign=<cluster>` so GROW-2/GROW-9 attribute paid conversions separately from organic. Verify the full ad→landing→waitlist conversion path before any spend.
- **Acceptance:** ad-group → pillar-page mapping + paid-UTM convention + pre-launch conversion-path verification checklist.

---

## 4. Operator-Gated (you cannot proceed past these)
| Blocker | Owner | Blocks |
|---|---|---|
| Google Ads account + billing + business verification | @operator | ADS-1 setup, ADS-4 spend |
| Advertiser certification (if ADS-0 says RESTRICTED) | @operator | ADS-4 go-live |
| `cac_gate.json gate_open=true` (≥14d, ≥300 sessions, non-zero conv) | GROW-5 / data | **all spend (ADS-4/5)** |
| Operator spend sign-off + monthly budget cap | @operator | ADS-4 go-live |
| PROD-0 reframe (free+waitlist) | settled 2026-06-17 | ad copy says "free indicator + waitlist", not "buy" |

Secrets (Google Ads API / GA4 IDs) → VPS/Railway env-only if any automation; never repo/commit/log. Most ADS work is doc + manual account config, minimal secrets.

## 5. Review Gates
- Each ADS doc PR → @claude review (and CMP/compliance lens on ADS-3 copy).
- ADS-3 copy must pass `content_compliance.py` after CMP-3 lands.
- ADS-4 spend gated on GROW-5 CAC gate + operator sign-off.
- Whole initiative → operator `/ultrareview` at the end.

## 6. Invariant Checklist (before each PR)
- [ ] No trade-path / engine touch (you only write `docs/marketing/*` + coordinate UTM with @hermes WEB-6).
- [ ] Ad copy passes `content_compliance` (no profit/performance/$, disclaimer on landing) AND Google financial policy.
- [ ] No live spend before CAC gate green + operator sign-off (ADS-4/5).
- [ ] Conservative proof: zero $ / performance % in any ad asset pre-90-day.
- [ ] Consume WEB-6 events / GROW-2 UTM; do not re-implement analytics.
- [ ] git format-patch + sha256 handoff; no Telegram; specific `git add`.

---

*End of Gemini handoff. Spec §4.7. Start with ADS-0 (feasibility) — it may GO/NO-GO the whole channel. Everything additive, doc-first, spend hard-gated on CAC + operator sign-off.*
