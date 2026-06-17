# SEO-1 — EN-first Keyword-Cluster Map + Manus RACI (CANONICAL)

| Field | Value |
|---|---|
| Task | SEO-1 (supersedes P-002 M10; **canonical Manus-SEO doc** — SD-7/WEB-9/GROW-3/ADS-2/TVS-1 reference this, do not duplicate) |
| Owner | @claude |
| Status | v1 2026-06-17 |
| Spec | §4.1, §5.1, §5.2 |

## 0. Pivot note (BINDING)
Audience = **GLOBAL / EN-FIRST** (operator 2026-06-17), overriding P-002's TR-first. Primary keyword set is English; TR is a secondary `/tr` hreflang layer. Rationale: SMC/ICT is an EN-native niche and the free TradingView indicator (the lead magnet) is a global surface.

## 1. Keyword clusters → page → domain → intent → funnel

| # | Cluster | Domain | Intent | Funnel | Head keywords | Long-tail spokes | Target page |
|---|---|---|---|---|---|---|---|
| C1 | Smart Money Concepts education | u2algo.com | info | TOFU | smart money concepts, smc trading explained, what is smc trading | smc vs price action, smc for beginners, smc trading rules | Pillar #1 `/en/smart-money-concepts` |
| C2 | SMC/ICT bot & automation | u2algo.com | commercial | MOFU | smc trading bot, ict algo trading bot, automated smc strategy | open source smc bot, smc bot python, algorithmic smc trading | Pillar #2 `/en/smc-trading-bot` |
| C3 | Order Block / FVG indicators | u2algo.com | commercial | BOFU | order block indicator, fvg indicator tradingview, best order block indicator | free order block indicator, fair value gap indicator, breaker block indicator | Pillar #3 `/en/order-block-indicator` |
| C4 | ICT concepts | u2algo.com | info | TOFU | ict trading, ict order blocks, ict concepts explained | ict vs smc, liquidity sweep ict, ict killzones | Pillar #4 `/en/ict-algo-trading` |
| C5 | Transparent track record / build-in-public | u2algo.com | commercial | MOFU | honest trading bot results, build in public trading, verified trading bot | trading bot transparency, research log trading, open backtest results | Pillar #5 `/en/research-log` (shape+% only; research-log frame) |
| C6 | Free TradingView SMC indicator | u2algo.com + TradingView | commercial/branded | BOFU/entry | tradingview smc indicator, free smc indicator, u2algo indicator | smc indicator no repaint, tradingview order block script | Pillar #6 `/en/tradingview-smc-indicator` + the TV script listing (TVS-1) |
| C7 | u2algo brand + dashboard | both | branded | BOFU | u2algo, u2algo bot, u2algo dashboard, u2algo login, u2algo review | u2algo indicator review, u2algo waitlist, is u2algo legit | Pillar #7 `bot.u2algo.com` landing + home |
| C8 | SMC risk management | u2algo.com | info | MOFU | smc risk management, r:r trading strategy, drawdown control | risk per trade smc, position sizing crypto, max drawdown bot | Pillar #8 `/en/smc-risk-management` |
| C9 | Long-tail spokes | u2algo.com | info | — | — | fair value gap vs order block, best timeframe for smc, breaker block explained, choch vs bos, equal highs lows trading | Supporting (10-15) |
| C10 | TR secondary (`/tr` hreflang) | u2algo.com | info | — | smart money concepts nedir, order block göstergesi, tradingview smc indikatörü | smc stratejisi nedir, fvg nedir, likidite avı | `/tr` mirrors of pillars 1/3/6 |

## 2. Near-term reality (governance HIGH — KPI guard)
SMC/ICT head terms (C3/C4 heads) are **saturated, authority-dominated** (LuxAlgo-class). A brand-new domain will not rank head terms for 6-12 months. **First 90 days target ONLY: branded (C7) + long-tail (C9 spokes) + the TradingView script-library channel (C6 / TVS-1)** — the one surface with a built-in audience. SEO-1 KPI = branded/long-tail impressions baseline + indexed-page count, NOT "+50% head-term." Head-term pillars are a 6-12mo compounding bet, not a Q1 deliverable.

## 3. Manus.im SEO vs hand-built — CANONICAL RACI
(SD-7 = social-profile slice; WEB-9 = canonical-conflict slice; GROW-3 = analytics slice; all reference THIS table.)

| Concern | Manus.im owns | Hand-built (us) | Coordinate |
|---|---|---|---|
| DNS / registrar config | ✅ | | domains bought via Manus |
| XML sitemap submission to GSC/Bing | ✅ submits | ✅ we own canonical `sitemap.xml` | Manus submits OUR file |
| Page `<head>` meta/title generation | suggests only | ✅ all `<head>` final | **MANUS-CAP blocker: confirm Manus does NOT auto-write `<head>`** |
| Keyword-suggestion feed | ✅ | | input to this map |
| JSON-LD schema (Org/SoftwareApp/FAQ/Breadcrumb) | | ✅ all | SEO-3 owns |
| hreflang EN/TR | | ✅ | SEO-4 |
| Pillar/supporting IA + internal-linking | | ✅ | SEO-5/SEO-6 |
| Editorial briefs / copy | generic (rejected) | ✅ all (compliance-gated) | Manus copy → `content_compliance` before publish (CMP-8) |
| Social-profile SEO / link-in-bio | ✅ | | SD-7 slice |

## 4. Technical-SEO checklist (feeds SEO-3)
schema.org Organization + SoftwareApplication (free indicator, **no `$39` offer** per PROD-0) + FAQ + BreadcrumbList · canonical (audit: all 5 live pages already have exactly 1 — confirm, don't blindly add) · hreflang EN/TR bidirectional · `bot.u2algo.com` app `noindex`, landing indexable · staging `bot.ualgotrade.com` full `noindex` · CWV targets (LCP <2.5s, INP <200ms, CLS <0.1) · one `sitemap.xml`.

## Acceptance (SEO-1)
- [x] ≥9 clusters, ≥40 keywords, TR cluster ≥6, EN-first pivot noted.
- [x] Each cluster → domain + intent + funnel + target page.
- [x] Canonical Manus-SEO RACI (zero-ambiguous; dedups SD-7/WEB-9/GROW-3/ADS-2).
- [x] Near-term reality KPI guard recorded.

*Downstream: SEO-3 (schema/canonical), SEO-5 (pillar briefs), ADS-2 (Gemini campaign blueprint — parked, organic), TVS-1 (Gemini TV-script SEO), CON-7 (copy keywords) reference this.*
