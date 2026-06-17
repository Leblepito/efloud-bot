# GROW-1 — Funnel KPI Dictionary + Measurement-Before-Spend

| Field | Value |
|---|---|
| Task | GROW-1 (gates GROW-2 UTM, KPI-ROUTINE, GROW-5 CAC gate, ADS-1) |
| Owner | @claude |
| Status | v1 2026-06-17 |
| Spec | §4.6 GROW-1 |

## 1. Funnel stages + events
`visit → cta_click → waitlist_submit → proof_view` (WEB-6) **+ `checkout_click → purchase_complete`** (the live `$39` founding path, server.js:247 LS webhook — DevEx/recon HIGH: there are TWO terminal events, waitlist AND purchase).

## 2. Metric dictionary
| Metric | Formula | Source | Cadence | Split |
|---|---|---|---|---|
| Impressions | platform reach | Plausible/GA4 + channel native | weekly | channel, EN/TR |
| CTR to site | clicks / impressions | analytics + UTM | weekly | channel |
| Sessions | unique visits | Plausible (cookieless) | daily→weekly | channel, EN/TR |
| **Visit→Waitlist % (NORTH-STAR)** | waitlist_submit / sessions | WEB-6 + Supabase `waitlist_leads` | weekly | channel (utm_source), EN/TR |
| Waitlist count | rows in `waitlist_leads` | Supabase | weekly | source |
| Checkout→Purchase % | purchase_complete / checkout_click | WEB-6 + LS webhook | weekly | channel |
| New founding customers | `entitlements` granted | Supabase `entitlements` | weekly | source |
| Churn / refund | entitlements revoked | Supabase | weekly | — |
| **CAC** | spend / new customers | spend (ADS-4) / entitlements | monthly | channel |
| MRR/LTV | (one-time) $39 × net customers | LS / entitlements | monthly | — |
| Retention | active entitlements / granted | Supabase | monthly | — |

**$ columns (CAC, MRR/LTV) are `null` until the 90-day proof milestone (GROW-8) AND there is real spend.** Pre-milestone the dictionary tracks counts + % only (conservative-proof).

## 3. CAC gate thresholds (GROW-5 `cac_gate.json`)
`gate_open = true` ONLY when ALL hold:
- ≥ **14 days** of analytics data, AND
- ≥ **300 organic sessions**, AND
- a **measured non-zero** visit→waitlist conversion.

While `gate_open=false`: **no paid spend** (ADS-4 hard-gated). This is the *measurement-before-spend* rule (P-002 R-001). Thresholds are a low-volume-niche starting point; operator may tune (spec §10 OQ#8).

## 4. Dual-funnel attribution (DevEx HIGH)
Two revenue-relevant events exist: **waitlist** (lead) and **purchase** (the live $39 founding). KPIs track BOTH:
- Lead CAC = spend / waitlist_submit (pre-revenue proxy).
- Purchase CAC = spend / purchase_complete (true CAC once spend exists).
Per PROD-0 the primary CTA is waitlist; purchase is the optional founding/early-access path. GROW-8's 90-day gate unlocks dollar-PnL **claims**, NOT "premium product" (premium is already purchasable as founding).

## 5. Break-even rule
A paid channel is only sustainable if **Purchase CAC ≤ net $39 LTV** (after LS fees + refund rate). Organic channels have ~0 marginal cost → always run. This rule + the CAC gate together govern when (if ever, per ADS-0 NO-GO) paid scales.

## Acceptance (GROW-1)
- [x] ≥10 metrics with formula/source/cadence + channel + EN/TR split.
- [x] North-Star = visit→waitlist %.
- [x] CAC gate thresholds defined (≥14d, ≥300 sessions, non-zero conv).
- [x] Dual funnel (waitlist + purchase) + purchase-CAC; $ null pre-milestone.
- [x] Break-even + measurement-before-spend policy.

*Downstream: GROW-2 (UTM persists `source`), KPI-ROUTINE (aggregates these), GROW-5 (CAC gate), GROW-6 (dashboard schema), ADS-1 (conversion actions).*
