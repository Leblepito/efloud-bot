# SD-2 — Content Repurposing Matrix (1 → N, EN-first)

| Field | Value |
|---|---|
| Task | SD-2 (gates SD-3/4/5/6, SD-10; references SD-1 handles, CON-1 creative, SEO-1 keywords) |
| Owner | @claude |
| Status | v1 2026-06-17 |
| Spec | §4.3 SD-2 |

## 1. Four content pillars
| Pillar | Theme | Maps to |
|---|---|---|
| **P-A Build-in-public** | the research log, honest progress, what shipped (research-log frame) | SEO C5, CON transparency beat |
| **P-B Risk & methodology** | SMC risk discipline, R:R, drawdown control (no profit talk) | SEO C8 |
| **P-C SMC/ICT education** | order blocks, FVG, EQH-EQL, breaker — what the FREE indicator draws | SEO C1/C3/C4, CON-6 |
| **P-D Free indicator + waitlist** | the TradingView lead magnet + early-access waitlist | SEO C6, PROD-0 |

## 2. Repurposing matrix — 1 pillar piece → N derivatives (leverage target ≥6)
| Derivative | P-A | P-B | P-C | P-D | Format (CON-3) |
|---|---|---|---|---|---|
| X thread (EN) | ✅ | ✅ | ✅ | ✅ | 5-8 tweets, aggregate-only |
| X single + chart (EN) | ✅ | | ✅ | ✅ | 1 image (real TV capture) |
| IG carousel (EN) | | ✅ | ✅ | ✅ | 4-6 slides 1080² |
| IG Reel / Short (EN) | ✅ | | ✅ | ✅ | 9:16 ≤15s segment (Higgsfield, CON-2) |
| Telegram snapshot (EN) | ✅ | | | ✅ | text + 1 image, aggregate digest (SD-5) |
| YouTube long (EN) | ✅ | ✅ | ✅ | | 16:9 screen-record, $0 Higgsfield (SD-6) |
| YouTube Short (EN) | ✅ | | ✅ | ✅ | 9:16 |
| Blog / pillar section (EN) | ✅ | ✅ | ✅ | ✅ | SEO pillar/supporting (SEO-5) |
| TR derivative (`/tr`, social) | secondary | secondary | secondary | secondary | EN-first → TR localized after |

**Leverage:** one P-C education piece → X thread + IG carousel + Reel + YT Short + blog section + TG snapshot = 6 derivatives. Cadence: 3-5 posts/week (SD-10 calendar), EN-primary, TR derivative where it adds reach.

## 3. Hard rules per derivative
- Every piece → SD-8 approval queue (draft-only, no auto-publish), passes `content_compliance` (CMP-2/CMP-3) + B1 disclaimer (CMP-1), `lang='en'` for EN.
- **Aggregate-only** for any results: count / win-rate% / R:R / equity SHAPE — NEVER per-trade entry/SL/TP, NEVER `$`-PnL (signal-service guard + conservative proof).
- Shipped-feature allowlist only (OB/FVG/EQH-EQL/Breaker); **no "CHoCH/BOS" claims, no "signals"** (CON-1, #221).
- Real TradingView captures, not fabricated charts.
- Handles per SD-1 (no unclaimed-handle reference); **`efloud`/`Leblepito` scrubbed** from any reused launch-asset before mapping.

## 4. Source → derivative flow
`content_jobs.py` CLOSED-trade aggregate event (flag-OFF, read-only) → P-A/P-D draft seed → SD-2 maps to derivatives → SD-8 queue → human approve → manual post. No trade-path write; no auto-publish.

## Acceptance (SD-2)
- [x] 4 pillars × derivative matrix (≥6 leverage).
- [x] EN-first / TR-derivative split.
- [x] Compliance + aggregate-only + shipped-feature + handle/efloud-scrub rules.
- [x] Draft-only source→queue flow (no trade-path, no auto-publish).
